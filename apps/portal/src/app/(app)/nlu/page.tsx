import type { NluDocument, NluDocType } from '@/lib/api/nlu'
import { serverFetch } from '@/lib/api/server'
import NluClient from './NluClient'

async function fetchDocs(scriptId?: string): Promise<NluDocument[]> {
  try {
    const qs = scriptId ? `?all=true&scriptId=${scriptId}` : '?all=true'
    return await serverFetch<NluDocument[]>(`/nlu/documents${qs}`)
  } catch {
    return []
  }
}

export default async function NluPage({
  searchParams,
}: {
  searchParams: Promise<{ scriptId?: string; type?: string }>
}) {
  const sp = await searchParams
  const scriptId = sp.scriptId
  const defaultType = (sp.type as NluDocType | undefined) ?? undefined
  const docs = await fetchDocs(scriptId)
  return <NluClient initialDocs={docs} scriptId={scriptId} defaultType={defaultType} />
}

export const metadata = {
  title: 'NLU Content — DoctorCheck',
}
