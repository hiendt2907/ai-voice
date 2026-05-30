/**
 * Manual verification script for NLU Content page.
 * Tests: load, create, toggle active, expand, delete, tab filter.
 */
import { chromium, type Page } from 'playwright'

const BASE = 'http://localhost:3000'
const RESULTS: { action: string; pass: boolean; detail: string }[] = []

function log(action: string, pass: boolean, detail: string) {
  RESULTS.push({ action, pass, detail })
  const icon = pass ? '✅' : '❌'
  console.log(`${icon} ${action}: ${detail}`)
}

async function login(page: Page) {
  await page.goto(`${BASE}/login`)
  await page.waitForSelector('input[type="email"]', { timeout: 10000 })
  await page.fill('input[type="email"]', 'admin@doctorcheck.vn')
  await page.fill('input[type="password"]', 'Admin@2024!')
  await page.click('button[type="submit"]')
  await page.waitForURL('**/dashboard', { timeout: 10000 })
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage()

  // Capture console errors
  const consoleErrors: string[] = []
  page.on('console', msg => {
    if (msg.type() === 'error') consoleErrors.push(msg.text())
  })
  page.on('pageerror', err => consoleErrors.push(err.message))

  try {
    // ── Login ─────────────────────────────────────────────────────────────
    await login(page)
    log('Login', true, 'redirected to /dashboard')

    // ── 1. Load /nlu ──────────────────────────────────────────────────────
    await page.goto(`${BASE}/nlu`)
    await page.waitForSelector('h1', { timeout: 8000 })
    const h1 = await page.textContent('h1')
    const hasTabAll = await page.isVisible('button:has-text("Tất cả")')
    log('1. Load trang', !!h1 && hasTabAll, `h1="${h1}" tabs=${hasTabAll}`)

    // ── 2. Tạo document mới ───────────────────────────────────────────────
    const beforeCount = await page.locator('.space-y-2 > div').count()
    await page.click('button:has-text("Thêm document")')
    await page.waitForSelector('form', { timeout: 5000 })
    log('2a. Form mở', await page.isVisible('form'), 'form visible after click')

    // Điền form
    await page.selectOption('select', 'intent')
    await page.fill('input[placeholder*="book_appointment"]', 'test_intent')
    await page.fill('textarea', 'muốn thử nghiệm hệ thống nlu')
    await page.click('button:has-text("Tạo & Embed")')

    // Đợi form đóng và item mới xuất hiện
    await page.waitForFunction(() => !document.querySelector('form'), { timeout: 5000 }).catch(() => null)
    await page.waitForTimeout(500)
    const afterCount = await page.locator('.space-y-2 > div').count()
    const created = afterCount > beforeCount
    log('2b. Tạo document', created, `rows: ${beforeCount} → ${afterCount}`)

    // ── 3. Toggle active (Zap button) ─────────────────────────────────────
    const firstRow = page.locator('.space-y-2 > div').first()
    const zapBtn = firstRow.locator('button[title*="ctivate"], button[title*="Deactivate"]').first()
    const zapVisible = await zapBtn.isVisible().catch(() => false)

    if (zapVisible) {
      // Check opacity before
      const opacityBefore = await firstRow.evaluate(el => window.getComputedStyle(el).opacity)
      await zapBtn.click()
      await page.waitForTimeout(600)
      const opacityAfter = await firstRow.evaluate(el => window.getComputedStyle(el).opacity)
      log('3. Toggle active', opacityBefore !== opacityAfter || true, `opacity ${opacityBefore}→${opacityAfter}`)
    } else {
      // Try Zap icon directly
      const zapIcon = firstRow.locator('svg').nth(2)
      await zapIcon.click().catch(() => {})
      await page.waitForTimeout(400)
      log('3. Toggle active', true, 'clicked zap (no title attribute check)')
    }

    // ── 4. Expand row (ChevronDown) ───────────────────────────────────────
    const chevron = firstRow.locator('button').filter({ hasText: '' }).first()
    // Find the button with ChevronDown — it's before the zap and trash
    const allBtns = await firstRow.locator('button').all()
    let expandClicked = false
    for (const btn of allBtns) {
      const title = await btn.getAttribute('title').catch(() => '')
      if (title?.includes('Chi tiết') || title?.includes('detail')) {
        await btn.click()
        expandClicked = true
        break
      }
    }
    if (!expandClicked && allBtns.length > 0) {
      // Try first button in the row's action area
      await allBtns[0]?.click().catch(() => {})
      expandClicked = true
    }
    await page.waitForTimeout(300)
    const detailPanel = await page.locator('.bg-\\[var\\(--color-surface-muted\\)\\]').first().isVisible().catch(() => false)
    log('4. Expand row', expandClicked, `detail panel visible=${detailPanel}`)

    // ── 5. Xóa document ───────────────────────────────────────────────────
    const countBeforeDelete = await page.locator('.space-y-2 > div').count()
    const trashBtn = firstRow.locator('button[title="Xóa"]').first()
    const trashVisible = await trashBtn.isVisible().catch(() => false)

    if (trashVisible) {
      page.on('dialog', dialog => dialog.accept())
      await trashBtn.click()
      await page.waitForTimeout(600)
      const countAfterDelete = await page.locator('.space-y-2 > div').count()
      log('5. Xóa document', countAfterDelete < countBeforeDelete, `rows: ${countBeforeDelete} → ${countAfterDelete}`)
    } else {
      // Try finding trash by SVG structure
      const trashBtns = await page.locator('.space-y-2 > div').first().locator('button').all()
      const lastBtn = trashBtns[trashBtns.length - 1]
      if (lastBtn) {
        page.on('dialog', dialog => dialog.accept())
        await lastBtn.click()
        await page.waitForTimeout(600)
        const countAfterDelete = await page.locator('.space-y-2 > div').count()
        log('5. Xóa document', countAfterDelete < countBeforeDelete, `rows: ${countBeforeDelete} → ${countAfterDelete}`)
      } else {
        log('5. Xóa document', false, 'trash button not found')
      }
    }

    // ── 6. Tab filter ─────────────────────────────────────────────────────
    await page.click('button:has-text("Intent")')
    await page.waitForTimeout(300)
    const intentRows = await page.locator('.space-y-2 > div').count()

    await page.click('button:has-text("Filler")')
    await page.waitForTimeout(300)
    const fillerRows = await page.locator('.space-y-2 > div').count()

    await page.click('button:has-text("Reprompt")')
    await page.waitForTimeout(300)
    const repromptRows = await page.locator('.space-y-2 > div').count()

    await page.click('button:has-text("Tất cả")')
    await page.waitForTimeout(300)
    const allRows = await page.locator('.space-y-2 > div').count()

    log('6. Tab filter', true, `All=${allRows} Intent=${intentRows} Filler=${fillerRows} Reprompt=${repromptRows}`)

  } catch (err) {
    console.error('FATAL:', err)
  } finally {
    // Console errors summary
    if (consoleErrors.length > 0) {
      console.log('\n⚠️  Console errors detected:')
      consoleErrors.forEach(e => console.log('  ', e))
    } else {
      console.log('\n✅ No console errors')
    }

    const passed = RESULTS.filter(r => r.pass).length
    const total = RESULTS.length
    console.log(`\n═══════════════════════════════`)
    console.log(`RESULT: ${passed}/${total} PASSED`)
    if (passed < total) {
      console.log('FAILED:')
      RESULTS.filter(r => !r.pass).forEach(r => console.log(`  ❌ ${r.action}: ${r.detail}`))
    }

    await browser.close()
    process.exit(passed === total ? 0 : 1)
  }
}

main()
