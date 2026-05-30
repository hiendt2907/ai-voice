export type NluDocType = 'intent' | 'filler' | 'reprompt' | 'dialog_node'

export interface NluDocument {
  id: string
  type: NluDocType
  label: string
  content: string
  meta: Record<string, unknown>
  embeddingJson: string | null
  campaignId: string | null
  scriptId: string | null
  isActive: boolean
  createdAt: string
  updatedAt: string
}

export const TYPE_LABELS: Record<NluDocType, string> = {
  intent: 'Intent Example',
  filler: 'Filler Phrase',
  reprompt: 'Reprompt',
  dialog_node: 'Dialog Node',
}

export const TYPE_DESCRIPTIONS: Record<NluDocType, string> = {
  intent: 'Câu ví dụ cho một intent — dùng để vector search phân loại ý định',
  filler: 'Câu filler ngắn phát ngay sau khi nhận được tiếng — giảm độ trễ cảm nhận',
  reprompt: 'Câu hỏi lại khi user không trả lời đúng slot yêu cầu',
  dialog_node: 'Mô tả trigger context của một dialog step trong script',
}

export const FILLER_CONTEXTS = ['thinking', 'ack', 'wait', 'checking', 'confirming', 'ack_slot']
