/**
 * E2E smoke test — full single battle with live LM Studio models.
 *
 * Prerequisites (must be running before executing this suite):
 *   • Pokémon Showdown  →  localhost:8000
 *   • Nidozo API        →  localhost:5001
 *   • Vite dev server   →  localhost:5173  (npm run dev in frontend/)
 *   • LM Studio         →  localhost:1234  (with at least 2 models loaded)
 *
 * Run:
 *   cd frontend && npx playwright test
 *   (or: npm run test:e2e)
 *
 * Design: after confirming 5 turns have progressed the test cancels the
 * battle rather than waiting for natural completion.  Gen3 random battles
 * can stall for 30+ minutes with certain matchups; cancelling after turn 5
 * keeps the suite under ~3 minutes regardless of team assignments while
 * still exercising the full pipeline (WS events, UI rendering, replay).
 */

import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TURN_TIMEOUT   = 180_000   // 3 min to see 5 turns (model inference can be slow)

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Wait for both model-select dropdowns in the battle form to have a value. */
async function waitForModelsLoaded(page) {
  await page.waitForFunction(() => {
    const selects = document.querySelectorAll('.model-selector .model-select')
    return selects.length >= 2 &&
      selects[0].value !== '' && selects[0].value !== 'select model…' &&
      selects[1].value !== '' && selects[1].value !== 'select model…'
  }, { timeout: 20_000 })
}

// ---------------------------------------------------------------------------
// Smoke test
// ---------------------------------------------------------------------------

test('full battle smoke test', async ({ page }) => {
  page.on('pageerror', err => console.error('  [pageerror]', err.message))

  // ── 1. Load home page ──────────────────────────────────────────────────

  await page.goto('/')
  await expect(page.locator('.leaderboard-panel, .battle-form, .form-tabs')).toBeVisible()

  // ── 2. Ensure BATTLE tab is active ─────────────────────────────────────

  const battleTab = page.locator('.form-tab', { hasText: 'BATTLE' })
  if (await battleTab.isVisible()) {
    await battleTab.click()
  }

  // ── 3. Wait for LM Studio models to auto-populate both selectors ────────
  //    BattleForm auto-fills p1/p2 with the first two loaded LM Studio models.

  await waitForModelsLoaded(page)

  const p1Model = await page.locator('.model-selector .model-select').nth(0).inputValue()
  const p2Model = await page.locator('.model-selector .model-select').nth(1).inputValue()
  console.log(`  P1: ${p1Model}`)
  console.log(`  P2: ${p2Model}`)

  // ── 4. Start the battle ─────────────────────────────────────────────────

  let startResponse = null
  page.once('response', async res => {
    if (res.url().includes('/api/battles/start')) {
      startResponse = { status: res.status(), body: await res.text().catch(() => '(unreadable)') }
    }
  })

  await page.locator('.btn-start').first().click()
  await page.waitForTimeout(3_000)

  if (startResponse) {
    console.log(`  POST /api/battles/start → ${startResponse.status}: ${startResponse.body.slice(0, 200)}`)
  } else {
    console.log('  POST /api/battles/start — no response captured')
  }

  // App transitions to battle view
  await expect(page.locator('.battlefield-wrapper')).toBeVisible({ timeout: 15_000 })

  // ── 5. Wait for 5 turn log entries (pipeline is confirmed working) ───────

  await expect(page.locator('.log-entry.turn-event').nth(4))
    .toBeVisible({ timeout: TURN_TIMEOUT })

  const firstTurnNum = page.locator('.log-turn-num').first()
  await expect(firstTurnNum).toBeVisible()
  const turnText = await firstTurnNum.textContent()
  expect(turnText).toMatch(/T\d+/)
  console.log(`  Reached turn: ${turnText}`)

  // ── 6. Cancel the battle ─────────────────────────────────────────────────
  //    Using cancel instead of waiting for natural completion avoids stall
  //    matchups (e.g. Skarmory Toxic-stall) running for 30+ minutes.

  const cancelBtn = page.locator('.btn-cancel-battle')
  await expect(cancelBtn).toBeVisible({ timeout: 5_000 })
  await cancelBtn.click()

  // ── 7. Wait for the result banner ────────────────────────────────────────

  await expect(page.locator('.winner-banner')).toBeVisible({ timeout: 30_000 })

  // ── 8. Assert banner content (cancelled shows "BATTLE CANCELLED") ────────

  const labelText = await page.locator('.winner-label').textContent()
  expect(['BATTLE COMPLETE', 'BATTLE CANCELLED']).toContain(labelText?.trim())
  console.log(`  Battle ended: ${labelText?.trim()}`)

  // ── 9. Open replay ──────────────────────────────────────────────────────

  const replayBtn = page.locator('.btn-replay').first()
  await expect(replayBtn).toBeVisible()
  await replayBtn.click()

  // ── 10. Replay shows turn decisions ──────────────────────────────────────
  //    BattleReplay renders "TURN N — DECISIONS" sections (.tap-title).

  await expect(page.locator('.tap-title').first())
    .toBeVisible({ timeout: 10_000 })
})
