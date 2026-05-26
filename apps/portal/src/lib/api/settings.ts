import { apiFetch } from './client'

export interface CloudFoneSettings {
  id: string
  odsUrl: string
  apiKey: string
  tenantId: string
  updatedBy: string | null
  updatedAt: string
}

export function fetchCloudFoneSettings(): Promise<CloudFoneSettings> {
  return apiFetch<CloudFoneSettings>('/settings/cloudfone')
}
