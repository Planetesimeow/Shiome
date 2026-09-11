// Run against `python -m tests.browser_server`; no model calls and no real data.
const assert = require('node:assert/strict');
const { chromium, webkit } = require('playwright');

async function main() {
  const engine = process.env.SHIOME_BROWSER === 'webkit' ? webkit : chromium;
  const browser = await engine.launch({ headless: true, ...(process.env.SHIOME_BROWSER_CHANNEL ? { channel: process.env.SHIOME_BROWSER_CHANNEL } : {}) });
  try {
    for (const width of [360, 390, 430, 1280]) {
      const context = await browser.newContext({ viewport: { width, height: 844 }, isMobile: width < 760, hasTouch: width < 760, timezoneId: 'Asia/Tokyo' });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', e => errors.push(e.message));
      await page.goto('http://127.0.0.1:8765/');
      await page.waitForURL('**/login');
      await page.locator('#password').fill('browser-test-password');
      await page.locator('#submit').click();
      await page.waitForURL('http://127.0.0.1:8765/');
      await page.locator('#hs-count').filter({ hasText: /\d/ }).waitFor();
      const fits = async () => assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), `horizontal overflow at ${width}`);
      await fits();
      if (width < 760) {
        await page.locator('.mobile-nav [data-view="capture"]').click();
        assert(await page.locator('#capture-intro').isVisible());
      }
      await page.locator('#shot-input').setInputFiles({ name: 'screenshot.png', mimeType: 'image/png', buffer: Buffer.from('fixture') });
      await page.locator('[data-save-draft]').waitFor();
      const title = page.locator('[id$="-v0-title"]');
      assert((await title.inputValue()).includes('"引号"'));
      const duration = page.locator('[id$="-v0-duration_sec"]');
      assert.equal(await duration.inputValue(), '18');
      // UTC+9 must be displayed as local time; the saved API timestamp stays UTC.
      const observed = await page.locator('[id$="-checked_at"]').inputValue();
      const expected = await page.evaluate(() => localDateTime());
      assert.equal(observed, expected);
      await fits();
      if (width < 760) {
        await page.locator('.mobile-nav [data-view="overview"]').click();
        await page.locator('.mobile-nav [data-view="capture"]').click();
        assert((await title.inputValue()).includes('"引号"'));
      }
      // A lost session must preserve editable work and present a working login link.
      await context.clearCookies();
      await page.locator('[data-save-draft]').click();
      await page.locator('#reauth-notice').waitFor();
      assert(await title.isVisible());
      const login = await context.request.post('http://127.0.0.1:8765/api/auth/login', { data: { password: 'browser-test-password' } });
      assert.equal(login.status(), 200);
      await duration.fill('21');
      const save = page.waitForResponse(r => r.url().endsWith('/api/vision/save') && r.status() === 200);
      await page.locator('[data-save-draft]').click();
      await save;
      await page.locator('[data-save-draft]').waitFor({ state: 'detached' });
      await page.locator('#status-line').filter({ hasText: '已保存' }).waitFor();
      assert(await page.locator('#reauth-notice').isHidden());
      if (width < 760) await page.locator('.mobile-nav [data-view="posts"]').click();
      await page.locator('.video-row .title').first().click();
      await page.locator('#metrics-panel .metric').first().waitFor();
      await page.locator('.tab[data-type="creator_profile"]').click();
      await page.locator('#profile-panel summary').click();
      await fits();
      const posts = await (await context.request.get('http://127.0.0.1:8765/api/posts')).json();
      assert.equal(posts[0].duration_sec, 21);
      const backup = await context.request.get('http://127.0.0.1:8765/api/backup');
      assert.equal(backup.status(), 200);
      assert((await backup.body()).subarray(0, 15).equals(Buffer.from('SQLite format 3')));
      if (process.env.SHIOME_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.SHIOME_SCREENSHOT_DIR}/shiome-${width}.png`, fullPage: true });
      await page.locator('#tools-menu summary').click();
      await page.locator('#logout-btn').click();
      await page.waitForURL('**/login');
      assert.deepEqual(errors, [], `browser errors at ${width}`);
      console.log(`PASS ${width}px login, capture, draft recovery, save, detail, backup, logout`);
      await context.close();
    }
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
