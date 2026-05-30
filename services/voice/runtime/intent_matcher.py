"""Example-based intent matcher for mock replay and testing.

In production this will be replaced by an LLM-based NLU call.
Matching strategy: case-insensitive substring check against intent examples.
Score is always in [0, 1]: exact=1.0, partial overlap = overlap/longer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class MatchResult:
    intent: str | None
    slots: dict[str, str]
    confidence: float  # 0.0–1.0


_WEEKDAYS_VN = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ Nhật"]

_SPECIALTY_MAP = {
    # Nội khoa & tiêu hóa
    "nội khoa": "Nội khoa",
    "nội soi": "Nội soi - Tiêu hóa",
    "nội soi dạ dày": "Nội soi - Tiêu hóa",
    "nội soi tiêu hóa": "Nội soi - Tiêu hóa",
    "nội soi đại tràng": "Nội soi - Tiêu hóa",
    "tiêu hóa": "Tiêu hóa",
    "dạ dày": "Tiêu hóa",
    "gan": "Tiêu hóa",
    "mật": "Tiêu hóa",
    "ruột": "Tiêu hóa",
    # Tim mạch
    "tim mạch": "Tim mạch",
    "tim": "Tim mạch",
    # Da liễu
    "da liễu": "Da liễu",
    "da dày": "Da liễu",
    "da": "Da liễu",
    # Nha khoa
    "nha khoa": "Nha khoa",
    "răng": "Nha khoa",
    "răng hàm mặt": "Nha khoa",
    # Mắt
    "mắt": "Nhãn khoa",
    "nhãn khoa": "Nhãn khoa",
    # Tai mũi họng
    "tai mũi họng": "Tai mũi họng",
    "tmh": "Tai mũi họng",
    "tai": "Tai mũi họng",
    "mũi": "Tai mũi họng",
    "họng": "Tai mũi họng",
    # Xương khớp
    "xương khớp": "Xương khớp",
    "cơ xương khớp": "Xương khớp",
    "cột sống": "Xương khớp",
    "khớp": "Xương khớp",
    # Thần kinh
    "thần kinh": "Thần kinh",
    "não": "Thần kinh",
    # Nhi
    "nhi": "Nhi khoa",
    "nhi khoa": "Nhi khoa",
    "trẻ em": "Nhi khoa",
    "trẻ con": "Nhi khoa",
    # Sản phụ khoa
    "sản phụ khoa": "Sản phụ khoa",
    "phụ khoa": "Sản phụ khoa",
    "sản khoa": "Sản phụ khoa",
    # Ung bướu
    "ung bướu": "Ung bướu",
    "ung thư": "Ung bướu",
    # Hô hấp
    "hô hấp": "Hô hấp",
    "phổi": "Hô hấp",
    "ho": "Hô hấp",
    "covid": "Hô hấp",
    # Thận - tiết niệu
    "thận tiết niệu": "Thận - Tiết niệu",
    "thận": "Thận - Tiết niệu",
    "tiết niệu": "Thận - Tiết niệu",
    # Nội tiết
    "nội tiết": "Nội tiết",
    "tiểu đường": "Nội tiết",
    "tuyến giáp": "Nội tiết",
    # Khám tổng quát
    "tổng quát": "Khám tổng quát",
    "tổng kiểm tra": "Khám tổng quát",
    "kiểm tra sức khỏe": "Khám tổng quát",
    "tầm soát": "Khám tổng quát",
    "khám sức khỏe": "Khám tổng quát",
    # Phục hồi chức năng
    "phục hồi chức năng": "Phục hồi chức năng",
    "vật lý trị liệu": "Phục hồi chức năng",
    # Tâm thần
    "tâm thần": "Tâm thần kinh",
    "tâm lý": "Tâm thần kinh",
}

# Ordered by length descending so longer, more specific phrases match first
_SPECIALTY_MAP_SORTED = sorted(_SPECIALTY_MAP.items(), key=lambda x: len(x[0]), reverse=True)

# Symptom phrase → implied specialty.
# Ordered by specificity (longer phrases first so "tim đập nhanh" beats "tim").
_SYMPTOM_MAP: dict[str, str] = {
    # Tiêu hóa
    "đau dạ dày": "Tiêu hóa",
    "viêm dạ dày": "Tiêu hóa",
    "trào ngược": "Tiêu hóa",
    "đau bụng": "Tiêu hóa",
    "đầy bụng": "Tiêu hóa",
    "đầy hơi": "Tiêu hóa",
    "buồn nôn": "Tiêu hóa",
    "khó tiêu": "Tiêu hóa",
    "tiêu chảy": "Tiêu hóa",
    "táo bón": "Tiêu hóa",
    # Tim mạch
    "tim đập nhanh": "Tim mạch",
    "tim đập loạn": "Tim mạch",
    "đau ngực": "Tim mạch",
    "tức ngực": "Tim mạch",
    "hồi hộp": "Tim mạch",
    "khó thở khi gắng sức": "Tim mạch",
    # Hô hấp
    "khó thở": "Hô hấp",
    "thở khò khè": "Hô hấp",
    "viêm phổi": "Hô hấp",
    "viêm phế quản": "Hô hấp",
    "ho kéo dài": "Hô hấp",
    "ho ra máu": "Hô hấp",
    # Thần kinh
    "đau đầu dữ dội": "Thần kinh",
    "đau nửa đầu": "Thần kinh",
    "đau đầu": "Thần kinh",
    "chóng mặt": "Thần kinh",
    "tê liệt": "Thần kinh",
    "co giật": "Thần kinh",
    "mất ngủ": "Thần kinh",
    # Da liễu
    "nổi mẩn ngứa": "Da liễu",
    "nổi mề đay": "Da liễu",
    "nổi mẩn": "Da liễu",
    "ngứa da": "Da liễu",
    "mụn trứng cá": "Da liễu",
    "viêm da": "Da liễu",
    "rụng tóc": "Da liễu",
    # Xương khớp
    "đau lưng dưới": "Xương khớp",
    "đau cột sống": "Xương khớp",
    "đau khớp gối": "Xương khớp",
    "đau lưng": "Xương khớp",
    "đau khớp": "Xương khớp",
    "tê tay": "Xương khớp",
    "tê chân": "Xương khớp",
    # Tai mũi họng
    "đau tai": "Tai mũi họng",
    "ù tai": "Tai mũi họng",
    "nghẹt mũi": "Tai mũi họng",
    "chảy mũi": "Tai mũi họng",
    "đau họng": "Tai mũi họng",
    "viêm amidan": "Tai mũi họng",
    "viêm xoang": "Tai mũi họng",
    # Mắt
    "mờ mắt": "Nhãn khoa",
    "đau mắt": "Nhãn khoa",
    "đỏ mắt": "Nhãn khoa",
    "chảy nước mắt": "Nhãn khoa",
    # Nội tiết / Thận
    "tiểu nhiều": "Nội tiết",
    "khát nước nhiều": "Nội tiết",
    "tăng cân": "Nội tiết",
    "giảm cân bất thường": "Nội tiết",
    "phù chân": "Thận - Tiết niệu",
    "tiểu buốt": "Thận - Tiết niệu",
    "tiểu ra máu": "Thận - Tiết niệu",
    # Nhi
    "con sốt": "Nhi khoa",
    "trẻ sốt": "Nhi khoa",
    "bé bệnh": "Nhi khoa",
    "con bệnh": "Nhi khoa",
    # Tổng quát
    "mệt mỏi": "Khám tổng quát",
    "sụt cân": "Khám tổng quát",
    "không khỏe": "Khám tổng quát",
}

_SYMPTOM_MAP_SORTED = sorted(_SYMPTOM_MAP.items(), key=lambda x: len(x[0]), reverse=True)

# Explicit symptom/health-concern markers — caller describes what's wrong with their body
_SYMPTOM_MARKERS = re.compile(
    r"\b(bị|ốm|đau|mệt|sốt|ho|ngứa|nổi mẩn|nổi|viêm|tê|chóng mặt|khó thở|khó chịu"
    r"|không khỏe|triệu chứng|hồi hộp|tức ngực|tiêu chảy|táo bón|buồn nôn|sụt cân|rụng tóc"
    r"|phù|ù tai|chảy mũi|nghẹt mũi|mờ mắt|đỏ mắt|co giật|tê liệt)\b",
    re.IGNORECASE,
)

# Explicit booking-intent markers — caller says they want to book/register
_BOOKING_MARKERS = re.compile(
    r"\b(muốn khám|cần khám|đặt khám|đặt lịch|book lịch|đặt hẹn|đăng ký khám|muốn đặt"
    r"|cho tôi đặt|xin đặt|muốn đăng ký|cho đặt lịch)\b",
    re.IGNORECASE,
)

# Service/inquiry markers — caller is asking for information, not booking yet
_INQUIRY_MARKERS = re.compile(
    r"\b(giá|phí|chi phí|bao nhiêu|thông tin|hỏi|tư vấn|cần chuẩn bị|cần nhịn"
    r"|mất bao lâu|thủ tục|gồm những gì|có những gì|bảo hiểm|được không|như thế nào)\b",
    re.IGNORECASE,
)

# Name extraction patterns, tried in order
_NAME_CAP = r"[A-ZĐẮẰẲẴẶẤẦẨẪẬÁÀÃẢẠÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ]"
_NAME_PATTERNS = [
    # "tên tôi là X", "tên em là X", "anh/chị tên là X"
    r"(?:tôi|em|anh|chị|bạn)\s+tên\s+(?:là\s+)?(.{2,35})",
    # "tên tôi là X" (reversed order)
    r"tên\s+(?:tôi|em|anh|chị|bạn)\s+(?:là\s+)?(.{2,35})",
    # "tên là X"
    r"tên\s+là\s+(.{2,35})",
    # "tôi là X", "em là X" — but avoid matching short common words like "tôi là bệnh nhân"
    r"(?:tôi|em|anh|chị)\s+là\s+(" + _NAME_CAP + r"[a-zA-ZÀ-ỹ ]{2,34})",
    # "họ tên (là) X"
    r"họ\s+tên\s+(?:là\s+)?(.{2,35})",
    # "bệnh nhân tên X" / "bệnh nhân là X"
    r"bệnh\s+nhân\s+(?:tên|là)\s+(.{2,35})",
    # "đặt cho X", "khám cho X", "cho X" + capitalized name
    r"(?:đặt\s+cho|khám\s+cho|lịch\s+cho|cho)\s+(?:anh|chị|em|bạn|ông|bà|cô|chú|bác)?\s*(" + _NAME_CAP + r"[a-zA-ZÀ-ỹ ]{1,34})",
]


def _weekday_vn(weekday: int) -> str:
    return _WEEKDAYS_VN[weekday]


def _format_date_vn(dt: datetime) -> str:
    return f"{_weekday_vn(dt.weekday())}, ngày {dt.day:02d}/{dt.month:02d}/{dt.year}"


def _score(utterance_lower: str, example_text: str) -> float:
    """Compute match score in [0, 1].

    Exact match = 1.0. Partial overlap = len(shorter) / len(longer).
    This keeps scores bounded and avoids false positives where a short
    affirmative like 'đúng' would outscore against a longer deny phrase
    like 'không đúng' under the old len(example)/len(utterance) formula.
    """
    if example_text == utterance_lower:
        return 1.0
    if example_text in utterance_lower:
        return len(example_text) / max(len(utterance_lower), 1)
    if utterance_lower in example_text:
        return len(utterance_lower) / max(len(example_text), 1)
    return 0.0


def match_intent(utterance: str, intents: list[dict]) -> MatchResult:
    """Match utterance against intent catalog using example-based heuristics."""
    utterance_lower = utterance.lower().strip()

    best: MatchResult = MatchResult(intent=None, slots={}, confidence=0.0)

    for intent_def in intents:
        intent_name: str = intent_def["intent"]
        examples: list[dict] = intent_def.get("examples", [])

        for example in examples:
            example_text = example["text"].lower()
            score = _score(utterance_lower, example_text)
            if score > 0 and score > best.confidence:
                slots: dict[str, str] = dict(example.get("slots", {}))
                best = MatchResult(intent=intent_name, slots=slots, confidence=score)

    # Slot extraction independent of intent
    extracted = _extract_slots(utterance)
    merged_slots = {**extracted, **best.slots}

    # When no intent matched (or low confidence) but caller described health symptoms,
    # infer intent from context so the FSM can route sensibly.
    if best.confidence < 0.3:
        inferred = _infer_intent_from_context(utterance_lower, merged_slots)
        if inferred is not None:
            return MatchResult(intent=inferred, slots=merged_slots, confidence=0.4)

    return MatchResult(intent=best.intent, slots=merged_slots, confidence=best.confidence)


def _infer_intent_from_context(utterance_lower: str, slots: dict[str, str]) -> str | None:
    """Infer intent when example matching fails.

    Priority order:
      1. Explicit booking phrase ("muốn khám", "đặt lịch")    → book_appointment
      2. Symptom markers ("bị đau", "ốm", "sốt")              → symptom_described
      3. Inquiry markers ("giá", "thông tin", "cần chuẩn bị") → service_inquiry
      4. Specialty slot extracted with no other signal         → book_appointment
    """
    if _BOOKING_MARKERS.search(utterance_lower):
        return "book_appointment"

    if _SYMPTOM_MARKERS.search(utterance_lower):
        return "symptom_described"

    if _INQUIRY_MARKERS.search(utterance_lower):
        return "service_inquiry"

    if "specialty" in slots:
        return "book_appointment"

    return None


def _extract_slots(utterance: str) -> dict[str, str]:
    slots: dict[str, str] = {}
    utt = utterance.lower().strip()
    now = datetime.now()

    # ── Date resolution ──────────────────────────────────────────────────────
    appointment_date: str | None = None

    if re.search(r"\bhôm nay\b|\bngày hôm nay\b", utt):
        appointment_date = _format_date_vn(now)
    elif re.search(r"\bngày mai\b", utt):
        appointment_date = _format_date_vn(now + timedelta(days=1))
    elif re.search(r"\bngày mốt\b|\bngày kia\b|\bmốt\b", utt):
        appointment_date = _format_date_vn(now + timedelta(days=2))
    elif re.search(r"\btuần sau\b", utt):
        appointment_date = _format_date_vn(now + timedelta(days=7))
    else:
        weekday_names = [
            (r"\bthứ\s*hai\b", 0),
            (r"\bthứ\s*ba\b", 1),
            (r"\bthứ\s*tư\b", 2),
            (r"\bthứ\s*năm\b", 3),
            (r"\bthứ\s*sáu\b", 4),
            (r"\bthứ\s*bảy\b|\bthứ\s*7\b", 5),
            (r"\bchủ\s*nhật\b", 6),
        ]
        for pattern, target_weekday in weekday_names:
            if re.search(pattern, utt):
                days_ahead = (target_weekday - now.weekday()) % 7
                if days_ahead == 0:
                    days_ahead = 7
                appointment_date = _format_date_vn(now + timedelta(days=days_ahead))
                break

        if appointment_date is None:
            m = re.search(
                r"(?:ngày\s+)?(\d{1,2})\s*(?:tháng|/|-)\s*(\d{1,2})|ngày\s+(\d{1,2})(?!\s*tháng)",
                utterance, re.IGNORECASE,
            )
            if m:
                if m.group(1) and m.group(2):
                    day, month = int(m.group(1)), int(m.group(2))
                else:
                    day, month = int(m.group(3)), now.month
                year = now.year
                try:
                    dt = datetime(year, month, day)
                    if dt.date() < now.date():
                        month = month % 12 + 1
                        year = year if month > 1 else year + 1
                        dt = datetime(year, month, day)
                    appointment_date = _format_date_vn(dt)
                except ValueError:
                    pass

    if appointment_date:
        slots["appointment_date"] = appointment_date

    # ── Specific hour ────────────────────────────────────────────────────────
    # "8 giờ", "8h", "lúc 8 giờ", "khoảng 9h sáng", "đặt 10 giờ"
    hour_m = re.search(
        r"(?:lúc\s+|khoảng\s+|đặt\s+)?(\d{1,2})\s*(?:giờ|h)\b",
        utt, re.IGNORECASE,
    )
    if hour_m:
        hour_val = int(hour_m.group(1))
        if 6 <= hour_val <= 21:
            slots["appointment_hour"] = str(hour_val)

    # ── Time of day ──────────────────────────────────────────────────────────
    if re.search(r"\bsáng\b", utterance, re.IGNORECASE):
        slots["time_of_day"] = "sáng"
        # Infer morning from hour if not explicitly said
    elif re.search(r"\bchiều\b", utterance, re.IGNORECASE):
        slots["time_of_day"] = "chiều"
    elif re.search(r"\btối\b", utterance, re.IGNORECASE):
        slots["time_of_day"] = "tối"
    elif "appointment_hour" in slots:
        # Infer time_of_day from hour value
        h = int(slots["appointment_hour"])
        if h < 12:
            slots["time_of_day"] = "sáng"
        elif h < 18:
            slots["time_of_day"] = "chiều"
        else:
            slots["time_of_day"] = "tối"

    # ── time_slot: combined display string ───────────────────────────────────
    if "time_of_day" in slots:
        tod = slots["time_of_day"]
        hour = slots.get("appointment_hour")
        if hour:
            slots["time_slot"] = f"buổi {tod} lúc {hour} giờ"
        else:
            slots["time_slot"] = f"buổi {tod}"

    # ── Patient name ─────────────────────────────────────────────────────────
    for pattern in _NAME_PATTERNS:
        nm = re.search(pattern, utterance, re.IGNORECASE)
        if nm:
            candidate = nm.group(1).strip()
            # Keep only the first 4 words (avoid capturing trailing garbage)
            words = candidate.split()[:4]
            name = " ".join(words).rstrip(".,!?;:")
            if len(name) >= 2:
                slots["patient_name"] = name.title()
                break

    # ── Nội soi type ─────────────────────────────────────────────────────────
    # Must run before specialty detection — order: combo > đại tràng > dạ dày
    _has_noisoi = "nội soi" in utt
    _has_da_day = "dạ dày" in utt
    _has_dai_trang = "đại tràng" in utt
    _has_combo = bool(re.search(r"\bcả (hai|2)\b|\bkết hợp\b|\bcombo\b|\bcả dạ dày", utt))
    if _has_combo or (_has_da_day and _has_dai_trang):
        slots["noisoi_type"] = "combo"
    elif _has_dai_trang:
        slots["noisoi_type"] = "dai_trang"
    elif _has_da_day or _has_noisoi:
        # "nội soi" alone defaults to dạ dày (most common); explicit "đại tràng" overrides above
        if _has_da_day or (not _has_dai_trang and _has_noisoi):
            slots["noisoi_type"] = "da_day"

    # ── Specialty ────────────────────────────────────────────────────────────
    # Try longer keywords first to avoid "da" matching inside "da liễu"
    for keyword, label in _SPECIALTY_MAP_SORTED:
        if keyword in utt:
            slots["specialty"] = label
            break

    # ── Symptom → implied specialty (if no direct specialty keyword found) ───
    if "specialty" not in slots:
        for symptom_phrase, implied_specialty in _SYMPTOM_MAP_SORTED:
            if symptom_phrase in utt:
                slots["specialty"] = implied_specialty
                slots["symptom_description"] = utterance
                break

    # ── Phone number ─────────────────────────────────────────────────────────
    phone_m = re.search(r"(?<!\d)(0[3-9]\d{8})(?!\d)", utterance)
    if phone_m:
        slots["patient_phone"] = phone_m.group(1)

    return slots
