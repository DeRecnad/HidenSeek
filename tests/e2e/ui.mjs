// Сквозная проверка интерфейса в браузере: учебный аудит на локальном сервере и онлайн-демо без сервера.
//   python -m hidenseek serve --port 8765 &   (с MODULE_DELAY=0)
//   python tools/build_static_demo.py build/hidenseek-demo.html
//   node tests/e2e/ui.mjs http://127.0.0.1:8765 build/hidenseek-demo.html
import assert from 'node:assert/strict';
import {readFileSync, writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {chromium} from 'playwright';

const [base = 'http://127.0.0.1:8765', demoPage = 'build/hidenseek-demo.html'] = process.argv.slice(2);
const browser = await chromium.launch();

async function page(viewport) {
  const p = await browser.newPage({viewport});
  p.errors = [];
  p.on('pageerror', e => p.errors.push(e.message));
  p.on('console', m => { if (m.type() === 'error') p.errors.push(m.text()); });
  return p;
}

async function runAndWait(p) {
  const done = () => (document.querySelector('#fullTerminal').textContent.match(/AUDIT DONE/g) || []).length;
  const before = await p.evaluate(done);
  await p.click('#runBtn');
  await p.waitForFunction(n => (document.querySelector('#fullTerminal').textContent.match(/AUDIT DONE/g) || []).length > n
    && !document.body.classList.contains('running'), before, {timeout: 30000});
}

async function scenario(p, label) {
  await p.locator('.candidate', {hasText: 'DemoDev'}).locator('[data-v="mine"]').click();
  await p.locator('.candidate', {hasText: 'PhotoSite'}).locator('[data-v="mine"]').click();
  await p.waitForFunction(() => document.querySelector('#conflictBox').textContent.includes('Москва'));
  await p.goto(p.url().split('#')[0] + '#report');
  await p.locator('.rep-item', {hasText: 'oldsocial.example'}).locator('[data-resolve]').click();
  await p.waitForFunction(() => document.querySelector('#reportSummary').textContent.includes('Закрыто вами: 1'));
  await runAndWait(p);
  await p.goto(p.url().split('#')[0] + '#case');
  const diff = await p.textContent('#diffList');
  assert.match(diff, /newsletter\.example/, `${label}: новое в сравнении`);
  assert.match(diff, /ВЫ ЗАКРЫЛИ — ПОДТВЕРЖДЕНО/, `${label}: закрытое подтверждено`);
  assert.equal(await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, `${label}: нет горизонтальной прокрутки`);
  assert.deepEqual(p.errors, [], `${label}: ошибки в консоли`);
}

// 1. Локальный сервер, десктоп
{
  const p = await page({width: 1440, height: 1000});
  await p.goto(base + '/');
  await p.click('[data-persona="alice"]');
  await runAndWait(p);
  assert.ok(Number(await p.textContent('#statFind')) > 0, 'сервер: есть находки');
  await scenario(p, 'сервер');
  const r = await p.request.get(base + '/api/config');
  assert.equal((await r.json()).encryption, 'on', 'сервер: шифрование включено');
}

// 2. Онлайн-демо без сервера, телефон
{
  const html = readFileSync(demoPage, 'utf8');
  const wrapped = resolve('build/e2e-demo-wrapped.html');
  writeFileSync(wrapped, `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head><body>${html}</body></html>`);
  const p = await page({width: 390, height: 844});
  await p.goto('file://' + wrapped);
  await p.waitForFunction(() => document.querySelector('#statFind').textContent.trim() !== '0');
  await scenario(p, 'онлайн-демо');
}

await browser.close();
console.log('e2e: OK');
