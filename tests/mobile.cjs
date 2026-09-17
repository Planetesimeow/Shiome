// Run against `python -m tests.browser_server`; no model calls and no real data.
const assert = require('node:assert/strict');
const { chromium, webkit } = require('playwright');

async function checkDetailRecovery(page, context, firstPost) {
  const base = 'http://127.0.0.1:8765';
  const second = await (await context.request.post(`${base}/api/posts`, { data: {
    title: '快速切换的第二条作品', publish_date: '2026-09-11', plays: 9000, new_followers: 90,
  } })).json();
  const profilePath = `**/api/posts/${second.id}/content-profile`;
  await context.request.patch(`${base}/api/posts/${second.id}/content-profile`, { data: { content_summary: '第二条的内容' } });
  let release, arrived;
  const gate = new Promise(resolve => { release = resolve; });
  const waiting = new Promise(resolve => { arrived = resolve; });
  await page.route(`**/api/posts/${firstPost.id}`, async route => {
    const response = await route.fetch();
    arrived();
    await gate;
    await route.fulfill({ response });
  });
  await page.evaluate(id => { window.oldSelection = selectVideo(id); }, firstPost.id);
  await waiting;
  await page.evaluate(id => selectVideo(id), second.id);
  release();
  await page.evaluate(() => window.oldSelection);
  await page.unroute(`**/api/posts/${firstPost.id}`);
  assert.equal(await page.locator('#pf-content_summary').inputValue(), '第二条的内容');
  assert.equal(await page.locator('#metrics-panel .value').first().textContent(), '9000');

  if (!await page.locator('#pf-content_summary').isVisible()) await page.locator('#profile-panel summary').click();
  const save = page.locator('button[onclick="saveContentProfile(this)"]');
  let writes = 0;
  await page.route(profilePath, async route => {
    writes++;
    await route.fulfill({ status: 503, json: { detail: '测试网络中断' } });
  });
  await page.locator('#pf-content_summary').fill('重试后应该保留的修改');
  await save.evaluate(button => { button.click(); button.click(); });
  await page.locator('#status-line').filter({ hasText: '保存失败' }).waitFor();
  assert.equal(writes, 1);
  assert.equal(await page.locator('#pf-content_summary').inputValue(), '重试后应该保留的修改');
  assert(await save.isEnabled());
  await page.unroute(profilePath);
  await save.click();
  await page.locator('#status-line').filter({ hasText: '内容画像已保存' }).waitFor();
  const persisted = await (await context.request.get(`${base}/api/posts/${second.id}`)).json();
  assert.equal(persisted.creative.content_summary, '重试后应该保留的修改');

  const snapshotPath = `**/api/posts/${second.id}/snapshots`;
  await page.route(snapshotPath, route => route.fulfill({ status: 503, json: { detail: '测试网络中断' } }));
  await page.locator('#sn-plays').fill('7777');
  const snapshot = page.locator('button[onclick="addSnapshot(this)"]');
  await snapshot.click();
  await page.locator('#status-line').filter({ hasText: '记录失败' }).waitFor();
  assert.equal(await page.locator('#sn-plays').inputValue(), '7777');
  await page.unroute(snapshotPath);
  await snapshot.click();
  await page.locator('#status-line').filter({ hasText: '快照已记录' }).waitFor();
  assert((await page.locator('#snapshot-list').textContent()).includes('7777'));
  assert.equal(await page.evaluate(() => diffusionChartInstance.data.datasets[0].data.at(-1)), 7777);

  // Switching tabs while an analysis is running must reuse the same paid request.
  let releaseAnalysis, analysisArrived, calls = 0;
  const analysisGate = new Promise(resolve => { releaseAnalysis = resolve; });
  const analysisWaiting = new Promise(resolve => { analysisArrived = resolve; });
  await page.route(`**/api/analyze/posts/${second.id}/enhancement`, async route => {
    calls++;
    analysisArrived();
    await analysisGate;
    await route.fulfill({ json: { diagnosis: ['测试分析完成'], concrete_edits: [], what_worked: [] } });
  });
  await page.locator('.tab[data-type="enhancement"]').click();
  await page.locator('#result-container button').filter({ hasText: '运行分析' }).click();
  await analysisWaiting;
  await page.locator('.tab[data-type="creator_profile"]').click();
  await page.locator('.tab[data-type="enhancement"]').click();
  releaseAnalysis();
  await page.locator('#result-container').filter({ hasText: '测试分析完成' }).waitFor();
  assert.equal(calls, 1);
  await page.unroute(`**/api/analyze/posts/${second.id}/enhancement`);
  await context.request.delete(`${base}/api/posts/${second.id}`);
  await page.evaluate(id => selectVideo(id), firstPost.id);
  console.log('PASS delayed detail, draft retry, duplicate save guard, snapshot refresh, shared analysis');
}

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
      if (width === 360) await checkDetailRecovery(page, context, posts[0]);
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
