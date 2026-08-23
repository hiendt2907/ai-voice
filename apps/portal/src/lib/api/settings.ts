// Hàm fetchCloudFoneSettings() đã bị xoá: xác nhận bằng grep toàn bộ src/ không còn nơi nào
// gọi hàm này — settings/CloudFoneSection.tsx tự định nghĩa interface CloudFoneSettings riêng
// và gọi API qua route handler khác, không dùng file này. Code chết hoàn toàn.
// Type dưới đây không còn được import ở đâu nữa nhưng giữ lại phòng khi cần dùng lại API base
// này trong tương lai — không có rủi ro vỡ build vì export type không dùng vẫn hợp lệ.

export interface CloudFoneSettings {
  id: string
  odsUrl: string
  apiKey: string
  tenantId: string
  updatedBy: string | null
  updatedAt: string
}
