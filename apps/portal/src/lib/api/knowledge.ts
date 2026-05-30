export interface KnowledgeArticle {
  id: string
  title: string
  category: string | null
  tags: string[]
  questionVariants: string[]
  answerText: string
  answerMale: string | null
  answerFemale: string | null
  embeddingJson: string | null
  confidenceThreshold: number
  scriptId: string | null
  isActive: boolean
  createdAt: string
  updatedAt: string
}

export interface CreateArticlePayload {
  title: string
  category?: string
  tags?: string[]
  questionVariants: string[]
  answerText: string
  answerMale?: string
  answerFemale?: string
  confidenceThreshold?: number
}

export interface UpdateArticlePayload extends Partial<CreateArticlePayload> {
  isActive?: boolean
}

export const KB_CATEGORIES = [
  'booking',
  'schedule',
  'pricing',
  'services',
  'doctors',
  'location',
  'insurance',
  'general',
] as const

export type KbCategory = (typeof KB_CATEGORIES)[number]

export const CATEGORY_LABELS: Record<string, string> = {
  booking: 'Đặt lịch',
  schedule: 'Lịch khám',
  pricing: 'Giá dịch vụ',
  services: 'Dịch vụ',
  doctors: 'Bác sĩ',
  location: 'Địa chỉ / Đường đi',
  insurance: 'Bảo hiểm',
  general: 'Chung',
}
