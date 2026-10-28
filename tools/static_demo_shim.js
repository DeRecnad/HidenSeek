/* Онлайн-демо HidenSeek без сервера.
 * Подменяет fetch для /api/*: учебные аудиты заранее посчитаны настоящим Python-кодом
 * (tools/build_static_demo.py) — два запуска, чтобы было видно сравнение. Здесь они только
 * проигрываются, а отметки «мой / не мой» и «закрыл» пересобирают отчёт из заранее посчитанных
 * вариантов. Реального поиска в демо нет. */
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
  const now = () => new Date().toISOString();

  const WHAT_LABEL = {password: 'пароль в утечке', breach: 'утечка', phone: 'телефон', real_name: 'настоящее имя', city: 'город',
    email: 'почта', account: 'аккаунт на сервисе', username: 'занятый ник', subdomain: 'поддомен'};
  const ORDER = ['password', 'breach', 'real_name', 'city', 'email', 'phone', 'account', 'username', 'subdomain'];
  const SEV = {4: 'критично', 3: 'высокая', 2: 'средняя', 1: 'низкая', 0: 'инфо'};
  const RESOLVED_NOTE = 'Вы отметили это как закрытое. Следующий аудит покажет, исчезло ли оно на самом деле.';

  const T = {а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'e', ж: 'zh', з: 'z', и: 'i', й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't', у: 'u', ф: 'f', х: 'kh', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'shch', ъ: '', ы: 'y', ь: '', э: 'e', ю: 'yu', я: 'ya'};
  const translit = v => [...v.toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim()].map(c => T[c] ?? c).join('');
  function latinKey(v) {  // как core/normalizer.latin_key
    let k = translit(v).replace(/[^a-z0-9 ]/g, '');
    [['kh', 'h'], ['ts', 'c'], ['yu', 'iu'], ['ya', 'ia'], ['shch', 'sch'], ['zh', 'j'], ['y', 'i'], ['ks', 'x']].forEach(([a, b]) => { k = k.split(a).join(b); });
    return k.replace(/(.)\1+/g, '$1').trim();
  }

  function rebuild(st) {
    const a = st.cur, variants = D.personas[st.persona].phases[st.phase].variants;
    const diff = a.report.diff;
    const change = {};
    if (diff) ['new', 'gone', 'changed'].forEach(k => diff[k].forEach(id => { change[id] = k; }));
    const items = a.findings.map(f => {
      if (st.status[f.id]) f.status = st.status[f.id];
      f.resolved_at = st.resolved[f.id] || null;
      const it = clone(variants[f.id][f.status]);
      if (it.fields) { f.data.fields = it.fields; delete it.fields; } else if (f.type === 'profile_url') delete f.data.fields;
      it.finding = clone(f);
      it.gone = !!f.gone_at;
      it.change = change[f.id] || null;
      it.resolved = !!f.resolved_at;
      if (it.resolved && !it.gone && f.status !== 'not_mine') it.recommendations.unshift(RESOLVED_NOTE);
      it.severity_label = SEV[it.severity];
      return it;
    });
    items.sort((x, y) => (x.gone - y.gone) || (y.severity - x.severity) || (x.resolved - y.resolved)
      || ((x.finding.status !== 'review') - (y.finding.status !== 'review')) || x.finding.source.localeCompare(y.finding.source));
    const active = it => !it.gone && it.finding.status !== 'not_mine';
    const confirmed = {}, review = {};
    items.filter(active).forEach(it => {
      const bucket = it.finding.status === 'review' ? review : confirmed;
      new Set(it.exposures.map(e => e.what)).forEach(w => { bucket[w] = (bucket[w] || 0) + 1; });
    });
    const parts = ORDER.filter(w => confirmed[w]).map(w => `${WHAT_LABEL[w]} — в ${confirmed[w]}`);
    let summary = parts.length ? 'Видно: ' + parts.join('; ') + '.' : 'Подтверждённых раскрытий пока нет.';
    const pending = items.filter(it => active(it) && it.finding.status === 'review').length;
    if (pending) summary += ` Ещё ${pending} находок ждут проверки «мой / не мой».`;
    const actionable = items.filter(i => i.severity > 0), resolved = actionable.filter(i => i.resolved).length;
    if (resolved) summary += ` Закрыто вами: ${resolved} из ${actionable.length}.`;
    if (diff) summary += ` С прошлого аудита: новых ${diff.new.length}, исчезло ${diff.gone.length}, изменилось ${diff.changed.length}.`;

    const seen = {};
    items.filter(active).forEach(it => {
      const loc = ((it.finding.data || {}).fields || {}).location;
      if (loc) (seen[latinKey(loc.split(',')[0])] = seen[latinKey(loc.split(',')[0])] || []).push({value: loc, source: it.finding.source, finding_id: it.finding.id});
    });
    const conflicts = Object.keys(seen).length > 1 ? [{field: 'city', values: Object.values(seen).flat()}] : [];

    a.report = Object.assign(a.report, {
      summary, items, conflicts, counts: {confirmed, review},
      max_severity: Math.max(0, ...items.map(i => i.severity)),
      totals: Object.assign(a.report.totals, {
        findings: a.findings.filter(f => !f.gone_at).length, gone: a.findings.filter(f => f.gone_at).length,
        review: pending, actionable: actionable.length, resolved,
        exposures: items.filter(active).reduce((n, i) => n + i.exposures.length, 0)}),
    });
    const byId = Object.fromEntries(items.map(i => [i.finding.id, i]));
    const LINK = {confirmed: 'confirmed', mine: 'confirmed', review: 'hypo', not_mine: 'conflict'};
    a.graph.nodes.forEach(n => {
      const it = byId[n.id]; if (!it) return;
      n.status = it.finding.status;
      n.severity = active(it) ? Math.max(0, ...it.exposures.map(e => e.severity)) : 0;
      n.exposes = it.exposures.map(e => e.what);
    });
    a.graph.edges.forEach(e => { const it = byId[e.to]; if (it) e.link = LINK[it.finding.status]; });
  }

  function load(st, snapshot, log) {
    const disabled = st.cur ? st.cur.disabled_modules : [];
    const created = st.cur ? st.cur.created_at : now();
    st.cur = clone(snapshot);
    Object.assign(st.cur, {id: st.id, created_at: created, updated_at: now(), disabled_modules: disabled.slice()});
    st.cur.report.audit_id = st.id;
    st.cur.modules.forEach(m => { m.enabled = !disabled.includes(m.name); });
    if (log) st.cur.log = log;
    rebuild(st);
  }

  function create(persona, ran) {
    const p = D.personas[persona];
    const id = 'aud_demo' + String(++seq).padStart(2, '0');
    const st = {id, persona, phase: 0, runs: 0, status: {}, resolved: {}, cur: null};
    if (ran) { st.runs = 1; load(st, p.phases[0].steps[p.phases[0].steps.length - 1]); } else load(st, p.initial);
    audits[id] = st;
    return st;
  }

  function run(st) {
    const phase = Math.min(st.runs, 1), steps = D.personas[st.persona].phases[phase].steps;
    const base = phase ? D.personas[st.persona].phases[0].steps.slice(-1)[0].log.length : D.personas[st.persona].initial.log.length;
    const prevLog = st.cur.log.slice();
    st.phase = phase;
    st.runs += 1;
    let i = 0;
    const tick = () => {
      load(st, steps[i], prevLog.concat(steps[i].log.slice(base)));
      st.cur.running = i < steps.length - 1;
      if (st.cur.running) { i += 1; st.timer = setTimeout(tick, 380); }
    };
    tick();
    st.cur.running = true;
  }

  function normalize(v) {
    const low = v.toLowerCase().replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();
    const compact = low.replace(/[^a-z0-9а-я@._+-]/g, '');
    const out = {'Исходное значение': v, 'Нижний регистр': low, 'Без пробелов и спецсимволов': compact,
      'Компактный вариант': compact.replace(/[._+-]/g, ''), 'Транслитерация': translit(v)};
    const digits = v.replace(/\D/g, '');
    if (digits.length >= 10) {
      let d = digits;
      if (d.length === 11 && d[0] === '8') d = '7' + d.slice(1); else if (d.length === 10) d = '7' + d;
      out['Телефон (E.164)'] = '+' + d;
    }
    out['Латиница для сверки имён'] = translit(v);
    return {variants: out};
  }

  const logLine = (st, level, text) => st.cur.log.push({at: now(), level, text});

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
    if ((m = rest.match(/^\/findings\/([^/]+)\/(review|resolve)$/)) && method === 'POST') {
      if (st.cur.running) return fail(409, 'Аудит выполняется — дождитесь окончания');
      const f = st.cur.findings.find(x => x.id === m[1]);
      if (!f) return fail(404, 'Нет такой находки');
      if (m[2] === 'review') {
        const v = body.verdict;
        st.status[f.id] = v == null ? (f.type === 'profile_url' ? 'review' : 'confirmed') : v;
        logLine(st, st.status[f.id] === 'mine' ? 'OK' : 'INFO', `MANUAL REVIEW ....... ${f.value} → ${st.status[f.id].toUpperCase()}`);
        const variant = D.personas[st.persona].phases[st.phase].variants[f.id].mine;
        if (st.status[f.id] === 'mine' && variant.fields) logLine(st, 'OK', `OWN PROFILE ....... ${f.value}: поля ${Object.keys(variant.fields).sort().join(', ')}`);
      } else {
        st.resolved[f.id] = body.done ? now() : null;
        logLine(st, body.done ? 'OK' : 'INFO', `CHECKLIST ....... ${f.value} → ${body.done ? 'ЗАКРЫТО' : 'ОТКРЫТО'}`);
      }
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
    if (rest === '/schedule') return fail(400, 'Расписание — только для аудита своего следа (локально)');
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

  window.HS_EXPORT = (a, fmt) => {
    const box = document.getElementById('ctxBody');
    document.getElementById('shell').classList.add('with-ctx');
    document.getElementById('ctxPanel').classList.add('sheet-open');
    box.innerHTML = `<div class="ctx-title">${fmt === 'html' ? 'Отчёт HTML' : 'Выгрузка JSON'}</div><div class="ctx-sub">В онлайн-демо файл не скачивается — вот его суть. Локально кнопка сохраняет полный файл${fmt === 'html' ? ', который открывается офлайн и печатается' : ''}.</div><pre class="terminal" style="white-space:pre-wrap;max-height:60vh"></pre>`;
    box.querySelector('pre').textContent = fmt === 'html'
      ? a.report.summary + '\n\n' + a.report.items.filter(i => i.severity).slice(0, 8).map(i => `[${i.severity_label}] ${i.finding.value}\n  → ${i.recommendations[0] || ''}`).join('\n')
      : JSON.stringify({audit_id: a.id, summary: a.report.summary, items: a.report.items.slice(0, 5)}, null, 2);
  };

  // Страница открывается в рабочем состоянии: аудит Алисы уже проведён один раз.
  window.HS_BOOT_AUDIT = create('alice', true).id;
  try { localStorage.removeItem('hs_audit'); } catch { /* private mode */ }

  const btn = document.getElementById('newRealBtn');
  if (btn) {
    btn.disabled = true;
    btn.insertAdjacentHTML('afterend', '<p class="ascii-note">Онлайн-демо: здесь работает только учебный режим. Чтобы проверить свой след, запустите проект локально — <span class="mono">python -m hidenseek</span>.</p>');
  }
})();
