/* Онлайн-демо HidenSeek без сервера.
 * Подменяет fetch для /api/*: учебные аудиты заранее посчитаны настоящим Python-кодом
 * (tools/build_static_demo.py), здесь они только проигрываются, а отметки «мой / не мой»
 * пересобирают отчёт из заранее посчитанных вариантов. Реального поиска в демо нет. */
(function () {
  'use strict';
  const D = window.HS_DEMO;
  const LOCAL_ONLY = 'В онлайн-демо доступен только учебный режим. Реальный аудит своего следа запускается локально: python -m hidenseek';
  const clone = o => JSON.parse(JSON.stringify(o));
  const audits = {};
  let seq = 0;

  window.confirm = () => true;  // в окне артефакта confirm() недоступен; данные здесь синтетические

  const reply = (status, data) => Promise.resolve(new Response(JSON.stringify(data), {status, headers: {'Content-Type': 'application/json'}}));
  const fail = (status, detail) => reply(status, {detail});

  const WHAT_LABEL = {password: 'пароль в утечке', breach: 'утечка', phone: 'телефон', real_name: 'настоящее имя', city: 'город',
    email: 'почта', account: 'аккаунт на сервисе', username: 'занятый ник', subdomain: 'поддомен'};
  const ORDER = ['password', 'breach', 'real_name', 'city', 'email', 'phone', 'account', 'username', 'subdomain'];

  function rebuild(st) {
    const a = st.cur, variants = D.personas[st.persona].variants;
    a.findings.forEach(f => { if (st.status[f.id]) f.status = st.status[f.id]; });
    const items = a.findings.map(f => { const it = clone(variants[f.id][f.status]); it.finding = clone(f); return it; });
    items.sort((x, y) => (y.severity - x.severity) || ((x.finding.status !== 'review') - (y.finding.status !== 'review')) || x.finding.source.localeCompare(y.finding.source));
    const confirmed = {}, review = {};
    items.forEach(it => {
      if (it.finding.status === 'not_mine') return;
      const bucket = it.finding.status === 'review' ? review : confirmed;
      new Set(it.exposures.map(e => e.what)).forEach(w => { bucket[w] = (bucket[w] || 0) + 1; });
    });
    const parts = ORDER.filter(w => confirmed[w]).map(w => `${WHAT_LABEL[w]} — в ${confirmed[w]}`);
    let summary = parts.length ? 'Видно: ' + parts.join('; ') + '.' : 'Подтверждённых раскрытий пока нет.';
    const pending = a.findings.filter(f => f.status === 'review').length;
    if (pending) summary += ` Ещё ${pending} находок ждут проверки «мой / не мой».`;
    a.report = Object.assign(a.report, {
      summary, counts: {confirmed, review}, items,
      max_severity: Math.max(0, ...items.map(i => i.severity)),
      totals: Object.assign(a.report.totals, {findings: a.findings.length, review: pending,
        exposures: items.reduce((n, i) => n + i.exposures.length, 0)}),
    });
    const byId = Object.fromEntries(items.map(i => [i.finding.id, i]));
    const LINK = {confirmed: 'confirmed', mine: 'confirmed', review: 'hypo', not_mine: 'conflict'};
    a.graph.nodes.forEach(n => {
      const it = byId[n.id]; if (!it) return;
      n.status = it.finding.status;
      n.severity = Math.max(0, ...it.exposures.map(e => e.severity));
      n.exposes = it.exposures.map(e => e.what);
    });
    a.graph.edges.forEach(e => { const it = byId[e.to]; if (it) e.link = LINK[it.finding.status]; });
  }

  function load(st, snapshot, keepLog) {
    const log = keepLog ? st.cur.log : null;
    const disabled = st.cur ? st.cur.disabled_modules : [];
    st.cur = clone(snapshot);
    st.cur.id = st.id;
    st.cur.report.audit_id = st.id;
    st.cur.disabled_modules = disabled.slice();
    st.cur.modules.forEach(m => { m.enabled = !disabled.includes(m.name); });
    if (log) st.cur.log = log.concat(snapshot.log.slice(st.baseLog));
    st.cur.updated_at = new Date().toISOString();
    rebuild(st);
  }

  function create(persona, ran) {
    const p = D.personas[persona];
    const id = 'aud_demo' + String(++seq).padStart(2, '0');
    const st = {id, persona, status: {}, cur: null, baseLog: p.initial.log.length};
    load(st, ran ? p.steps[p.steps.length - 1] : p.initial);
    st.cur.created_at = new Date().toISOString();
    audits[id] = st;
    return st;
  }

  function run(st) {
    const steps = D.personas[st.persona].steps, prevLog = st.cur.log.slice(), created = st.cur.created_at;
    let i = 0;
    const tick = () => {
      st.cur.log = prevLog;
      load(st, steps[i], true);
      st.cur.created_at = created;
      st.cur.running = i < steps.length - 1;
      if (st.cur.running) { i += 1; st.timer = setTimeout(tick, 380); }
    };
    tick();
    st.cur.running = true;
  }

  function normalize(v) {
    const T = {а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'kh', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'shch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya'};
    const low = v.toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();
    const compact = low.replace(/[^a-z0-9а-я@._+-]/g, '');
    const tr = [...low].map(c => T[c] ?? c).join('');
    const out = {'Исходное значение': v, 'Нижний регистр': low, 'Без пробелов и спецсимволов': compact,
      'Компактный вариант': compact.replace(/[._+-]/g, ''), 'Транслитерация': tr};
    const digits = v.replace(/\D/g, '');
    if (digits.length >= 10) {
      let d = digits;
      if (d.length === 11 && d[0] === '8') d = '7' + d.slice(1); else if (d.length === 10) d = '7' + d;
      out['Телефон (E.164)'] = '+' + d;
    }
    out['Латиница для сверки имён'] = tr;
    return {variants: out};
  }

  function route(method, path, body) {
    let m;
    if (method === 'GET' && path === '/api/config') return reply(200, D.config);
    if (method === 'POST' && path === '/api/normalize') return reply(200, normalize(String(body.value || '').slice(0, 200)));
    if (path === '/api/audits') {
      if (method === 'GET') return reply(200, Object.values(audits).reverse().map(s => ({id: s.id, mode: 'demo', persona: s.persona,
        created_at: s.cur.created_at, save: false, findings: s.cur.findings.length, name: s.cur.owner_profile.full_name})));
      if (method === 'POST') {
        if (body.mode !== 'demo') return fail(400, LOCAL_ONLY);
        if (!D.personas[body.persona]) return fail(400, 'Нет такого персонажа');
        return reply(200, create(body.persona, false).cur);
      }
    }
    if (method === 'DELETE' && path === '/api/data') {
      Object.values(audits).forEach(s => clearTimeout(s.timer));
      Object.keys(audits).forEach(k => delete audits[k]);
      return reply(200, {ok: true});
    }
    if (!(m = path.match(/^\/api\/audits\/([^/]+)(\/.*)?$/))) return fail(404, 'Not found');
    const st = audits[m[1]], rest = m[2] || '';
    if (!st) return fail(404, 'Аудит не найден');
    if (rest === '' && method === 'GET') return reply(200, st.cur);
    if (rest === '' && method === 'DELETE') { clearTimeout(st.timer); delete audits[st.id]; return reply(200, {ok: true}); }
    if (rest === '/run' && method === 'POST') {
      if (st.cur.running) return fail(409, 'Аудит выполняется — дождитесь окончания');
      run(st);
      return reply(200, st.cur);
    }
    if ((m = rest.match(/^\/findings\/([^/]+)\/review$/)) && method === 'POST') {
      if (st.cur.running) return fail(409, 'Аудит выполняется — дождитесь окончания');
      const f = st.cur.findings.find(x => x.id === m[1]);
      if (!f) return fail(404, 'Нет такой находки');
      const v = body.verdict;
      st.status[f.id] = v == null ? (f.type === 'profile_url' ? 'review' : 'confirmed') : v;
      st.cur.log.push({at: new Date().toISOString(), level: st.status[f.id] === 'mine' ? 'OK' : 'INFO', text: `MANUAL REVIEW ....... ${f.value} → ${st.status[f.id].toUpperCase()}`});
      rebuild(st);
      return reply(200, st.cur);
    }
    if ((m = rest.match(/^\/modules\/([^/]+)$/)) && method === 'PUT') {
      const d = st.cur.disabled_modules;
      if (body.enabled) st.cur.disabled_modules = d.filter(x => x !== m[1]);
      else if (!d.includes(m[1])) d.push(m[1]);
      st.cur.modules.forEach(x => { x.enabled = !st.cur.disabled_modules.includes(x.name); });
      return reply(200, st.cur);
    }
    return fail(400, LOCAL_ONLY);
  }

  const realFetch = window.fetch.bind(window);
  window.fetch = (input, opt = {}) => {
    const url = typeof input === 'string' ? input : input.url;
    if (!url.startsWith('/api/')) return realFetch(input, opt);
    let body = {};
    try { body = opt.body ? JSON.parse(opt.body) : {}; } catch { /* empty */ }
    return route((opt.method || 'GET').toUpperCase(), url.split('?')[0], body);
  };

  window.HS_EXPORT = a => {
    const box = document.getElementById('ctxBody');
    document.getElementById('shell').classList.add('with-ctx');
    document.getElementById('ctxPanel').classList.add('sheet-open');
    box.innerHTML = '<div class="ctx-title">Выгрузка JSON</div><div class="ctx-sub">В онлайн-демо файл не скачивается — вот его начало. Локально кнопка сохраняет полный файл.</div><pre class="terminal" style="white-space:pre-wrap;max-height:60vh"></pre>';
    box.querySelector('pre').textContent = JSON.stringify({audit_id: a.id, summary: a.report.summary, items: a.report.items.slice(0, 5)}, null, 2);
  };

  // Страница открывается в рабочем состоянии: аудит Алисы уже проведён.
  window.HS_BOOT_AUDIT = create('alice', true).id;
  try { localStorage.removeItem('hs_audit'); } catch { /* private mode */ }

  const btn = document.getElementById('newRealBtn');
  if (btn) {
    btn.disabled = true;
    btn.insertAdjacentHTML('afterend', '<p class="ascii-note">Онлайн-демо: здесь работает только учебный режим. Чтобы проверить свой след, запустите проект локально — <span class="mono">python -m hidenseek</span>.</p>');
  }
})();
