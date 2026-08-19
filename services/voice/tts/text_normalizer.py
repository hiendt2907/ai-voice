"""Vietnamese text normalization before TTS synthesis.

Converts raw text containing dates, numbers, phone numbers, currency, and
time into a form that Piper (and other TTS engines) can read naturally.

All rules are regex-based — no ML dependency.
"""

from __future__ import annotations

import re

# ── Digit words ───────────────────────────────────────────────────────────────

_UNITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_TEENS = [
    "mười", "mười một", "mười hai", "mười ba", "mười bốn",
    "mười lăm", "mười sáu", "mười bảy", "mười tám", "mười chín",
]
_TENS = [
    "", "mười", "hai mươi", "ba mươi", "bốn mươi",
    "năm mươi", "sáu mươi", "bảy mươi", "tám mươi", "chín mươi",
]


def _three_digits(n: int) -> str:
    """Convert 0–999 to Vietnamese words."""
    if n == 0:
        return "không"
    parts: list[str] = []
    h = n // 100
    remainder = n % 100
    if h:
        parts.append(f"{_UNITS[h]} trăm")
    if remainder == 0:
        pass
    elif remainder < 10:
        if h:
            parts.append("lẻ")
        parts.append(_UNITS[remainder])
    elif remainder < 20:
        parts.append(_TEENS[remainder - 10])
    else:
        t, u = divmod(remainder, 10)
        tens_word = _TENS[t]
        if u == 1 and t > 1:
            parts.append(f"{tens_word} mốt")
        elif u == 5 and t >= 1:
            parts.append(f"{tens_word} lăm")
        elif u == 0:
            parts.append(tens_word)
        else:
            parts.append(f"{tens_word} {_UNITS[u]}")
    return " ".join(parts)


def _integer_to_words(n: int) -> str:
    if n == 0:
        return "không"
    if n < 0:
        return "âm " + _integer_to_words(-n)

    parts: list[str] = []
    billion = n // 1_000_000_000
    million = (n % 1_000_000_000) // 1_000_000
    thousand = (n % 1_000_000) // 1_000
    remainder = n % 1_000

    if billion:
        parts.append(_three_digits(billion) + " tỷ")
    if million:
        parts.append(_three_digits(million) + " triệu")
    if thousand:
        parts.append(_three_digits(thousand) + " nghìn")
    if remainder or not parts:
        parts.append(_three_digits(remainder))

    return " ".join(parts)


# ── Conversion helpers ────────────────────────────────────────────────────────

def _normalize_date(m: re.Match) -> str:  # type: ignore[type-arg]
    """DD/MM/YYYY or D/M/YYYY → 'ngày D tháng M năm YYYY'.

    Skips 'ngày' prefix if already present in the surrounding text.
    """
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    prefix = "" if m.group(0) != m.string[m.start():m.end()] else ""
    # Check if 'ngày ' immediately precedes this match
    pre = m.string[max(0, m.start() - 5):m.start()]
    if "ngày" in pre or "Ngày" in pre:
        return f"{day} tháng {month} năm {_integer_to_words(year)}"
    return f"ngày {day} tháng {month} năm {_integer_to_words(year)}"


def _normalize_time(m: re.Match) -> str:  # type: ignore[type-arg]
    """HH:MM or HHhMM → 'H giờ M phút' / 'H giờ'."""
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    if minute:
        return f"{hour} giờ {minute} phút"
    return f"{hour} giờ"


def _normalize_phone(m: re.Match) -> str:  # type: ignore[type-arg]
    """Phone number → digit-by-digit reading."""
    digits = re.sub(r"[\s\-\.]", "", m.group(0))
    return " ".join(_UNITS[int(d)] for d in digits)


def _normalize_currency(m: re.Match) -> str:  # type: ignore[type-arg]
    """50,000đ / 50.000 VNĐ → 'năm mươi nghìn đồng'."""
    raw = re.sub(r"[,\.]", "", m.group(1))
    value = int(raw)
    return _integer_to_words(value) + " đồng"


def _normalize_number(m: re.Match) -> str:  # type: ignore[type-arg]
    """Plain number (possibly with thousand separators) → words."""
    raw = re.sub(r"[,\.]", "", m.group(0))
    return _integer_to_words(int(raw))


# ── Ordered rule table ────────────────────────────────────────────────────────
# Order matters: more specific patterns must come before generic ones.

_RULES: list[tuple[re.Pattern, object]] = [
    # Date: DD/MM/YYYY
    (re.compile(r"\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})\b"), _normalize_date),
    # Time: 15h30, 15:30, 08h00
    (re.compile(r"\b(\d{1,2})[h:](\d{2})?\b"), _normalize_time),
    # Phone (10-11 digits starting with 0 or +84)
    (re.compile(r"(?<!\d)(\+84|0)[\s\-\.]?\d{2,3}[\s\-\.]?\d{3,4}[\s\-\.]?\d{3,4}(?!\d)"), _normalize_phone),
    # Currency: 50,000đ / 50.000 VNĐ / 1,500,000 đồng
    (re.compile(r"([\d]{1,3}(?:[,\.]\d{3})+)\s*(?:đ|đồng|VNĐ|VND)\b", re.IGNORECASE), _normalize_currency),
    # Large numbers with thousand separators
    (re.compile(r"\b\d{1,3}(?:[,\.]\d{3})+\b"), _normalize_number),
    # Plain integers (standalone)
    (re.compile(r"\b\d+\b"), _normalize_number),
]

# Abbreviation expansions (applied after numeric rules)
_ABBREVS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bBS\b"), "bác sĩ"),
    (re.compile(r"\bBN\b"), "bệnh nhân"),
    (re.compile(r"\bPK\b"), "phòng khám"),
    (re.compile(r"\bTP\.HCM\b", re.IGNORECASE), "Thành phố Hồ Chí Minh"),
    (re.compile(r"\bTP\b"), "thành phố"),
    (re.compile(r"\bTX\b"), "thị xã"),
    (re.compile(r"\bHN\b"), "Hà Nội"),
]


def normalize(text: str) -> str:
    """Normalize Vietnamese text for TTS — converts numbers, dates, phones, etc."""
    for pattern, handler in _RULES:
        if callable(handler):
            text = pattern.sub(handler, text)  # type: ignore[arg-type]
        else:
            text = pattern.sub(handler, text)

    for pattern, replacement in _ABBREVS:
        text = pattern.sub(replacement, text)

    # Clean up extra whitespace
    text = re.sub(r" {2,}", " ", text).strip()
    return text
