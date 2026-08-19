"""Vietnamese telephony STT test set — DoctorCheck booking domain.

Each entry is a caller-side utterance that the phone agent must transcribe.
Coverage is deliberately spread across the failure modes that matter for a
booking agent (see docs/ai-streaming-voice-architecture-proposal.md §D2):

  - plain intent phrases            (intent)
  - phone numbers                   (digits)
  - dates and times                 (date / time)
  - proper names                    (name)
  - domain / medical vocabulary     (domain)
  - short confirmations             (short)  ← hardest for VAD + ASR
  - long multi-slot sentences       (long)

`text` is BOTH the TTS input and the ground truth. It is written in the exact
orthography a Vietnamese speaker would use; digits are expanded at scoring
time by `tts.text_normalizer.normalize`, so an engine that emits "0908" and an
engine that emits "không chín không tám" score identically.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Utterance:
    uid: str
    text: str
    tags: tuple[str, ...]


TEST_SET: tuple[Utterance, ...] = (
    Utterance("u01", "Dạ em muốn đặt lịch khám sức khỏe tổng quát ạ.", ("intent",)),
    Utterance("u02", "Cho anh hỏi phòng khám mình có làm việc thứ bảy không em?", ("intent",)),
    Utterance("u03", "Số điện thoại của tôi là không chín không tám bốn năm sáu bảy tám chín.", ("digits",)),
    Utterance("u04", "Em cho chị đặt lịch ngày mười bảy tháng chín nhé.", ("date",)),
    Utterance("u05", "Khoảng tám giờ rưỡi sáng mai được không em?", ("time",)),
    Utterance("u06", "Tên tôi là Nguyễn Thị Thanh Huyền.", ("name",)),
    Utterance("u07", "Anh tên Trần Quốc Bảo, sinh năm một chín tám lăm.", ("name", "digits")),
    Utterance("u08", "Chị muốn nội soi dạ dày gây mê thì chuẩn bị gì ạ?", ("domain",)),
    Utterance("u09", "Gói tầm soát ung thư đại tràng giá bao nhiêu vậy em?", ("domain",)),
    Utterance("u10", "Dạ đúng rồi ạ.", ("short",)),
    Utterance("u11", "Không, chị đổi ý rồi.", ("short",)),
    Utterance("u12", "Em ơi cho anh hỏi chút.", ("short",)),
    Utterance(
        "u13",
        "Em đặt giúp chị lịch nội soi vào chiều thứ tư tuần sau, khoảng hai giờ chiều nhé.",
        ("long", "date", "time"),
    ),
    Utterance(
        "u14",
        "Anh muốn hủy lịch khám ngày mai và dời sang thứ sáu tuần này được không em?",
        ("long", "date"),
    ),
    Utterance("u15", "Chi nhánh Doctor Check ở quận mười có xét nghiệm máu không ạ?", ("domain", "name")),
    Utterance("u16", "Cho em xin kết quả xét nghiệm hôm qua với ạ.", ("intent",)),
    Utterance("u17", "Em chuyển máy cho nhân viên tư vấn giúp chị đi.", ("intent",)),
    Utterance("u18", "Số căn cước của anh là không bảy chín hai không không ba một hai ba bốn.", ("digits",)),
    Utterance("u19", "Bác sĩ Lê Minh Đức có khám vào buổi sáng không em?", ("name", "time")),
    Utterance("u20", "Dạ em ở Bình Thạnh, đường Xô Viết Nghệ Tĩnh ạ.", ("name",)),
)
