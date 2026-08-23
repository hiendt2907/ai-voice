/**
 * Tiện ích dùng chung để che (mask) dữ liệu cá nhân (PII) trước khi ghi vào
 * bất kỳ nơi nào có thể bị đọc lại sau này — DB (audit_events, call_sessions),
 * log ứng dụng, v.v.
 *
 * Bất biến bắt buộc (xem CLAUDE.md mục "Bất biến quan trọng"):
 *   "PII masking: Mask SĐT trong audit log và transcript"
 *
 * Trước đây `maskPhone()` là hàm private bên trong `calls.service.ts` nên
 * các module khác (vd. voip24h) không dùng lại được và vô tình ghi SĐT thô
 * vào audit log. Tách ra đây để toàn bộ apps/api dùng chung một bản duy nhất.
 */

/**
 * Che một số điện thoại, chỉ giữ lại 3 số đầu và 3 số cuối.
 * Ví dụ: "0901234567" → "090****567"
 *
 * @param phone Số điện thoại thô (có thể còn khoảng trắng/dấu gạch ngang)
 * @returns Số điện thoại đã che, chỉ gồm chữ số và ký tự '*'
 */
export function maskPhone(phone: string): string {
  const digits = phone.replace(/\D/g, '')
  if (digits.length <= 4) return '*'.repeat(digits.length)
  return digits.slice(0, 3) + '*'.repeat(digits.length - 6) + digits.slice(-3)
}
