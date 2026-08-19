/**
 * One-time seed: migrate hardcoded fillers + intent examples from Python code → DB.
 * Run via: ts-node apps/api/src/nlu/nlu.seed.ts
 * Or call NluService.seed() from DevModule.
 */

export const NLU_SEED_DOCS = [
  // ── Fillers ──────────────────────────────────────────────────────────────
  { type: 'filler' as const, label: 'thinking', content: 'Dạ,', meta: {} },
  { type: 'filler' as const, label: 'thinking', content: 'Vâng,', meta: {} },
  { type: 'filler' as const, label: 'thinking', content: 'À,', meta: {} },
  { type: 'filler' as const, label: 'thinking', content: 'Ừm,', meta: {} },
  { type: 'filler' as const, label: 'ack', content: 'Dạ vâng ạ.', meta: {} },
  { type: 'filler' as const, label: 'ack', content: 'Được ạ.', meta: {} },
  { type: 'filler' as const, label: 'ack', content: 'Vâng ạ.', meta: {} },
  { type: 'filler' as const, label: 'ack', content: 'Dạ em hiểu ạ.', meta: {} },
  { type: 'filler' as const, label: 'wait', content: 'Dạ, anh chị giữ máy giúp em một chút ạ.', meta: {} },
  { type: 'filler' as const, label: 'wait', content: 'Dạ, để em kiểm tra cho mình ạ.', meta: {} },
  { type: 'filler' as const, label: 'wait', content: 'Em xem ngay ạ.', meta: {} },
  { type: 'filler' as const, label: 'checking', content: 'Dạ, anh chị giữ máy giúp em, để em kiểm tra lịch cho mình ạ.', meta: {} },
  { type: 'filler' as const, label: 'checking', content: 'Vâng, em kiểm tra ngay ạ.', meta: {} },
  { type: 'filler' as const, label: 'checking', content: 'Để em xem lịch trong hệ thống nhé.', meta: {} },
  { type: 'filler' as const, label: 'confirming', content: 'Dạ, em nhận thông tin rồi ạ, em xin xác nhận lại.', meta: {} },
  { type: 'filler' as const, label: 'confirming', content: 'Vâng, để em xác nhận lại thông tin ạ.', meta: {} },
  { type: 'filler' as const, label: 'confirming', content: 'Dạ, để em đặt lịch cho anh chị ạ.', meta: {} },
  { type: 'filler' as const, label: 'ack_slot', content: 'Vâng, {value} ạ.', meta: {} },
  { type: 'filler' as const, label: 'ack_slot', content: 'Dạ, {value} ạ.', meta: {} },
  { type: 'filler' as const, label: 'ack_slot', content: 'À, {value} ạ.', meta: {} },

  // ── Intent examples: book_appointment ────────────────────────────────────
  { type: 'intent' as const, label: 'book_appointment', content: 'muốn đặt lịch khám', meta: {} },
  { type: 'intent' as const, label: 'book_appointment', content: 'tôi muốn khám bệnh', meta: {} },
  { type: 'intent' as const, label: 'book_appointment', content: 'đặt hẹn khám', meta: {} },
  { type: 'intent' as const, label: 'book_appointment', content: 'đăng ký khám', meta: {} },
  { type: 'intent' as const, label: 'book_appointment', content: 'cho tôi đặt lịch', meta: {} },
  { type: 'intent' as const, label: 'book_appointment', content: 'tôi cần khám bác sĩ', meta: {} },
  { type: 'intent' as const, label: 'book_appointment', content: 'book lịch khám', meta: {} },
  { type: 'intent' as const, label: 'book_appointment', content: 'muốn gặp bác sĩ', meta: {} },
  { type: 'intent' as const, label: 'book_appointment', content: 'xin đặt khám', meta: {} },
  { type: 'intent' as const, label: 'book_appointment', content: 'muốn khám tim mạch', meta: { slots: { specialty: 'Tim mạch' } } },
  { type: 'intent' as const, label: 'book_appointment', content: 'muốn khám da liễu', meta: { slots: { specialty: 'Da liễu' } } },
  { type: 'intent' as const, label: 'book_appointment', content: 'muốn khám nhi', meta: { slots: { specialty: 'Nhi khoa' } } },
  { type: 'intent' as const, label: 'book_appointment', content: 'muốn nội soi dạ dày', meta: { slots: { specialty: 'Nội soi - Tiêu hóa' } } },
  { type: 'intent' as const, label: 'book_appointment', content: 'khám tổng quát', meta: { slots: { specialty: 'Khám tổng quát' } } },

  // ── Intent examples: confirm ─────────────────────────────────────────────
  { type: 'intent' as const, label: 'confirm', content: 'đúng rồi', meta: {} },
  { type: 'intent' as const, label: 'confirm', content: 'vâng', meta: {} },
  { type: 'intent' as const, label: 'confirm', content: 'dạ', meta: {} },
  { type: 'intent' as const, label: 'confirm', content: 'đúng', meta: {} },
  { type: 'intent' as const, label: 'confirm', content: 'ừ', meta: {} },
  { type: 'intent' as const, label: 'confirm', content: 'okay', meta: {} },
  { type: 'intent' as const, label: 'confirm', content: 'được', meta: {} },
  { type: 'intent' as const, label: 'confirm', content: 'chính xác', meta: {} },
  { type: 'intent' as const, label: 'confirm', content: 'đúng vậy', meta: {} },
  { type: 'intent' as const, label: 'confirm', content: 'yes', meta: {} },

  // ── Intent examples: deny ────────────────────────────────────────────────
  { type: 'intent' as const, label: 'deny', content: 'không', meta: {} },
  { type: 'intent' as const, label: 'deny', content: 'không phải', meta: {} },
  { type: 'intent' as const, label: 'deny', content: 'sai rồi', meta: {} },
  { type: 'intent' as const, label: 'deny', content: 'không đúng', meta: {} },
  { type: 'intent' as const, label: 'deny', content: 'không phải vậy', meta: {} },
  { type: 'intent' as const, label: 'deny', content: 'thay đổi', meta: {} },
  { type: 'intent' as const, label: 'deny', content: 'không muốn', meta: {} },
  { type: 'intent' as const, label: 'deny', content: 'no', meta: {} },

  // ── Intent examples: cancel ──────────────────────────────────────────────
  { type: 'intent' as const, label: 'cancel', content: 'hủy lịch', meta: {} },
  { type: 'intent' as const, label: 'cancel', content: 'muốn hủy', meta: {} },
  { type: 'intent' as const, label: 'cancel', content: 'không đi khám nữa', meta: {} },
  { type: 'intent' as const, label: 'cancel', content: 'thôi không khám', meta: {} },
  { type: 'intent' as const, label: 'cancel', content: 'hủy đặt lịch', meta: {} },

  // ── Intent examples: service_inquiry ─────────────────────────────────────
  { type: 'intent' as const, label: 'service_inquiry', content: 'giá khám bao nhiêu', meta: {} },
  { type: 'intent' as const, label: 'service_inquiry', content: 'chi phí khám', meta: {} },
  { type: 'intent' as const, label: 'service_inquiry', content: 'cần chuẩn bị gì', meta: {} },
  { type: 'intent' as const, label: 'service_inquiry', content: 'cần nhịn ăn không', meta: {} },
  { type: 'intent' as const, label: 'service_inquiry', content: 'thủ tục khám như thế nào', meta: {} },
  { type: 'intent' as const, label: 'service_inquiry', content: 'có nhận bảo hiểm không', meta: {} },

  // ── Intent examples: check_availability ──────────────────────────────────
  { type: 'intent' as const, label: 'check_availability', content: 'hôm nay còn giờ nào trống', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'còn lịch không', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'còn chỗ không', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'giờ nào còn trống', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'hôm nay được không', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'sáng hay chiều còn giờ', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'lịch khám còn không', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'có thể khám hôm nay không', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'còn nhận khám không', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'mấy giờ còn trống', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'buổi chiều còn không', meta: {} },
  { type: 'intent' as const, label: 'check_availability', content: 'buổi sáng còn chỗ không', meta: {} },

  // ── Intent examples: goodbye ──────────────────────────────────────────────
  { type: 'intent' as const, label: 'goodbye', content: 'không cần gì thêm', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'thôi cảm ơn em', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'không em anh cảm ơn', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'không cần hỗ trợ gì thêm', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'cảm ơn em rồi', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'vậy thôi cảm ơn', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'không cần đâu cảm ơn', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'thôi không cần nữa', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'okay cảm ơn nhé', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'bye bye', meta: {} },
  { type: 'intent' as const, label: 'goodbye', content: 'tạm biệt', meta: {} },

  // ── Intent examples: symptom_described ───────────────────────────────────
  { type: 'intent' as const, label: 'symptom_described', content: 'bị đau dạ dày', meta: {} },
  { type: 'intent' as const, label: 'symptom_described', content: 'tôi bị ho kéo dài', meta: {} },
  { type: 'intent' as const, label: 'symptom_described', content: 'hay bị chóng mặt', meta: {} },
  { type: 'intent' as const, label: 'symptom_described', content: 'tim đập loạn', meta: {} },
  { type: 'intent' as const, label: 'symptom_described', content: 'mệt mỏi không biết vì sao', meta: {} },
  { type: 'intent' as const, label: 'symptom_described', content: 'con tôi bị sốt', meta: {} },
  { type: 'intent' as const, label: 'symptom_described', content: 'bị đau lưng', meta: {} },
  { type: 'intent' as const, label: 'symptom_described', content: 'khó thở khi leo cầu thang', meta: {} },
]
