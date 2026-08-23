import type { CallStatus } from '../call-session.entity'

/**
 * Danh sách các giá trị `status` hợp lệ khi lọc call session.
 * Dùng chung cho `ParseEnumPipe` ở controller và cho tài liệu Swagger,
 * để tránh lệch nhau giữa nơi validate và nơi document.
 */
export const CALL_STATUS_VALUES: readonly CallStatus[] = [
  'active',
  'completed',
  'handoff',
  'error',
] as const
