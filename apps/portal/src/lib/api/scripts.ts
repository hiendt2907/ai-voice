// Các hàm gọi API (listCampaigns, getCampaign, listVersions, validateScript) đã bị xoá:
// xác nhận bằng grep toàn bộ src/ không còn nơi nào import/gọi chúng — code chết hoàn toàn.
// Các type/interface dưới đây vẫn được import trực tiếp ở nhiều trang scripts/*, giữ nguyên.

export interface Campaign {
  id: string
  name: string
  direction: 'inbound' | 'outbound'
  voiceProfile: string
  isActive: boolean
  interceptionMode: 'shadow' | 'medium' | 'full'
  interceptionDomains: string[]
  versions?: ScriptVersion[]
  createdAt: string
  updatedAt: string
}

export type VersionStatus = 'draft' | 'under_review' | 'published' | 'archived'

export interface ScriptVersion {
  id: string
  campaignId: string
  version: string
  body: Record<string, unknown>
  status: VersionStatus
  reviewNote: string | null
  createdBy: string | null
  publishedAt: string | null
  createdAt: string
  updatedAt: string
}

export interface LintError {
  code: string
  message: string
  severity: 'error' | 'warning'
  field?: string
}

export interface LintResult {
  valid: boolean
  errors: LintError[]
  warnings: LintError[]
}
