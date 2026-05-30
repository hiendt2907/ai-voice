import { apiFetch } from './client'

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

export function listCampaigns(token?: string) {
  return apiFetch<Campaign[]>('/scripts', token ? { headers: { Authorization: `Bearer ${token}` } } : undefined)
}

export function getCampaign(id: string, token?: string) {
  return apiFetch<Campaign>(`/scripts/${id}`, token ? { headers: { Authorization: `Bearer ${token}` } } : undefined)
}

export function listVersions(campaignId: string, token?: string) {
  return apiFetch<ScriptVersion[]>(`/scripts/${campaignId}/versions`, token ? { headers: { Authorization: `Bearer ${token}` } } : undefined)
}

export function validateScript(body: Record<string, unknown>, token?: string) {
  return apiFetch<LintResult>('/scripts/validate', {
    method: 'POST',
    body: JSON.stringify({ body }),
    ...(token ? { headers: { Authorization: `Bearer ${token}` } } : {}),
  })
}
