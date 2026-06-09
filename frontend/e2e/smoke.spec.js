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
 */

import { test, expect } from '@playwright/test'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const TURN_TIMEOUT    = 120_000   // 2 min to see first 2 turns
const BATTLE_TIMEOUT  = 300_000   // 5 min for winner banner

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
  // ── 1. Load home page ──────────────────────────────────────────────────

  await page.goto('/')
  await expect(page.locator('.leaderboard-panel, .battle-form, .form-tabs')).toBeVisible()

  // ── 2. Ensure BATTLE tab is active ─────────────────────────────────────

  const battleTab = page.locator('.form-tab', { hasText: 'BATTLE' })
  if (await battleTab.isVisible()) {
    await battleTab.click()
  }

  // ── 3. Wait for LM Studio models to auto-populate both selectors ────────
  //    The BattleForm effect auto-fills p1_model / p2_model with the first
  //    two loaded models; we just wait for the dropdowns to be non-empty.

  await waitForModelsLoaded(page)

  // Log the chosen models for debugging
  const p1Model = await page.locator('.model-selector .model-select').nth(0).inputValue()
  const p2Model = await page.locator('.model-selector .model-select').nth(1).inputValue()
  console.log(`  P1: ${p1Model}`)
  console.log(`  P2: ${p2Model}`)

  // ── 4. Start the battle ─────────────────────────────────────────────────

  await page.locator('.btn-start').first().click()

  // The app transitions to the battle view — wait for the battlefield root
  await expect(page.locator('.battlefield-wrapper')).toBeVisible({ timeout: 15_000 })

  // ── 5. Wait for at least 2 turn log entries (battle is progressing) ─────

  await expect(page.locator('.log-entry.turn-event').nth(1))
    .toBeVisible({ timeout: TURN_TIMEOUT })

  // Check we have turn numbers rendered
  const firstTurnNum = page.locator('.log-turn-num').first()
  await expect(firstTurnNum).toBeVisible()
  const turnText = await firstTurnNum.textContent()
  expect(turnText).toMatch(/T\d+/)

  // ── 6. Wait for the battle to finish ────────────────────────────────────

  await expect(page.locator('.winner-banner')).toBeVisible({ timeout: BATTLE_TIMEOUT })

  // ── 7. Assert winner banner content ─────────────────────────────────────

  await expect(page.locator('.winner-label')).toContainText('BATTLE COMPLETE')

  // ── 8. Open replay ──────────────────────────────────────────────────────

  const replayBtn = page.locator('.btn-replay').first()
  await expect(replayBtn).toBeVisible()
  await replayBtn.click()

  // ── 9. Replay shows turn entries ─────────────────────────────────────────

  await expect(page.locator('.log-entry.turn-event').first())
    .toBeVisible({ timeout: 10_000 })
})
