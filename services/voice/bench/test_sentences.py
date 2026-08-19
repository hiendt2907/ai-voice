"""Vietnamese TTS bake-off test corpus (Phase 0, task G.4).

Sentences 1–10 are taken verbatim from the production booking script
`scripts/examples/booking_inbound_v1.json` (template slots filled with
realistic values). Sentences 11–18 are stress cases targeting the D3 rubric:
tone minimal pairs, numerals/irregulars (mốt / lăm / lẻ), dates, times,
currency, phone numbers, Vietnamese proper nouns and embedded English.

Each entry: (id, category, text).
`category` is used only for grouping in the report and the sample INDEX.
"""

from __future__ import annotations

SENTENCES: list[tuple[str, str, str]] = [
    # ---- verbatim from booking_inbound_v1.json (agent-spoken beats) ----
    ("s01", "script", "Dạ, Doctor Check xin nghe ạ. Em có thể hỗ trợ gì cho anh chị ạ?"),
    ("s02", "script", "Dạ anh chị muốn đặt lịch khám hay cần hỗ trợ gì ạ?"),
    ("s03", "script", "Dạ em có thể hỗ trợ đặt lịch khám, hoặc trả lời thắc mắc về dịch vụ ạ."),
    ("s04", "script", "Anh chị có thể nói ví dụ: tám giờ sáng, hoặc ba giờ chiều ạ."),
    ("s05", "script", "Dạ, anh chị giữ máy giúp em, để em kiểm tra chính xác giờ cho mình ạ."),
    (
        "s06",
        "script",
        "Dạ, hiện tại chín giờ ba mươi sáng ngày hai mươi lăm tháng mười hai "
        "phòng khám vẫn còn trống lịch ạ, em đặt luôn cho mình nhé?",
    ),
    (
        "s07",
        "script",
        "Dạ, em nhận thông tin rồi ạ, em xin xác nhận lại. "
        "Anh chị Nguyễn Văn Bảy, số điện thoại 0903 456 789, "
        "đặt lịch khám vào chín giờ sáng ngày mười lăm tháng mười một.",
    ),
    (
        "s08",
        "script",
        "Dạ, em đặt lịch cho mình xong rồi ạ. Phòng khám sẽ nhắn tin xác nhận "
        "lịch hẹn tới số 0903 456 789 trước ngày khám ạ.",
    ),
    (
        "s09",
        "script",
        "Dạ, em cảm ơn anh chị. Doctor Check rất vui được tiếp đón anh chị "
        "vào buổi sáng ngày mai ạ. Chúc anh chị sức khỏe ạ.",
    ),
    (
        "s10",
        "script",
        "Dạ để tra cứu kết quả xét nghiệm, em xin phép chuyển anh chị sang "
        "nhân viên chuyên trách ạ. Anh chị vui lòng giữ máy giây lát ạ.",
    ),
    # ---- stress: numerals, dates, currency, phone ----
    (
        "s11",
        "numbers",
        "Anh Nguyễn Văn Bảy có lịch khám lúc 9 giờ 30 sáng ngày 25 tháng 12.",
    ),
    (
        "s12",
        "numbers",
        "Số điện thoại của chị là không chín không ba, bốn năm sáu, bảy tám chín.",
    ),
    (
        "s13",
        "numbers",
        "Tổng chi phí gói khám là 1.250.000 đồng, đã bao gồm phí xét nghiệm ạ.",
    ),
    (
        "s14",
        "numbers",
        "Lịch trống còn thứ Ba ngày 15 tháng 11, lúc 8 giờ 15 và 10 giờ 45 ạ.",
    ),
    (
        "s15",
        "numbers",
        "Hai mươi mốt, hai mươi lăm, một trăm lẻ một, một nghìn không trăm ba mươi tư.",
    ),
    # ---- stress: tones / minimal pairs / final consonants ----
    (
        "s16",
        "tones",
        "Mốt hay một, sáu hay sáo, chín hay chin, ngã hay ngả, hỏi hay hỏng ạ?",
    ),
    (
        "s17",
        "tones",
        "Bác sĩ Lê Thị Hoài Mỹ khám tại phòng khám Quận Phú Nhuận, "
        "đường Nguyễn Văn Trỗi, thành phố Hồ Chí Minh.",
    ),
    # ---- stress: embedded English / loanwords ----
    (
        "s18",
        "loanword",
        "Anh chị vui lòng check-in tại quầy lễ tân, chọn combo tầm soát "
        "Doctor Check Premium, rồi scan mã QR ạ.",
    ),
]
