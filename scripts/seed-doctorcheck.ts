/**
 * DoctorCheck seed script — wipes existing data and seeds fresh from doctorcheck.vn data.
 *
 * Usage:
 *   SEED_PASSWORD=Admin@2024! npx ts-node scripts/seed-doctorcheck.ts
 *
 * Optional env vars:
 *   API_URL          — default: http://localhost:3001
 *   SEED_EMAIL       — default: admin@doctorcheck.vn
 *   SEED_PASSWORD    — required
 *   VOICE_WORKER_URL — default: http://localhost:8000
 *   TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID — for escalation config
 */

import { CAMPAIGN_DEF, KB_ARTICLES, NLU_DOCS } from './data/doctorcheck-seed'

const API_URL = process.env['API_URL'] ?? 'http://localhost:3001'
const VOICE_WORKER_URL = process.env['VOICE_WORKER_URL'] ?? 'http://localhost:8000'
const SEED_EMAIL = process.env['SEED_EMAIL'] ?? 'admin@doctorcheck.vn'
const SEED_PASSWORD = process.env['SEED_PASSWORD']

if (!SEED_PASSWORD) {
  console.error('❌  SEED_PASSWORD env var is required')
  process.exit(1)
}

async function apiPost(path: string, body: unknown, token?: string) {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) headers['Authorization'] = `Bearer ${token}`
  const res = await fetch(`${API_URL}/api/v1${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`POST ${path} → ${res.status}: ${text.slice(0, 200)}`)
  }
  return res.json()
}

async function workerPost(path: string) {
  const res = await fetch(`${VOICE_WORKER_URL}${path}`, { method: 'POST' })
  if (!res.ok) throw new Error(`Worker POST ${path} → ${res.status}`)
  return res.json()
}

async function main() {
  console.log(`\n🔧  DoctorCheck seed script`)
  console.log(`    API: ${API_URL}`)
  console.log(`    Worker: ${VOICE_WORKER_URL}\n`)

  // 1. Login
  process.stdout.write('1. Logging in as admin... ')
  const loginRes = await apiPost('/auth/login', { email: SEED_EMAIL, password: SEED_PASSWORD }) as { accessToken: string }
  const token = loginRes.accessToken
  console.log('✓')

  // 2. Wipe
  process.stdout.write('2. Wiping existing data... ')
  const wipeRes = await apiPost('/dev/wipe', {}, token) as { wiped: Record<string, number> }
  const w = wipeRes.wiped
  console.log(`✓ (${w.campaigns} campaigns, ${w.scriptVersions} versions, ${w.knowledgeArticles} KB, ${w.nluDocuments} NLU)`)

  // 3. Create campaign
  process.stdout.write('3. Creating campaign... ')
  const campaign = await apiPost('/scripts', {
    name: CAMPAIGN_DEF.name,
    direction: CAMPAIGN_DEF.direction,
    voiceProfile: CAMPAIGN_DEF.voiceProfile,
  }, token) as { id: string; name: string }
  console.log(`✓ id=${campaign.id}`)

  // 4. Create script version
  process.stdout.write('4. Creating script version 1.0.0... ')
  await apiPost(`/scripts/${campaign.id}/versions`, {
    version: CAMPAIGN_DEF.scriptVersion,
    body: CAMPAIGN_DEF.scriptBody,
  }, token)
  console.log('✓')

  // 5. Submit for review
  process.stdout.write('5. Submitting for review... ')
  await apiPost(`/scripts/${campaign.id}/versions/${CAMPAIGN_DEF.scriptVersion}/submit-review`, {}, token)
  console.log('✓')

  // 6. Publish
  process.stdout.write('6. Publishing script... ')
  await apiPost(`/scripts/${campaign.id}/versions/${CAMPAIGN_DEF.scriptVersion}/publish`, {}, token)
  console.log('✓')

  // 7. Create KB articles
  console.log(`7. Creating ${KB_ARTICLES.length} KB articles...`)
  let kbOk = 0
  for (const article of KB_ARTICLES) {
    try {
      await apiPost('/knowledge', { ...article, scriptId: campaign.id }, token)
      kbOk++
      process.stdout.write('.')
    } catch (e) {
      process.stdout.write('✗')
      console.error(`\n   ❌ KB "${article.title}": ${(e as Error).message}`)
    }
  }
  console.log(`\n   ✓ ${kbOk}/${KB_ARTICLES.length} articles created`)

  // 8. Create NLU docs
  console.log(`8. Creating ${NLU_DOCS.length} NLU documents...`)
  let nluOk = 0
  for (const doc of NLU_DOCS) {
    try {
      await apiPost('/nlu/documents', { ...doc, campaignId: campaign.id }, token)
      nluOk++
      process.stdout.write('.')
    } catch (e) {
      process.stdout.write('✗')
      console.error(`\n   ❌ NLU "${doc.label}/${doc.content.slice(0, 30)}": ${(e as Error).message}`)
    }
  }
  console.log(`\n   ✓ ${nluOk}/${NLU_DOCS.length} NLU docs created`)

  // 9. Reload voice worker
  process.stdout.write('9. Reloading voice worker KB... ')
  try {
    const ragRes = await workerPost('/rag/reload') as { count: number }
    process.stdout.write(`${ragRes.count} articles. `)
  } catch (e) {
    process.stdout.write(`⚠ skipped (${(e as Error).message.slice(0, 50)}) `)
  }
  process.stdout.write('NLU... ')
  try {
    const nluRes = await workerPost('/nlu/reload') as { count: number }
    console.log(`${nluRes.count} docs. ✓`)
  } catch (e) {
    console.log(`⚠ skipped (${(e as Error).message.slice(0, 50)})`)
  }

  console.log(`
✅  Seed complete!
    Campaign: "${campaign.name}" (id: ${campaign.id})
    Script:   version ${CAMPAIGN_DEF.scriptVersion} — published
    KB:       ${kbOk} articles (scriptId = campaign id)
    NLU:      ${nluOk} documents (campaignId = campaign id)

💡  Next: Open Portal → Scripts to verify, then test a call.
`)
}

main().catch((err) => {
  console.error('\n❌ Seed failed:', err.message)
  process.exit(1)
})
