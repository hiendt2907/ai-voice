"""Structured slot extraction from Vietnamese utterances.

Extracts ALL slots detectable in a single utterance — name, date, time, specialty,
phone, etc. — allowing multi-slot turns to be absorbed at once.

This is intentionally regex/heuristic-based (not vector): structured data like dates
and phone numbers are parsed patterns, not semantic intent.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

_WEEKDAYS_VN = ["thứ Hai", "thứ Ba", "thứ Tư", "thứ Năm", "thứ Sáu", "thứ Bảy", "Chủ Nhật"]

_SPECIALTY_MAP = {
    "nội soi tiêu hóa": "Nội soi - Tiêu hóa",
    "nội soi dạ dày": "Nội soi - Tiêu hóa",
    "nội soi đại tràng": "Nội soi - Tiêu hóa",
    "nội soi": "Nội soi - Tiêu hóa",
    "tiêu hóa": "Tiêu hóa",
    "nội khoa": "Nội khoa",
    "dạ dày": "Tiêu hóa",
    "gan": "Tiêu hóa",
    "mật": "Tiêu hóa",
    "ruột": "Tiêu hóa",
    "tim mạch": "Tim mạch",
    "tim": "Tim mạch",
    "da liễu": "Da liễu",
    "nha khoa": "Nha khoa",
    "răng hàm mặt": "Nha khoa",
    "răng": "Nha khoa",
    "nhãn khoa": "Nhãn khoa",
    "mắt": "Nhãn khoa",
    "tai mũi họng": "Tai mũi họng",
    "tmh": "Tai mũi họng",
    "tai": "Tai mũi họng",
    "mũi": "Tai mũi họng",
    "họng": "Tai mũi họng",
    "cơ xương khớp": "Xương khớp",
    "xương khớp": "Xương khớp",
    "cột sống": "Xương khớp",
    "khớp": "Xương khớp",
    "thần kinh": "Thần kinh",
    "não": "Thần kinh",
    "nhi khoa": "Nhi khoa",
    "nhi": "Nhi khoa",
    "trẻ em": "Nhi khoa",
    "trẻ con": "Nhi khoa",
    "sản phụ khoa": "Sản phụ khoa",
    "phụ khoa": "Sản phụ khoa",
    "sản khoa": "Sản phụ khoa",
    "ung bướu": "Ung bướu",
    "ung thư": "Ung bướu",
    "hô hấp": "Hô hấp",
    "phổi": "Hô hấp",
    "thận tiết niệu": "Thận - Tiết niệu",
    "tiết niệu": "Thận - Tiết niệu",
    "thận": "Thận - Tiết niệu",
    "nội tiết": "Nội tiết",
    "tiểu đường": "Nội tiết",
    "tuyến giáp": "Nội tiết",
    "khám tổng quát": "Khám tổng quát",
    "tổng quát": "Khám tổng quát",
    "tổng kiểm tra": "Khám tổng quát",
    "kiểm tra sức khỏe": "Khám tổng quát",
    "tầm soát": "Khám tổng quát",
    "khám sức khỏe": "Khám tổng quát",
    "phục hồi chức năng": "Phục hồi chức năng",
    "vật lý trị liệu": "Phục hồi chức năng",
    "tâm thần kinh": "Tâm thần kinh",
    "tâm thần": "Tâm thần kinh",
    "tâm lý": "Tâm thần kinh",
}

_SPECIALTY_MAP_SORTED = sorted(_SPECIALTY_MAP.items(), key=lambda x: len(x[0]), reverse=True)

_SYMPTOM_MAP: dict[str, str] = {
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
    "tim đập nhanh": "Tim mạch",
    "tim đập loạn": "Tim mạch",
    "đau ngực": "Tim mạch",
    "tức ngực": "Tim mạch",
    "hồi hộp": "Tim mạch",
    "khó thở khi gắng sức": "Tim mạch",
    "khó thở": "Hô hấp",
    "thở khò khè": "Hô hấp",
    "viêm phổi": "Hô hấp",
    "viêm phế quản": "Hô hấp",
    "ho kéo dài": "Hô hấp",
    "ho ra máu": "Hô hấp",
    "đau đầu dữ dội": "Thần kinh",
    "đau nửa đầu": "Thần kinh",
    "đau đầu": "Thần kinh",
    "chóng mặt": "Thần kinh",
    "tê liệt": "Thần kinh",
    "co giật": "Thần kinh",
    "mất ngủ": "Thần kinh",
    "nổi mẩn ngứa": "Da liễu",
    "nổi mề đay": "Da liễu",
    "nổi mẩn": "Da liễu",
    "ngứa da": "Da liễu",
    "mụn trứng cá": "Da liễu",
    "viêm da": "Da liễu",
    "rụng tóc": "Da liễu",
    "đau lưng dưới": "Xương khớp",
    "đau cột sống": "Xương khớp",
    "đau khớp gối": "Xương khớp",
    "đau lưng": "Xương khớp",
    "đau khớp": "Xương khớp",
    "tê tay": "Xương khớp",
    "tê chân": "Xương khớp",
    "đau tai": "Tai mũi họng",
    "ù tai": "Tai mũi họng",
    "nghẹt mũi": "Tai mũi họng",
    "chảy mũi": "Tai mũi họng",
    "đau họng": "Tai mũi họng",
    "viêm amidan": "Tai mũi họng",
    "viêm xoang": "Tai mũi họng",
    "mờ mắt": "Nhãn khoa",
    "đau mắt": "Nhãn khoa",
    "đỏ mắt": "Nhãn khoa",
    "chảy nước mắt": "Nhãn khoa",
    "tiểu nhiều": "Nội tiết",
    "khát nước nhiều": "Nội tiết",
    "tăng cân": "Nội tiết",
    "giảm cân bất thường": "Nội tiết",
    "phù chân": "Thận - Tiết niệu",
    "tiểu buốt": "Thận - Tiết niệu",
    "tiểu ra máu": "Thận - Tiết niệu",
    "con sốt": "Nhi khoa",
    "trẻ sốt": "Nhi khoa",
    "bé bệnh": "Nhi khoa",
    "con bệnh": "Nhi khoa",
    "mệt mỏi": "Khám tổng quát",
    "sụt cân": "Khám tổng quát",
    "không khỏe": "Khám tổng quát",
}

_SYMPTOM_MAP_SORTED = sorted(_SYMPTOM_MAP.items(), key=lambda x: len(x[0]), reverse=True)

_NAME_CAP = r"[A-ZĐẮẰẲẴẶẤẦẨẪẬÁÀÃẢẠÉÈẺẼẸẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌỐỒỔỖỘỚỜỞỠỢÚÙỦŨỤỨỪỬỮỰÝỲỶỸỴ]"
# Anchored on a keyword ("tên là", "họ tên") — safe to match case-insensitively
# since the captured name text isn't validated by case.
_NAME_PATTERNS = [
    r"(?:tôi|em|anh|chị|bạn)\s+tên\s+(?:là\s+)?(.{2,35})",
    r"tên\s+(?:tôi|em|anh|chị|bạn)\s+(?:là\s+)?(.{2,35})",
    r"tên\s+là\s+(.{2,35})",
    r"họ\s+tên\s+(?:là\s+)?(.{2,35})",
    r"bệnh\s+nhân\s+(?:tên|là)\s+(.{2,35})",
]
# Rely on an actual capital letter to distinguish a name from an ordinary
# word ("cho tôi số điện thoại" must NOT match as a name) — must stay
# case-SENSITIVE. re.IGNORECASE would fold the uppercase-only character
# class down to match lowercase too, defeating the whole point of requiring
# a capital. Found via a dynamic LLM-caller test: "báo lại cho tôi số điện
# thoại" was extracted as patient_name "Tôi Số Điện".
_NAME_PATTERNS_CASE_SENSITIVE = [
    r"(?:tôi|em|anh|chị)\s+là\s+(" + _NAME_CAP + r"[a-zA-ZÀ-ỹ ]{2,34})",
    r"(?:đặt\s+cho|khám\s+cho|lịch\s+cho|cho)\s+(?:anh|chị|em|bạn|ông|bà|cô|chú|bác)?\s*(" + _NAME_CAP + r"[a-zA-ZÀ-ỹ ]{1,34})",
    # "Đặng Tập Hiền, số điện thoại 0909..." — name before comma followed by phone keyword
    r"^(" + _NAME_CAP + r"[a-zA-ZÀ-ỹ ]{1,34}),\s*(?:số|sdt|đt\b|điện)",
]


def _weekday_vn(weekday: int) -> str:
    return _WEEKDAYS_VN[weekday]


def _format_date_vn(dt: datetime) -> str:
    return f"{_weekday_vn(dt.weekday())}, ngày {dt.day:02d}/{dt.month:02d}/{dt.year}"


def extract_slots(utterance: str) -> dict[str, str]:
    """Extract ALL structured slots from utterance.

    Runs all extractors unconditionally — callers receive a complete dict of
    everything found. The FSM/executor decides which slots are relevant for
    the current step and merges them into session state.
    """
    slots: dict[str, str] = {}
    utt = utterance.lower().strip()
    now = datetime.now()

    # ── Date ────────────────────────────────────────────────────────────────
    appointment_date: str | None = None
    if re.search(r"\bhôm nay\b|\bngày hôm nay\b|(?:sáng|chiều|tối)\s+nay\b|\bnay\b(?=\s+đi\b)", utt):
        appointment_date = _format_date_vn(now)
    elif re.search(r"\bngày mai\b", utt):
        appointment_date = _format_date_vn(now + timedelta(days=1))
    elif re.search(r"\bngày mốt\b|\bmốt\b", utt):
        appointment_date = _format_date_vn(now + timedelta(days=2))
    # "ngày kia" is NOT a synonym of "ngày mốt" — the Vietnamese sequential
    # day idiom is hôm nay(+0) → mai(+1) → mốt(+2) → kia(+3) → kìa(+4). Found
    # via real manual testing: a caller said "ngày kia" (asking for +3) and
    # got told +2 back, then had to correct the AI ("ngày kia đâu phải
    # 23/8... 23/8 là ngày mốt"). "kìa" is one more day than "kia" — a
    # 100-call batch test caught these being conflated too (both landed on
    # the same date), so they must stay in separate branches.
    elif re.search(r"\bngày kìa\b", utt):
        appointment_date = _format_date_vn(now + timedelta(days=4))
    elif re.search(r"\bngày kia\b", utt):
        appointment_date = _format_date_vn(now + timedelta(days=3))
    # Vietnamese counting-word phrasing ("hai/ba/bốn hôm nữa", "còn N bữa
    # nữa") — handled directly by regex instead of relying on the LLM
    # slot-recovery path to map it onto one of the keyword phrases above.
    # Found via the same batch test: the LLM prompt only had explicit
    # examples up to "ba hôm nữa" → it silently mapped "bốn hôm nữa" to the
    # same (wrong, one day short) answer as "ba hôm nữa" since it had no
    # +4 keyword to reach for.
    elif (m := re.search(r"\b(hai|ba|bốn|năm|sáu|bảy)\s+(?:hôm|ngày|bữa)\s+nữa\b", utt)):
        _NUM_WORDS = {"hai": 2, "ba": 3, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7}
        appointment_date = _format_date_vn(now + timedelta(days=_NUM_WORDS[m.group(1)]))
    # Same idiom, digit form ("còn 2 ngày nữa", "3 bữa nữa") — a batch test
    # caught this falling through the word-form branch above straight to
    # the LLM, which guessed wrong (+3 instead of +2) with no exact keyword
    # to anchor on.
    elif (m := re.search(r"\b(\d{1,2})\s+(?:hôm|ngày|bữa)\s+nữa\b", utt)):
        appointment_date = _format_date_vn(now + timedelta(days=int(m.group(1))))
    else:
        _WEEKDAY_PATTERNS = [
            (r"\bthứ\s*hai\b", 0), (r"\bthứ\s*ba\b", 1), (r"\bthứ\s*tư\b", 2),
            (r"\bthứ\s*năm\b", 3), (r"\bthứ\s*sáu\b", 4),
            (r"\bthứ\s*bảy\b|\bthứ\s*7\b", 5), (r"\bchủ\s*nhật\b", 6),
        ]
        _has_next_week = bool(re.search(r"\btuần sau\b|\btuần tới\b|\btuần kế\b", utt))
        for pattern, target_wd in _WEEKDAY_PATTERNS:
            if re.search(pattern, utt):
                if _has_next_week:
                    # Compound phrase like "thứ Ba tuần sau" — this must land
                    # on that weekday IN NEXT WEEK, not just today+7 raw days.
                    # A caller-LLM dynamic test caught the old "tuần sau"
                    # branch (today+7 unconditional, checked before this loop)
                    # winning over the named weekday whenever both appeared in
                    # the same utterance: today Saturday + "thứ Ba tuần sau"
                    # got resolved to next Saturday instead of next Tuesday.
                    this_monday = now - timedelta(days=now.weekday())
                    next_monday = this_monday + timedelta(days=7)
                    appointment_date = _format_date_vn(next_monday + timedelta(days=target_wd))
                else:
                    days_ahead = (target_wd - now.weekday()) % 7 or 7
                    appointment_date = _format_date_vn(now + timedelta(days=days_ahead))
                break
        if appointment_date is None and _has_next_week:
            appointment_date = _format_date_vn(now + timedelta(days=7))
        if appointment_date is None:
            m = re.search(
                r"(?:ngày\s+)?(\d{1,2})\s*(?:tháng|/|-)\s*(\d{1,2})|ngày\s+(\d{1,2})(?!\s*tháng)",
                utterance, re.IGNORECASE,
            )
            if m:
                day = int(m.group(1) or m.group(3))
                month = int(m.group(2)) if m.group(2) else now.month
                try:
                    dt = datetime(now.year, month, day)
                    if dt.date() < now.date():
                        month = month % 12 + 1
                        year = now.year if month > 1 else now.year + 1
                        dt = datetime(year, month, day)
                    appointment_date = _format_date_vn(dt)
                except ValueError:
                    pass
    if appointment_date:
        slots["appointment_date"] = appointment_date

    # ── Time of day (parse before hour so we can do AM/PM correction) ────────
    if re.search(r"\bsáng\b", utterance, re.IGNORECASE):
        slots["time_of_day"] = "sáng"
    elif re.search(r"\bchiều\b", utterance, re.IGNORECASE):
        slots["time_of_day"] = "chiều"
    elif re.search(r"\btối\b", utterance, re.IGNORECASE):
        slots["time_of_day"] = "tối"

    # ── Hour ────────────────────────────────────────────────────────────────
    # Prefer the LAST "lúc/khoảng/đặt N giờ" anchored mention over a bare
    # match. An utterance can contain an incidental hour that isn't the
    # requested appointment time at all — e.g. "Chủ nhật chỉ làm đến 12 giờ
    # thôi hả? ... vậy tôi đặt lịch thứ Hai lúc 8 giờ sáng nhé" — the old
    # single re.search grabbed the leftmost number ("12", the clinic's
    # closing time) instead of the customer's actual anchored request ("lúc
    # 8 giờ"). Found via a dynamic LLM-caller test. Falling back to the last
    # bare mention (not the first) matches how this file already treats
    # other self-corrected values (date, time_of_day) — the caller's final
    # stated number wins over an earlier aside.
    anchored = list(re.finditer(r"(?:lúc|khoảng|đặt)\s+(\d{1,2})\s*(?:giờ|h)\b", utt, re.IGNORECASE))
    bare = list(re.finditer(r"(\d{1,2})\s*(?:giờ|h)\b", utt, re.IGNORECASE))
    hour_m = anchored[-1] if anchored else (bare[-1] if bare else None)
    if hour_m:
        h = int(hour_m.group(1))
        # AM/PM correction: "3h chiều" → 15, "11h sáng" → 11
        tod = slots.get("time_of_day")
        if tod == "chiều" and 1 <= h <= 6:
            h += 12
        elif tod == "tối" and 1 <= h <= 5:
            h += 12
        if 6 <= h <= 21:
            slots["appointment_hour"] = str(h)

    # Infer time_of_day from hour if not already set
    if "time_of_day" not in slots and "appointment_hour" in slots:
        h = int(slots["appointment_hour"])
        slots["time_of_day"] = "sáng" if h < 12 else ("chiều" if h < 18 else "tối")

    if "time_of_day" in slots:
        tod = slots["time_of_day"]
        hour = slots.get("appointment_hour")
        slots["time_slot"] = f"buổi {tod} lúc {hour} giờ" if hour else f"buổi {tod}"

    # ── Patient name ─────────────────────────────────────────────────────────
    for pattern, ignore_case in (
        *((p, True) for p in _NAME_PATTERNS),
        *((p, False) for p in _NAME_PATTERNS_CASE_SENSITIVE),
    ):
        nm = re.search(pattern, utterance, re.IGNORECASE if ignore_case else 0)
        if nm:
            # Stop at comma (which signals next clause, not part of the name)
            raw = nm.group(1).strip().split(",")[0].strip()
            words = raw.split()[:3]  # Vietnamese names are ≤3 words
            name = " ".join(words).rstrip(".,!?;:")
            if len(name) >= 2:
                slots["patient_name"] = name.title()
                break

    # ── Nội soi type ─────────────────────────────────────────────────────────
    _has_noisoi = "nội soi" in utt
    _has_da_day = "dạ dày" in utt
    _has_dai_trang = "đại tràng" in utt
    _has_combo = bool(re.search(r"\bcả (hai|2)\b|\bkết hợp\b|\bcombo\b|\bcả dạ dày", utt))
    if _has_combo or (_has_da_day and _has_dai_trang):
        slots["noisoi_type"] = "combo"
    elif _has_dai_trang:
        slots["noisoi_type"] = "dai_trang"
    elif _has_da_day or _has_noisoi:
        slots["noisoi_type"] = "da_day"

    # ── Specialty ────────────────────────────────────────────────────────────
    for keyword, label in _SPECIALTY_MAP_SORTED:
        if keyword in utt:
            slots["specialty"] = label
            break

    # ── Symptom → implied specialty ───────────────────────────────────────────
    if "specialty" not in slots:
        for symptom_phrase, implied_specialty in _SYMPTOM_MAP_SORTED:
            if symptom_phrase in utt:
                slots["specialty"] = implied_specialty
                slots["symptom_description"] = utterance
                break

    # ── Phone ────────────────────────────────────────────────────────────────
    # Reverted the space/dash-tolerant version: that "fix" was validated
    # against my own hand-typed test strings ("090-111-2222") injected via
    # --utterances, which bypasses STT entirely — no caller ever SAYS a
    # dash. Real STT output for a spoken phone number has never actually
    # been checked here. Don't special-case formatting again without
    # evidence from a real --wav/STT-driven test transcript first.
    phone_m = re.search(r"(?<!\d)(0[3-9]\d{8})(?!\d)", utterance)
    if phone_m:
        slots["patient_phone"] = phone_m.group(1)

    # ── Bare Vietnamese name fallback ─────────────────────────────────────────
    # When utterance is 2-4 words all starting with actual capital letters,
    # treat it as a provided name (covers "Nguyễn Văn A" without "tên là" prefix).
    if "patient_name" not in slots:
        words = utterance.strip().split()
        if 2 <= len(words) <= 4 and all(w and w[0].isupper() for w in words):
            slots["patient_name"] = " ".join(words)

    return slots
