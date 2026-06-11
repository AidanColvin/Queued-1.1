import { test, expect } from '@playwright/test';

/**
 * Real headless-Chrome interaction tests. These run in CI (the dev sandbox can
 * neither download a browser nor reach the deploy), against a local static
 * export + the sample-bundle backend.
 *
 * They drive the actual UI: load the deck, perform a swipe via the action bar
 * (same code path as a drag → decide() → /swipe), and check the standalone
 * pages render.
 */

// Skip the first-visit WelcomeGate before any page script runs so we land
// straight on the deck.
test.beforeEach(async ({ context }) => {
  await context.addInitScript(() => {
    try {
      localStorage.setItem('queued:welcomed', '1');
    } catch {
      /* storage unavailable */
    }
  });
});

test('deck loads a real card and a swipe advances to a new one', async ({ page }) => {
  await page.goto('/');

  // The splash is decorative and clears itself; the card appears once the
  // backend returns the first batch.
  const card = page.getByTestId('swipe-card').first();
  await expect(card).toBeVisible({ timeout: 45_000 });

  const firstTitle = (await card.getByRole('heading').first().innerText()).trim();
  expect(firstTitle.length).toBeGreaterThan(0);

  // "Swipe right" via the LIKE button — exercises decide() → recordSwipe → the
  // deck advancing to the next card.
  await page.getByRole('button', { name: 'LIKE', exact: true }).click();

  // The top card's title should change (allowing for the exit animation).
  await expect
    .poll(
      async () => (await page.getByTestId('swipe-card').first().getByRole('heading').first().innerText()).trim(),
      { timeout: 20_000 },
    )
    .not.toBe(firstTitle);

  // The deck is still interactive (a card is present after swiping).
  await expect(page.getByTestId('swipe-card').first()).toBeVisible();
});

test('privacy policy page renders the full policy', async ({ page }) => {
  await page.goto('/privacy/');
  await expect(page.getByRole('heading', { name: 'Queued Privacy Policy' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Deleting your data' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Contact' })).toBeVisible();
});

test('for-you page shows the Taste Matchmaker', async ({ page }) => {
  await page.goto('/for-you/');
  await expect(page.getByRole('heading', { name: 'Taste Matchmaker' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Copy' })).toBeVisible();
});
