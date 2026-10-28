/* HidenSeek — Ghost Terminal UI, подключённый к локальному JSON API */
'use strict';
const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];

/* ---------- helpers ---------- */
const ESC = {'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'};
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ESC[c]);
function safeUrl(u) {
  try { const x = new URL(u); return (x.protocol === 'http:' || x.protocol === 'https:') ? x.href : null; } catch { return null; }
}
function link(u, text) {
  const s = safeUrl(u);
  return s ? `<a href="${esc(s)}" target="_blank" rel="noopener noreferrer">${esc(text || u)}</a>` : esc(text || '');
}
const pad = n => String(n).padStart(2, '0');
function fmtTime(iso) { if (!iso) return '—'; const d = new Date(iso); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; }
function fmtDate(iso) { if (!iso) return '—'; const d = new Date(iso); return `${pad(d.getDate())}.${pad(d.getMonth() + 1)}.${String(d.getFullYear()).slice(2)} ${pad(d.getHours())}:${pad(d.getMinutes())}`; }
const lsGet = k => { try { return localStorage.getItem(k); } catch { return null; } };
const lsSet = (k, v) => { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch { /* private mode */ } };

const toast = $('#toast'); let toastTimer;
function notify(msg) { toast.textContent = msg; toast.classList.add('show'); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove('show'), 2800); }

async function api(method, path, body) {
  const opt = {method, headers: {'X-HidenSeek': '1'}};
  if (body !== undefined) { opt.headers['Content-Type'] = 'application/json'; opt.body = JSON.stringify(body); }
  const r = await fetch(path, opt);
  let data = null;
  try { data = await r.json(); } catch { /* empty */ }
  if (!r.ok) throw new Error((data && data.detail) || `HTTP ${r.status}`);
  return data;
}
async function act(fn, okMsg) {
  try { const res = await fn(); if (okMsg) notify(okMsg); return res; } catch (e) { notify('✕ ' + e.message); return null; }
}

/* ---------- labels ---------- */
const TYPE_LABEL = {email: 'EMAIL', github: 'GITHUB', domain: 'ДОМЕН', username: 'НИК'};
const TYPE_AV = {email: '@', github: 'gh', domain: '.d', username: 'nk'};
const FTYPE = {profile_url: 'профиль на сайте', registered_service: 'аккаунт на сервисе', breach: 'утечка',
  public_email_in_commits: 'email в коммитах', profile_fields: 'поля профиля', subdomain: 'поддомен', certificate: 'сертификаты'};
const WHAT = {password: 'ПАРОЛЬ', breach: 'УТЕЧКА', phone: 'ТЕЛЕФОН', real_name: 'ИМЯ', city: 'ГОРОД', email: 'ПОЧТА',
  account: 'АККАУНТ', username: 'НИК', subdomain: 'ПОДДОМЕН'};
const STATUS = {confirmed: ['ПОДТВЕРЖДЕНО', 'good'], review: ['ПРОВЕРЬТЕ', 'warn'], mine: ['МОЙ', 'good'], not_mine: ['НЕ МОЙ', 'bad']};
const SEV_LABEL = {4: 'КРИТИЧНО', 3: 'ВЫСОКАЯ', 2: 'СРЕДНЯЯ', 1: 'НИЗКАЯ', 0: 'ИНФО'};
function verifiedHow(v) {
  if (!v) return '';
  if (v === 'email_code') return 'код из письма';
  if (v === 'dns_txt') return 'TXT-запись';
  if (v === 'github_oauth') return 'GitHub OAuth';
  if (v === 'github_oauth_email') return 'подтверждён на GitHub';
  if (v === 'demo') return 'синтетика';
  if (v.startsWith('inherited:')) return 'наследует';
  if (v.startsWith('domain_link:')) return 'ссылка с домена';
  return v;
}

/* ---------- state ---------- */
const S = {cfg: null, audit: null, list: [], view: 'start', pendingCode: new Set(), findFilter: 'all', logFilter: {mini: 'ALL', full: 'ALL'}, pollTimer: null, ctx: null};
const NEED_AUDIT = new Set(['case', 'identities', 'graph', 'evidence', 'report', 'sources', 'timeline', 'terminal']);
const TITLES = {
  start: ['SESSION', 'Аудиты', 'Начните аудит своего следа или откройте учебный режим.'],
  case: ['PERSONAL FOOTPRINT', 'Мой цифровой след', 'Что обо мне видно снаружи и что стоит закрыть.'],
  identities: ['VERIFIED SEEDS', 'Мои идентификаторы', 'Поиск запускают только идентификаторы, которыми вы владеете и подтвердили это.'],
  graph: ['GRAPH', 'Где видны мои идентификаторы', 'Я → мои идентификаторы → места, где они видны.'],
  evidence: ['FINDINGS', 'Находки', 'Каждый факт — с источником, датой и confidence.'],
  report: ['REPORT', 'Что закрыть', 'Сводка раскрытий и рекомендации, от самого серьёзного.'],
  sources: ['SOURCES', 'Источники', 'Модули аудита, их статус и повторная проверка.'],
  timeline: ['TIMELINE', 'Хронология', 'Подтверждения и находки по времени.'],
  normalize: ['TOOLS', 'Нормализация', 'Как сверка сравнивает имена, ники и телефоны.'],
  assistant: ['TOOLS', 'Ассистент', 'Объясняет находки и подсказывает, что делать.'],
  terminal: ['TOOLS', 'Журнал', 'Все события текущего аудита.'],
  data: ['SESSION', 'Настройки и данные', 'Хранение, выгрузка и удаление данных.'],
  about: ['ABOUT', 'О проекте', 'HidenSeek — аудит собственного цифрового следа.'],
};

/* ---------- navigation ---------- */
const sidebar = $('#sidebar'), backdrop = $('#backdrop'), menuBtn = $('#menuBtn');
function openMenu(open) {
  sidebar.classList.toggle('open', open); backdrop.classList.toggle('show', open);
  menuBtn.setAttribute('aria-expanded', String(open));
}
menuBtn.addEventListener('click', () => openMenu(!sidebar.classList.contains('open')));
backdrop.addEventListener('click', () => openMenu(false));
window.addEventListener('resize', () => { if (window.innerWidth > 720) openMenu(false); });

function showView(name, {push = true} = {}) {
  if (!TITLES[name]) name = 'case';
  if (NEED_AUDIT.has(name) && !S.audit) name = 'start';
  S.view = name;
  $$('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
  $$('.worktab').forEach(b => b.classList.toggle('active', b.dataset.view === name));
  $$('.nav-item[data-view]').forEach(b => b.classList.toggle('active', b.dataset.view === name));
  const [eb, t, sub] = TITLES[name];
  $('#eyebrow').textContent = eb + (S.audit ? ' // ' + S.audit.id.toUpperCase() : '');
  $('#pageTitle').textContent = t; $('#pageSub').textContent = sub;
  const showStrip = S.audit && !['start', 'data', 'about', 'normalize', 'assistant'].includes(name);
  $('#caseStrip').style.display = showStrip ? '' : 'none';
  $('.worktabs').style.display = showStrip ? '' : 'none';
  if (push && location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
  openMenu(false);
  if (name === 'graph') setTimeout(() => graph.center(), 40);
}
window.addEventListener('hashchange', () => {
  const name = location.hash.slice(1);
  if (name && name !== S.view) showView(name, {push: false});
});
document.addEventListener('click', e => {
  const b = e.target.closest('[data-view]');
  if (b && !b.closest('.ctx-body')) showView(b.dataset.view);
});

/* ---------- loading ---------- */
async function loadConfig() {
  S.cfg = await api('GET', '/api/config');
  $('#buildVer').textContent = S.cfg.version;
  const personas = Object.entries(S.cfg.personas).map(([k, p]) => `
    <div class="persona"><div class="avatar">${esc(p.title.split(' ').map(x => x[0]).join(''))}</div>
      <div><div class="candidate-name">${esc(p.title)}</div><div class="candidate-sub">${esc(p.description)}</div></div>
      <button class="btn" data-persona="${esc(k)}">ОТКРЫТЬ ДЕМО</button></div>`).join('');
  $('#personaList').innerHTML = personas;
  $$('[data-persona]').forEach(b => b.addEventListener('click', () => newAudit('demo', b.dataset.persona)));
  const yes = (on, txt = 'OK') => on ? `<span style="color:var(--green)">${txt}</span>` : '<span style="color:var(--amber)">НЕ НАСТРОЕН</span>';
  $('#cfgSmtp').innerHTML = yes(S.cfg.smtp_configured);
  $('#cfgGh').innerHTML = yes(S.cfg.github_oauth_configured);
  $('#cfgHibp').innerHTML = yes(S.cfg.hibp_configured);
  $('#cfgTtl').textContent = S.cfg.verify_ttl_days + ' ДН.';
  $('#cfgEnc').innerHTML = {on: '<span style="color:var(--green)">ВКЛ</span>', off: '<span style="color:var(--amber)">ВЫКЛ</span>',
    unavailable: '<span style="color:var(--amber)">НЕТ ПАКЕТА</span>'}[S.cfg.encryption] || '—';
  if (S.cfg.encryption === 'unavailable') $('#encHint').textContent = 'pip install cryptography — без него аудиты сохраняются открытым JSON';
  if (S.cfg.unreadable_files) $('#encHint').textContent += ` · не удалось прочитать файлов: ${S.cfg.unreadable_files} (другой ключ?)`;
  $('#cfgAi').innerHTML = yes(S.cfg.assistant_configured);
  $('#cfgOwn').innerHTML = S.cfg.own_profiles_available ? '<span style="color:var(--green)">OK</span>' : '<span style="color:var(--amber)">НУЖЕН MAIGRET</span>';
  $('#scheduleSel').innerHTML = '<option value="">ВЫКЛ</option>' + S.cfg.schedule_choices.map(h => `<option value="${h}">КАЖДЫЕ ${h} Ч</option>`).join('');
  $('#cbUrl').textContent = location.origin + '/auth/github/callback';
  $('#ttlHint').textContent = 'ПОВТОРНОЕ ПОДТВЕРЖДЕНИЕ ЧЕРЕЗ ' + S.cfg.verify_ttl_days + ' ДН.';
}
async function loadList() {
  S.list = await api('GET', '/api/audits');
  $('#auditCount').textContent = S.list.length;
  $('#auditList').innerHTML = S.list.length ? S.list.map(a => `
    <div class="audit-row${S.audit && S.audit.id === a.id ? ' current' : ''}"><div>${esc(a.id)} · ${a.mode === 'demo' ? 'УЧЕБНЫЙ' : 'РЕАЛЬНЫЙ'}${a.name ? ' · ' + esc(a.name) : ''}
      <small>создан ${fmtDate(a.created_at)} · находок: ${a.findings} · ${a.save ? 'сохранён на диск' : 'только в памяти'}</small></div>
      <button class="btn small" data-open="${esc(a.id)}">ОТКРЫТЬ</button></div>`).join('') : '<div class="empty-mini">Аудитов пока нет</div>';
  $$('[data-open]').forEach(b => b.addEventListener('click', () => openAudit(b.dataset.open, 'case')));
}
async function openAudit(id, view) {
  const a = await act(() => api('GET', '/api/audits/' + encodeURIComponent(id)));
  if (!a) { lsSet('hs_audit', null); return; }
  setAudit(a); if (view) showView(view);
}
async function newAudit(mode, persona) {
  const a = await act(() => api('POST', '/api/audits', {mode, persona}), mode === 'demo' ? 'Учебный аудит: данные синтетические' : 'Новый аудит создан');
  if (!a) return;
  setAudit(a); loadList();
  showView(mode === 'demo' ? 'case' : 'identities');
}
function setAudit(a) {
  S.audit = a;
  lsSet('hs_audit', a ? a.id : null);
  render();
  clearTimeout(S.pollTimer);
  if (a && a.running) S.pollTimer = setTimeout(refresh, 900);
}
async function refresh() {
  if (!S.audit) return;
  try { setAudit(await api('GET', '/api/audits/' + S.audit.id)); } catch (e) { notify('✕ ' + e.message); }
}

/* ---------- render ---------- */
function render() {
  const a = S.audit;
  document.body.classList.toggle('no-audit', !a);
  document.body.classList.toggle('running', !!(a && a.running));
  $('#runBtn').disabled = !a || a.running;
  $('#runBtn').textContent = a && a.running ? '◷ АУДИТ ИДЁТ…' : '▶ ЗАПУСТИТЬ АУДИТ';
  ['#exportBtn', '#exportBtn2', '#exportBtn3', '#exportBtn4', '#deleteAuditBtn'].forEach(s => { $(s).disabled = !a; });
  if (!a) { $('#pillAudit').textContent = 'НЕТ АУДИТА'; $('#crumbId').textContent = '—'; return; }
  const rep = a.report, t = rep.totals;
  $('#pillAudit').textContent = (a.mode === 'demo' ? 'DEMO / ' : 'AUDIT / ') + a.id.slice(4).toUpperCase();
  $('#crumbId').textContent = a.id;
  $('#topStatus').textContent = a.save ? 'DB: DISK' : 'DB: MEMORY';
  $('#caseName').innerHTML = `${esc(a.owner_profile.full_name || 'я')} <span style="color:#526b58;font:11px var(--mono)">/ ${a.mode === 'demo' ? 'учебный режим' : 'аудит своего следа'}</span>`;
  $('#caseMeta').innerHTML = `<span class="tag">${a.running ? 'ВЫПОЛНЯЕТСЯ' : a.mode === 'demo' ? 'СИНТЕТИКА' : 'ГОТОВ'}</span>подтверждено ${t.identities_verified} из ${t.identities} идентификаторов · обновлено ${fmtTime(a.updated_at)}`;
  $('#statFind').textContent = pad(t.findings);
  $('#statExp').textContent = pad(t.exposures);
  $('#statExp').style.color = rep.max_severity >= 3 ? 'var(--red)' : '';
  $('#statReview').textContent = pad(t.review);
  $('#navIdent').textContent = `${t.identities_verified}/${t.identities}`;
  $('#navGraph').textContent = pad(a.graph.nodes.length);
  $('#navFind').textContent = pad(t.findings);
  $('#navRep').textContent = pad(rep.items.filter(i => i.severity > 0).length);
  $('#navSrc').textContent = pad(a.modules.length);
  $('#tabFind').textContent = t.findings;
  $('#saveToggle').checked = a.save;
  $('#saveState').textContent = a.save ? 'DISK' : 'MEMORY';
  $('#scheduleSel').value = a.schedule_hours ? String(a.schedule_hours) : '';
  $('#scheduleSel').disabled = a.mode === 'demo';
  renderAssistantMode();
  renderOverview(); renderIdentities(); renderEvidence(); renderReport(); renderSources(); renderTimeline(); renderLogs();
  graph.render(a.graph);
  if (S.ctx) openCtx(S.ctx.kind, S.ctx.id, true);
  const hasVerified = t.identities_verified > 0;
  $('#runBtn').title = hasVerified ? '' : 'Сначала подтвердите хотя бы один идентификатор';
}

function findingSub(f) {
  return `${esc(FTYPE[f.type] || f.type)} · ${esc(f.source)}${f.url && safeUrl(f.url) ? ' · ' + esc(new URL(f.url).host) : ''}`;
}
function scoreColor(c) { return c >= 0.7 ? 'var(--green2)' : c >= 0.45 ? 'var(--amber)' : 'var(--red)'; }
function scoreText(c) { return c >= 0.7 ? 'ВЕРОЯТНО ВАШ' : c >= 0.45 ? 'ПРОВЕРЬТЕ ВРУЧНУЮ' : 'ЧАСТО — ЧУЖОЙ'; }
function resolveButton(item) {
  if (!item || item.gone || !item.severity) return '';
  return `<button class="btn small resolve${item.resolved ? ' is-on' : ''}" data-resolve="${esc(item.finding.id)}" data-done="${item.resolved ? '0' : '1'}">${item.resolved ? '✓ ЗАКРЫТО' : '○ ЗАКРЫЛ'}</button>`;
}
const CHANGE_TAG = {new: ['НОВОЕ', 'good'], gone: ['ИСЧЕЗЛО', ''], changed: ['ИЗМЕНИЛОСЬ', 'warn']};
function changeTag(item) {
  const c = item && (item.gone ? 'gone' : item.change);
  return c && CHANGE_TAG[c] ? `<span class="tag ${CHANGE_TAG[c][1]}">${CHANGE_TAG[c][0]}</span>` : '';
}
function reviewButtons(f) {
  return `<div class="review-actions"><button class="btn small mine${f.status === 'mine' ? ' is-on' : ''}" data-review="${esc(f.id)}" data-v="mine">✓ МОЙ</button>` +
    `<button class="btn small notmine${f.status === 'not_mine' ? ' is-on' : ''}" data-review="${esc(f.id)}" data-v="not_mine">✕ НЕ МОЙ</button></div>`;
}

function renderOnboarding() {
  const a = S.audit, t = a.report.totals;
  const steps = [
    ['Добавьте свои email, домен или ник — или войдите через GitHub', a.identities.length > 0, 'identities'],
    ['Подтвердите владение хотя бы одним идентификатором', t.identities_verified > 0, 'identities'],
    ['Запустите аудит', a.runs.some(r => r.finished_at), null],
    ['Отметьте «мой / не мой» у найденных аккаунтов', a.runs.length > 0 && t.review === 0, 'evidence'],
  ];
  const done = steps.filter(x => x[1]).length;
  $('#onboarding').hidden = a.mode === 'demo' || done === steps.length;
  $('#onbCount').textContent = `${done} / ${steps.length}`;
  const next = steps.findIndex(x => !x[1]);
  $('#onbSteps').innerHTML = steps.map(([text, ok, view], i) => `<li class="${ok ? 'done' : i === next ? 'next' : ''}"><span>${ok ? '✓' : i + 1}</span>${esc(text)}${
    i === next ? (view ? ` <button class="btn small" data-view="${view}">ПЕРЕЙТИ →</button>` : ' <button class="btn small primary" data-run-now="1">▶ ЗАПУСТИТЬ</button>') : ''}</li>`).join('');
}

function renderOverview() {
  const a = S.audit, rep = a.report;
  $('#summaryText').textContent = rep.summary;
  $('#sevLabel').textContent = 'MAX SEVERITY: ' + SEV_LABEL[rep.max_severity];
  $('#summaryChips').innerHTML = Object.entries(rep.counts.confirmed).sort((x, y) => y[1] - x[1])
    .map(([w, n]) => `<span class="tag ${['password', 'breach', 'phone'].includes(w) ? 'bad' : ['real_name', 'city', 'email'].includes(w) ? 'warn' : ''}">${esc(WHAT[w] || w)} × ${n}</span>`).join('');
  renderOnboarding();
  const t = rep.totals;
  $('#progressRow').hidden = !t.actionable;
  if (t.actionable) {
    $('#progressBar').style.width = Math.round(100 * t.resolved / t.actionable) + '%';
    $('#progressText').textContent = `закрыто вами: ${t.resolved} из ${t.actionable}`;
  }
  const d = rep.diff, byId = Object.fromEntries(rep.items.map(i => [i.finding.id, i]));
  $('#diffPanel').hidden = !d;
  if (d) {
    $('#diffMeta').textContent = `ЗАПУСК #${d.run} · ${fmtDate(d.at)}`;
    const rows = [...d.new.map(id => ['new', id]), ...d.gone.map(id => ['gone', id]), ...d.changed.map(id => ['changed', id])]
      .filter(([, id]) => byId[id]);
    $('#diffList').innerHTML = rows.length ? rows.map(([k, id]) => {
      const f = byId[id].finding;
      return `<div class="evidence${k === 'gone' ? ' gone' : ''}" data-ctx="finding" data-id="${esc(id)}"><div class="evi-icon">${{new: '+', gone: '−', changed: '~'}[k]}</div>
        <div><div class="evi-title">${esc(f.value)}</div><div class="evi-source">${esc(FTYPE[f.type] || f.type)} · ${esc(f.source)} ${changeTag(byId[id])}${byId[id].resolved && k === 'gone' ? ' <span class="tag good">ВЫ ЗАКРЫЛИ — ПОДТВЕРЖДЕНО</span>' : ''}</div></div></div>`;
    }).join('') : '<div class="empty-mini">С прошлого аудита ничего не изменилось</div>';
  }
  $('#conflictBox').innerHTML = rep.conflicts.map(c => `<div class="conflict-box">▲ Разные значения поля «город» в источниках — оба показаны, без схлопывания: ${c.values.map(v => `<b>${esc(v.value)}</b> (${esc(v.source)})`).join(', ')}</div>`).join('');

  const pending = a.findings.filter(f => f.status === 'review' || (f.type === 'profile_url' && f.status !== 'confirmed'))
    .sort((x, y) => (x.status === 'review' ? 0 : 1) - (y.status === 'review' ? 0 : 1) || y.confidence - x.confidence);
  $('#reviewCount').textContent = a.findings.filter(f => f.status === 'review').length + ' TO REVIEW';
  $('#reviewList').innerHTML = pending.length ? pending.slice(0, 6).map(f => `
    <div class="candidate" data-ctx="finding" data-id="${esc(f.id)}">
      <div class="avatar" style="color:${scoreColor(f.confidence)}">${esc((f.data.site || f.value).slice(0, 2))}</div>
      <div><div class="candidate-name">${esc(f.value)}</div><div class="candidate-sub">${findingSub(f)}</div>
        <div class="candidate-tags"><span class="tag ${STATUS[f.status][1]}">${STATUS[f.status][0]}</span></div>${reviewButtons(f)}</div>
      <div class="score" style="color:${scoreColor(f.confidence)}">${f.confidence.toFixed(2)}<small>${scoreText(f.confidence)}</small></div>
    </div>`).join('') + (pending.length > 6 ? `<div class="hint" style="padding-top:10px">…и ещё ${pending.length - 6} — во вкладке «Находки»</div>` : '') : `<div class="empty-mini">${a.findings.length ? 'Все находки проверены' : 'Пока нечего проверять — запустите аудит'}</div>`;

  const top = rep.items.filter(i => i.severity > 0).sort((x, y) => x.resolved - y.resolved).slice(0, 6);
  $('#topList').innerHTML = top.length ? top.map(i => `
    <div class="evidence" data-ctx="finding" data-id="${esc(i.finding.id)}"><div class="evi-icon"><span class="sev s${i.severity}">${i.severity}</span></div>
      <div><div class="evi-title">${esc(i.finding.value)} ${i.resolved ? '<span class="tag good">ЗАКРЫТО</span>' : ''}</div><div class="evi-source">${i.exposures.map(e => esc(WHAT[e.what] || e.what)).join(' · ')} — ${esc((i.recommendations[i.resolved ? 1 : 0] || '').slice(0, 110))}</div></div>
      <div class="evi-date">${fmtTime(i.finding.found_at)}</div></div>`).join('') : '<div class="empty-mini">Раскрытий пока нет</div>';

  $('#queueState').textContent = a.running ? 'RUNNING' : 'IDLE';

  $('#queueList').innerHTML = a.modules.map(m => queueRow(m)).join('');
}
function srcState(m) {
  if (!m.enabled) return ['ВЫКЛ', '', '○'];
  if (!m.available) return ['НЕДОСТУПЕН', 'wait', '◷'];
  const st = m.status && m.status.state;
  return {running: ['ВЫПОЛНЯЕТСЯ', 'run', '▶'], queued: ['В ОЧЕРЕДИ', 'wait', '◷'], done: ['ГОТОВО', '', '✓'],
    failed: ['СБОЙ', 'wait', '✕'], skipped: ['ПРОПУЩЕН', 'wait', '◷']}[st] || ['ОЖИДАНИЕ', '', '·'];
}
function queueRow(m) {
  const [label, cls, ico] = srcState(m);
  const detail = !m.available ? m.unavailable_reason : (m.status && m.status.detail) || `${m.input_type} → ${m.outputs.join(', ')}`;
  return `<div class="queue-row"><span class="queue-icon" style="${cls === 'wait' ? 'color:var(--amber)' : ''}">${ico}</span><div>${esc(m.title)}<small>${esc(detail)}</small></div><span class="queue-state ${cls}">${label}</span></div>`;
}

function renderIdentities() {
  const a = S.audit, demo = a.mode === 'demo';
  $('#identCount').textContent = a.identities.length;
  const pf = a.owner_profile;
  if (document.activeElement.closest('#profileForm') == null) {
    $('#pfName').value = pf.full_name; $('#pfCity').value = pf.city; $('#pfPhones').value = pf.phones.join(', ');
  }
  $('#ghLoginBtn').disabled = demo || !S.cfg.github_oauth_configured;
  $('#ghHint').textContent = demo ? 'В учебном режиме подтверждение не выполняется'
    : S.cfg.github_oauth_configured ? 'GitHub-аккаунт, его ник и подтверждённые на GitHub адреса станут подтверждёнными'
      : 'OAuth не настроен: GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET в .env';
  const byId = Object.fromEntries(a.identities.map(i => [i.id, i]));
  const order = [];
  const visit = (i, depth) => { order.push([i, depth]); a.identities.filter(c => c.parent_id === i.id).forEach(c => visit(c, depth + 1)); };
  a.identities.filter(i => !i.parent_id || !byId[i.parent_id]).forEach(i => visit(i, 0));
  $('#identList').innerHTML = order.length ? order.map(([i, depth]) => identRow(i, depth, byId, demo)).join('')
    : '<div class="empty-mini">Добавьте свой email, домен или ник — или войдите через GitHub</div>';
}
function identRow(i, depth, byId, demo) {
  const st = {verified: ['ПОДТВЕРЖДЁН', 'good'], unverified: ['НЕ ПОДТВЕРЖДЁН', 'warn'], expired: ['ПОДТВЕРЖДЕНИЕ ИСТЕКЛО', 'bad']}[i.state];
  const parent = i.parent_id && byId[i.parent_id];
  const how = i.verified_by ? `${verifiedHow(i.verified_by)}${parent ? ' от ' + esc(parent.value) : ''} · ${fmtDate(i.verified_at)}` : 'модули не запускает';
  let actions = '';
  if (!demo && i.state !== 'verified') {
    if (i.type === 'email') {
      actions = S.pendingCode.has(i.id)
        ? `<input class="code-input" maxlength="6" inputmode="numeric" placeholder="000000" data-code-for="${esc(i.id)}"><button class="btn primary small" data-act="email-confirm" data-id="${esc(i.id)}">ПОДТВЕРДИТЬ</button><button class="btn small" data-act="email-start" data-id="${esc(i.id)}">ВЫСЛАТЬ ЕЩЁ РАЗ</button>`
        : `<button class="btn small" data-act="email-start" data-id="${esc(i.id)}">✉ ОТПРАВИТЬ КОД</button>`;
    } else if (i.type === 'domain') {
      actions = `<button class="btn small" data-act="domain-token" data-id="${esc(i.id)}">ПОЛУЧИТЬ TXT-ЗАПИСЬ</button>` +
        (i.verify_token ? `<button class="btn primary small" data-act="domain-check" data-id="${esc(i.id)}">ПРОВЕРИТЬ DNS</button>` : '');
    } else if (i.type === 'username') {
      actions = `<button class="btn small" data-act="username-check" data-id="${esc(i.id)}">ПРОВЕРИТЬ ССЫЛКУ С ДОМЕНА</button>`;
    } else if (i.type === 'github') {
      actions = `<button class="btn small" data-act="github" data-id="${esc(i.id)}">ВОЙТИ ЧЕРЕЗ GITHUB СНОВА</button>`;
    }
  }
  const del = `<button class="btn small danger" data-act="delete" data-id="${esc(i.id)}" title="Удалить вместе с унаследованными">✕</button>`;
  let box = '';
  if (!demo && i.state !== 'verified' && i.type === 'domain' && i.verify_token) {
    box = `<div class="verify-box">Добавьте в DNS домена <b>${esc(i.value)}</b> TXT-запись:<br><code>${esc(S.cfg.txt_prefix + i.verify_token)}</code><br>и нажмите «Проверить DNS». Обновление DNS может занять несколько минут.</div>`;
  } else if (!demo && i.state !== 'verified' && i.type === 'username') {
    box = `<div class="verify-box">Ник подтверждается двумя способами: войдите через GitHub (ваш логин станет подтверждённым ником) или положите на подтверждённый домен файл <code>https://ваш-домен${esc(S.cfg.well_known_path)}</code> со строкой <code>${esc(i.value)}</code>.</div>`;
  }
  return `<div class="ident" style="padding-left:${depth * 18}px">
    <div class="ident-top"><div class="avatar">${esc(TYPE_AV[i.type] || '?')}</div>
      <div><div class="candidate-name">${depth ? '<span class="child-mark">└</span>' : ''}${esc(i.value)}</div>
        <div class="candidate-sub">${TYPE_LABEL[i.type]} · ${how}</div>
        <div class="candidate-tags"><span class="tag ${st[1]}">${st[0]}</span>${i.runs_modules ? '<span class="tag">ЗАПУСКАЕТ ПОИСК</span>' : ''}</div></div>
      <div>${del}</div></div>
    ${actions ? `<div class="ident-actions">${actions}</div>` : ''}${box}</div>`;
}

function renderEvidence() {
  const a = S.audit, f = S.findFilter;
  const exposed = new Set(a.report.items.filter(i => i.exposures.length).map(i => i.finding.id));
  const expMap = Object.fromEntries(a.report.items.map(i => [i.finding.id, i.exposures]));
  const item = Object.fromEntries(a.report.items.map(i => [i.finding.id, i]));
  const match = x => f === 'all' ? !x.gone_at : f === 'exposed' ? exposed.has(x.id) : f === 'gone' ? !!x.gone_at
    : f === 'changes' ? !!(item[x.id] && (item[x.id].change || item[x.id].gone)) : x.status === f && !x.gone_at;
  const rows = a.findings.filter(match)
    .sort((x, y) => (y.found_at || '').localeCompare(x.found_at || ''));
  $('#findCount').textContent = rows.length + ' / ' + a.findings.length;
  $('#findTable').innerHTML = rows.length ? rows.map(x => `
    <tr data-ctx="finding" data-id="${esc(x.id)}" class="${x.gone_at ? 'gone' : ''}"><td>${x.url ? link(x.url, x.value) : esc(x.value)} ${changeTag(item[x.id])}${item[x.id] && item[x.id].resolved ? '<span class="tag good">ЗАКРЫТО</span>' : ''}</td><td>${esc(FTYPE[x.type] || x.type)}</td><td>${esc(x.source)}</td>
      <td>${(expMap[x.id] || []).map(e => esc(WHAT[e.what] || e.what)).join(', ') || '—'}</td><td style="color:${scoreColor(x.confidence)}">${x.confidence.toFixed(2)}</td>
      <td><span class="tag ${STATUS[x.status][1]}">${STATUS[x.status][0]}</span></td><td>${fmtDate(x.found_at)}</td></tr>`).join('')
    : '<tr><td colspan="7" style="text-align:center;color:var(--muted)">Нет находок</td></tr>';
}

function renderReport() {
  const rep = S.audit.report;
  $('#reportSummary').textContent = rep.summary;
  $('#reportItems').innerHTML = rep.items.length ? rep.items.map(i => {
    const f = i.finding;
    if (i.gone && !i.change) return '';
    return `<div class="rep-item s${i.severity}${f.status === 'not_mine' || i.gone ? ' muted' : ''}${i.resolved ? ' resolved' : ''}">
      <div class="rep-head"><div><div class="rep-title">${f.url ? link(f.url, f.value) : esc(f.value)}</div>
        <div class="rep-meta">${esc(FTYPE[f.type] || f.type)} · ${esc(f.source)} · confidence ${f.confidence.toFixed(2)} · ${fmtDate(f.found_at)}</div>
        <div class="candidate-tags">${changeTag(i)}</div></div>
        <span class="sev s${i.severity}">${SEV_LABEL[i.severity]}</span></div>
      ${i.exposures.length ? `<div class="exp-list">${i.exposures.map(e => `<b>${esc(WHAT[e.what] || e.what)}</b>: ${esc(e.detail)}`).join('<br>')}</div>` : ''}
      ${i.recommendations.length ? `<ul class="rep-recs">${i.recommendations.map(r => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
      <div class="review-actions">${resolveButton(i)}${f.type === 'profile_url' || f.status === 'mine' || f.status === 'not_mine' ? reviewButtons(f).replace(/^<div class="review-actions">|<\/div>$/g, '') : ''}</div></div>`;
  }).join('') : '<div class="empty-mini" style="margin-top:12px">Отчёт появится после аудита</div>';
}

function renderSources() {
  const a = S.audit;
  $('#srcCount').textContent = a.modules.length + ' MODULES';
  $('#srcTable').innerHTML = a.modules.map(m => {
    const [label, cls] = srcState(m);
    const tagCls = cls === 'run' ? 'good' : label === 'СБОЙ' ? 'bad' : cls === 'wait' ? 'warn' : '';
    const st = m.status;
    const detail = !m.available ? m.unavailable_reason : st ? `${st.detail || ''}${st.last_run ? ' · ' + fmtDate(st.last_run) : ''}` : '';
    return `<tr><td><input type="checkbox" class="src-toggle" data-mod="${esc(m.name)}" ${m.enabled ? 'checked' : ''} aria-label="Включить ${esc(m.title)}"></td>
      <td><b>${esc(m.title)}</b><div class="hint">${esc(m.description)}</div>${m.warning ? `<div class="warn-note">▲ ${esc(m.warning)}</div>` : ''}</td>
      <td>${esc(m.input_type)} → ${esc(m.outputs.join(', '))}</td>
      <td><span class="tag ${tagCls}">${label}</span><div class="hint">${esc(detail)}</div></td>
      <td><button class="btn small" data-retry="${esc(m.name)}" ${!m.enabled || !m.available || a.running ? 'disabled' : ''}>↻ ПРОВЕРИТЬ ЕЩЁ РАЗ</button></td></tr>`;
  }).join('');
}

function renderTimeline() {
  const a = S.audit, ev = [];
  a.identities.forEach(i => {
    ev.push({at: i.added_at, title: `Добавлен идентификатор ${TYPE_LABEL[i.type]}`, body: i.value, tag: 'ИДЕНТИФИКАТОР'});
    if (i.verified_at) ev.push({at: i.verified_at, title: `Подтверждён: ${i.value}`, body: 'Способ: ' + verifiedHow(i.verified_by), tag: 'ПОДТВЕРЖДЕНИЕ', good: true});
  });
  a.findings.forEach(f => ev.push({at: f.found_at, title: `${FTYPE[f.type] || f.type}: ${f.value}`, body: `Источник: ${f.source}. Статус: ${STATUS[f.status][0].toLowerCase()}.`, tag: f.source, warn: f.status === 'review'}));
  ev.push({at: a.created_at, title: 'Создан аудит ' + a.id, body: a.mode === 'demo' ? 'Учебный режим, синтетические данные.' : 'Аудит собственного следа.', tag: 'АУДИТ'});
  ev.sort((x, y) => (y.at || '').localeCompare(x.at || ''));
  $('#timeline').innerHTML = ev.slice(0, 120).map(e => `<div class="event"><time>${fmtDate(e.at)}</time><strong>${esc(e.title)}</strong><p>${esc(e.body)}</p><div class="candidate-tags"><span class="tag ${e.good ? 'good' : e.warn ? 'warn' : ''}">${esc(e.tag)}</span></div></div>`).join('');
}

function logLines(filter) {
  return S.audit.log.filter(l => filter === 'ALL' || l.level === filter).map(l => {
    const cls = l.level === 'WARN' ? 'term-warn' : l.level === 'ERROR' ? 'term-err' : l.level === 'OK' ? 'term-ok' : 'term-output';
    return `<div class="term-line"><span class="term-time">${fmtTime(l.at)}</span><span class="term-prompt">[${l.level}]</span> <span class="${cls}">${esc(l.text)}</span></div>`;
  }).join('');
}
function renderLogs() {
  const mini = $('#terminalLog'), full = $('#fullTerminal');
  const stick = el => el.scrollHeight - el.scrollTop - el.clientHeight < 40;
  const sm = stick(mini), sf = stick(full);
  mini.innerHTML = logLines(S.logFilter.mini) + `<div class="term-line"><span class="term-prompt">ghost@local:~$</span> <span class="cursor"></span></div>`;
  full.innerHTML = logLines(S.logFilter.full);
  if (sm) mini.scrollTop = mini.scrollHeight;
  if (sf) full.scrollTop = full.scrollHeight;
  $('#logCount').textContent = S.audit.log.length + ' LINES';
  const last = S.audit.log.slice(-6);
  const item = l => `<span class="ticker-item">[${fmtTime(l.at)}] <span class="${l.level === 'OK' ? 'up' : l.level === 'WARN' ? 'warn' : l.level === 'ERROR' ? 'err' : 'info'}">[${l.level}] ${esc(l.text)}</span></span>`;
  $('#ticker').innerHTML = last.map(item).join('') + last.map(item).join('');
}
$$('.log-filters[data-log]').forEach(g => g.addEventListener('click', e => {
  const b = e.target.closest('.log-filter'); if (!b) return;
  $$('.log-filter', g).forEach(x => x.classList.toggle('active', x === b));
  S.logFilter[g.dataset.log] = b.dataset.type; if (S.audit) renderLogs();
}));
$('#findFilters').addEventListener('click', e => {
  const b = e.target.closest('.log-filter'); if (!b) return;
  $$('.log-filter', $('#findFilters')).forEach(x => x.classList.toggle('active', x === b));
  S.findFilter = b.dataset.f; if (S.audit) renderEvidence();
});

/* ---------- actions (delegated) ---------- */
async function review(fid, verdict) {
  const f = S.audit.findings.find(x => x.id === fid);
  const v = f && f.status === verdict ? null : verdict;
  const a = await act(() => api('POST', `/api/audits/${S.audit.id}/findings/${fid}/review`, {verdict: v}),
    v === 'mine' ? 'Отмечено: мой аккаунт' : v === 'not_mine' ? 'Отмечено: не мой — исключено из раскрытий' : 'Отметка снята');
  if (a) setAudit(a);
}
document.addEventListener('click', async e => {
  const rs = e.target.closest('[data-resolve]');
  if (rs) {
    e.stopPropagation();
    const done = rs.dataset.done === '1';
    const a = await act(() => api('POST', `/api/audits/${S.audit.id}/findings/${rs.dataset.resolve}/resolve`, {done}),
      done ? 'Отмечено как закрытое — повторный аудит проверит' : 'Снова открыто');
    if (a) setAudit(a);
    return;
  }
  if (e.target.closest('[data-run-now]')) { runAudit(); return; }
  const rv = e.target.closest('[data-review]');
  if (rv) { e.stopPropagation(); review(rv.dataset.review, rv.dataset.v); return; }
  const ctx = e.target.closest('[data-ctx]');
  if (ctx && !e.target.closest('a,button,input')) { openCtx(ctx.dataset.ctx, ctx.dataset.id); return; }
  const retry = e.target.closest('[data-retry]');
  if (retry) { runAudit(retry.dataset.retry); return; }
  const b = e.target.closest('[data-act]');
  if (!b || !S.audit) return;
  const id = b.dataset.id, base = `/api/audits/${S.audit.id}/identities/${id}`;
  switch (b.dataset.act) {
    case 'email-start':
      if (await act(() => api('POST', base + '/email/start'), 'Код отправлен — проверьте почту')) { S.pendingCode.add(id); renderIdentities(); }
      break;
    case 'email-confirm': {
      const code = ($(`[data-code-for="${CSS.escape(id)}"]`) || {}).value || '';
      const a = await act(() => api('POST', base + '/email/confirm', {code}), 'Email подтверждён');
      if (a) { S.pendingCode.delete(id); setAudit(a); }
      break;
    }
    case 'domain-token': {
      const r = await act(() => api('POST', base + '/domain/token'));
      if (r) refresh();
      break;
    }
    case 'domain-check': {
      const a = await act(() => api('POST', base + '/domain/check'), 'Домен подтверждён');
      if (a) setAudit(a);
      break;
    }
    case 'username-check': {
      const a = await act(() => api('POST', base + '/username/check'), 'Ник подтверждён ссылкой с домена');
      if (a) setAudit(a);
      break;
    }
    case 'github': githubLogin(); break;
    case 'delete': {
      if (!confirm('Удалить идентификатор, всё, что от него унаследовано, и связанные находки? Унаследованный идентификатор не вернётся при следующем аудите.')) return;
      const a = await act(() => api('DELETE', base), 'Удалено');
      if (a) setAudit(a);
      break;
    }
  }
});
document.addEventListener('change', async e => {
  const t = e.target.closest('.src-toggle');
  if (!t || !S.audit) return;
  const a = await act(() => api('PUT', `/api/audits/${S.audit.id}/modules/${t.dataset.mod}`, {enabled: t.checked}), t.checked ? 'Модуль включён' : 'Модуль выключен');
  if (a) setAudit(a);
});
function githubLogin() { if (S.audit) location.href = '/auth/github/start?audit_id=' + encodeURIComponent(S.audit.id); }
$('#ghLoginBtn').addEventListener('click', githubLogin);

$('#identForm').addEventListener('submit', async e => {
  e.preventDefault(); if (!S.audit) return;
  const type = $('#identType').value, value = $('#identValue').value.trim();
  if (!value) { notify('Введите значение'); return; }
  const a = await act(() => api('POST', `/api/audits/${S.audit.id}/identities`, {type, value}), 'Добавлено — теперь подтвердите владение');
  if (a) { $('#identValue').value = ''; setAudit(a); }
});
$('#identType').addEventListener('change', () => {
  $('#identValue').placeholder = {email: 'you@example.com', domain: 'example.com', username: 'my_nickname'}[$('#identType').value];
});
$('#profileForm').addEventListener('submit', async e => {
  e.preventDefault(); if (!S.audit) return;
  const body = {full_name: $('#pfName').value, city: $('#pfCity').value, phones: $('#pfPhones').value.split(',').map(x => x.trim()).filter(Boolean)};
  const a = await act(() => api('PUT', `/api/audits/${S.audit.id}/profile`, body), 'Эталон сохранён — сверка пересчитана');
  if (a) { document.activeElement.blur(); setAudit(a); }
});

async function runAudit(module) {
  if (!S.audit) return;
  const a = await act(() => api('POST', `/api/audits/${S.audit.id}/run`, {module: module || null}), module ? 'Повторная проверка источника' : 'Аудит запущен');
  if (a) { setAudit(a); if (!module && S.view === 'identities') showView('case'); }
}
$('#runBtn').addEventListener('click', () => runAudit());
$('#newRealBtn').addEventListener('click', () => newAudit('real'));
const doExport = fmt => {
  if (!S.audit) return;
  if (window.HS_EXPORT) { window.HS_EXPORT(S.audit, fmt); return; }  // онлайн-демо без сервера
  location.href = `/api/audits/${S.audit.id}/export${fmt === 'html' ? '.html' : ''}`;
};
['#exportBtn', '#exportBtn2', '#exportBtn4'].forEach(s => $(s).addEventListener('click', () => doExport('html')));
$('#exportBtn3').addEventListener('click', () => doExport('json'));
$('#scheduleSel').addEventListener('change', async e => {
  if (!S.audit) return;
  const hours = e.target.value ? Number(e.target.value) : null;
  const a = await act(() => api('PUT', `/api/audits/${S.audit.id}/schedule`, {hours}), hours ? `Повторный аудит каждые ${hours} ч` : 'Расписание выключено');
  if (a) setAudit(a); else e.target.value = S.audit.schedule_hours ? String(S.audit.schedule_hours) : '';
});
$('#saveToggle').addEventListener('change', async e => {
  if (!S.audit) return;
  const a = await act(() => api('PUT', `/api/audits/${S.audit.id}/save`, {save: e.target.checked}), e.target.checked ? 'Аудит сохраняется на диск' : 'Файл аудита удалён, данные только в памяти');
  if (a) setAudit(a);
});
$('#deleteAuditBtn').addEventListener('click', async () => {
  if (!S.audit || !confirm('Удалить этот аудит (и его файл, если он сохранён)?')) return;
  if (await act(() => api('DELETE', `/api/audits/${S.audit.id}`), 'Аудит удалён')) { setAudit(null); loadList(); showView('start'); }
});
$('#wipeBtn').addEventListener('click', async () => {
  if (!confirm('Удалить ВСЕ аудиты из памяти и с диска? Это нельзя отменить.')) return;
  if (await act(() => api('DELETE', '/api/data'), 'Все данные удалены')) { setAudit(null); loadList(); showView('start'); }
});

/* ---------- context panel ---------- */
const shellEl = $('#shell');
function openCtx(kind, id, silent) {
  const a = S.audit; if (!a) return;
  let h = '';
  if (kind === 'finding') {
    const item = a.report.items.find(i => i.finding.id === id); if (!item) { closeCtx(); return; }
    const f = item.finding, ident = a.identities.find(i => i.id === f.identity_id);
    h = `<div class="ctx-title">${esc(f.value)}</div><div class="ctx-sub">${esc(FTYPE[f.type] || f.type)}${f.url ? '<br>' + link(f.url) : ''}</div>`;
    [['Источник', f.source], ['Confidence', f.confidence.toFixed(2) + ' — ' + scoreText(f.confidence).toLowerCase()], ['Статус', STATUS[f.status][0]],
      ['Severity', SEV_LABEL[item.severity]], ['Найдено', fmtDate(f.found_at)], ['По идентификатору', ident ? ident.value : '—']]
      .forEach(([k, v]) => { h += `<div class="ctx-row"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`; });
    Object.entries(f.data || {}).forEach(([k, v]) => {
      if (v == null || v === '' || (Array.isArray(v) && !v.length)) return;
      const val = typeof v === 'object' ? (Array.isArray(v) ? v.join(', ') : Object.entries(v).map(([a2, b2]) => `${a2}: ${b2}`).join('; ')) : v;
      h += `<div class="ctx-row"><span class="k">${esc(k)}</span><span class="v">${esc(val)}</span></div>`;
    });
    if (item.exposures.length) h += `<div class="section-title" style="margin-top:14px">ЧТО РАСКРЫТО</div><div class="exp-list">${item.exposures.map(e => `<b>${esc(WHAT[e.what] || e.what)}</b>: ${esc(e.detail)}`).join('<br>')}</div>`;
    if (item.recommendations.length) h += `<div class="section-title" style="margin-top:14px">ЧТО СДЕЛАТЬ</div><ul class="rep-recs">${item.recommendations.map(r => `<li>${esc(r)}</li>`).join('')}</ul>`;
    if (item.gone) h += `<div class="conflict-box">Не найдено при последней проверке источника${item.resolved ? ' — вы закрыли это, и аудит подтвердил' : ''}.</div>`;
    if (resolveButton(item)) h += `<div class="section-title" style="margin-top:14px">ЧЕК-ЛИСТ</div><div class="review-actions">${resolveButton(item)}</div>`;
    h += `<div class="section-title" style="margin-top:14px">ВАШ ЛИ ЭТО АККАУНТ?</div>${reviewButtons(f)}`;
    if (f.type === 'profile_url') h += `<div class="hint">После «мой» сайт прочитает только эту страницу и проверит, видно ли на ней ваше имя и город.</div>`;
    h += `<div class="ctx-actions"><button class="btn" data-retry="${esc(f.source)}" ${a.running ? 'disabled' : ''}>↻ ПРОВЕРИТЬ ИСТОЧНИК ЕЩЁ РАЗ</button><button class="btn small" data-goto="graph">В ГРАФ</button></div>`;
  } else if (kind === 'identity') {
    const i = a.identities.find(x => x.id === id); if (!i) { closeCtx(); return; }
    const n = a.findings.filter(f => f.identity_id === i.id).length;
    h = `<div class="ctx-title">${esc(i.value)}</div><div class="ctx-sub">${TYPE_LABEL[i.type]} · мой идентификатор</div>`;
    [['Состояние', i.state], ['Подтверждён', verifiedHow(i.verified_by) || '—'], ['Когда', fmtDate(i.verified_at)], ['Находок', n]]
      .forEach(([k, v]) => { h += `<div class="ctx-row"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`; });
    h += `<div class="ctx-actions"><button class="btn small" data-goto="identities">К ИДЕНТИФИКАТОРАМ</button></div>`;
  } else { closeCtx(); return; }
  S.ctx = {kind, id};
  shellEl.classList.add('with-ctx');
  const body = $('#ctxBody'); body.innerHTML = h;
  $$('[data-goto]', body).forEach(b => b.addEventListener('click', () => { showView(b.dataset.goto); if (window.innerWidth <= 900) closeCtx(); }));
  $$('[data-ctx]').forEach(el => el.classList.toggle('selected', el.dataset.id === id));
  if (!silent) { $('#ctxPanel').classList.add('sheet-open'); if (window.innerWidth <= 900) $('#ctxBackdrop').classList.add('show'); }
}
function closeCtx() {
  S.ctx = null; shellEl.classList.remove('with-ctx');
  $('#ctxBody').innerHTML = '<div class="ctx-empty">Выберите находку<br>или узел графа</div>';
  $$('[data-ctx]').forEach(el => el.classList.remove('selected'));
  $('#ctxPanel').classList.remove('sheet-open'); $('#ctxBackdrop').classList.remove('show');
}
$('#ctxClose').addEventListener('click', closeCtx);
$('#ctxBackdrop').addEventListener('click', closeCtx);
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeCtx(); openMenu(false); closeTheme(); } });

/* ---------- graph: я → идентификаторы → где видны ---------- */
const graph = (() => {
  const C = [1200, 1200];
  let pos = {}, camX = 0, camY = 0, camScale = 1, data = {nodes: [], edges: []}, expanded = null, lastSig = '';
  const world = $('#graphWorld'), viewport = $('#graphViewport'), svg = $('#graphCardsSvg');

  function layout(g) {
    pos = {me: C};
    const ids = g.nodes.filter(n => n.kind === 'identity');
    const children = {};
    g.edges.forEach(e => { (children[e.from] = children[e.from] || []).push(e.to); });
    const R1 = 230;
    ids.forEach((n, i) => {
      const ang = (i / Math.max(ids.length, 1)) * Math.PI * 2 - Math.PI / 2;
      pos[n.id] = [C[0] + Math.cos(ang) * R1 * 1.4, C[1] + Math.sin(ang) * R1];
      const fs = (children[n.id] || []).filter(id => g.nodes.find(x => x.id === id && x.kind === 'finding'));
      const spread = Math.min(Math.PI * 1.6 / Math.max(ids.length, 1), 1.4);
      fs.forEach((fid, j) => {
        const ring = j % 2, k = fs.length > 1 ? j / (fs.length - 1) - 0.5 : 0;
        const a2 = ang + k * spread * (fs.length > 6 ? 1.6 : 1);
        const r = R1 + 170 + ring * 90 + Math.floor(j / 8) * 50;
        pos[fid] = [C[0] + Math.cos(a2) * r * 1.45, C[1] + Math.sin(a2) * r];
      });
    });
  }
  const Y = 24;
  function drawEdges() {
    const show = Object.fromEntries($$('[data-filter]').map(cb => [cb.dataset.filter, cb.checked]));
    svg.innerHTML = data.edges.map(e => {
      const a = pos[e.from], b = pos[e.to]; if (!a || !b) return '';
      return `<line class="edge${e.link === 'confirmed' ? ' solid' : ''}${e.link === 'conflict' ? ' conflict' : ''}${show[e.link] === false ? ' hidden' : ''}" x1="${a[0]}" y1="${a[1] + Y}" x2="${b[0]}" y2="${b[1] + Y}"></line>`;
    }).join('');
  }
  function cardHtml(n) {
    if (n.kind === 'me') return `<div class="g-type">Я</div><div class="g-title">${esc(n.label)}</div>`;
    if (n.kind === 'identity') return `<div class="g-type">${esc(TYPE_LABEL[n.sub] || n.sub)} · ${n.state === 'verified' ? '✓' : '?'}</div><div class="g-title">${esc(n.label)}</div>`;
    return `<div class="g-type">${esc(FTYPE[n.sub] || n.sub)}${n.severity ? ' · S' + n.severity : ''}</div><div class="g-title">${esc(n.label)}</div>`;
  }
  function render(g) {
    data = g;
    const sig = JSON.stringify(g);
    $('#graphCount').textContent = `${g.nodes.length} NODES · ${g.edges.length} EDGES`;
    $('#graphEmpty').classList.toggle('show', g.nodes.length <= 1);
    if (sig === lastSig) return;
    lastSig = sig;
    layout(g);
    $$('.gcard', world).forEach(c => c.remove());
    g.nodes.forEach(n => {
      const card = document.createElement('div');
      const p = pos[n.id] || C;
      card.className = 'gcard ' + n.kind + (n.kind === 'me' ? ' main' : '') +
        (n.kind === 'identity' && n.state !== 'verified' ? ' unverified' : '') +
        (n.kind === 'finding' ? ` ${n.status} sev${n.severity}` : '') + (expanded === n.id ? ' expanded' : '');
      card.dataset.node = n.id;
      card.style.left = p[0] + 'px'; card.style.top = p[1] + 'px';
      card.innerHTML = cardHtml(n);
      card.addEventListener('click', ev => {
        ev.stopPropagation();
        $('#nodeInfo').innerHTML = `<strong>${esc(n.label)}</strong><br><span style="color:var(--muted)">${esc(n.kind === 'finding' ? (FTYPE[n.sub] || n.sub) + ' · ' + n.source + (n.exposes.length ? ' · раскрывает: ' + n.exposes.map(w => WHAT[w] || w).join(', ') : '') : n.kind === 'identity' ? (TYPE_LABEL[n.sub] + ' · ' + (n.state === 'verified' ? 'подтверждён' : 'не подтверждён')) : 'владелец аудита')}</span>`;
        $$('.gcard', world).forEach(c => c.classList.toggle('expanded', c === card));
        expanded = n.id;
        if (n.kind === 'finding' || n.kind === 'identity') openCtx(n.kind, n.id);
      });
      world.appendChild(card);
    });
    drawEdges();
  }
  function apply() {
    world.style.transform = `translate(${camX}px,${camY}px) scale(${camScale})`;
    const gs = 28 * camScale; viewport.style.backgroundSize = gs + 'px ' + gs + 'px';
    viewport.style.backgroundPosition = (camX % gs) + 'px ' + (camY % gs) + 'px';
  }
  function center() {
    const st = $('#graphStage2d'); const w = st.clientWidth || 320, h = st.clientHeight || 440;
    const pts = Object.values(pos);
    let minX = C[0], maxX = C[0], minY = C[1], maxY = C[1];
    pts.forEach(([x, y]) => { minX = Math.min(minX, x - 80); maxX = Math.max(maxX, x + 80); minY = Math.min(minY, y); maxY = Math.max(maxY, y + 60); });
    camScale = Math.max(0.55, Math.min(1, Math.min(w / (maxX - minX + 40), h / (maxY - minY + 40))));
    camX = w / 2 - ((minX + maxX) / 2) * camScale; camY = h / 2 - ((minY + maxY) / 2) * camScale;
    apply();
  }
  let drag = false, sx = 0, sy = 0, scx = 0, scy = 0, pinch = 0, pinchScale = 1;
  const start = (x, y, t) => { if (t.closest && t.closest('.gcard')) return; drag = true; sx = x; sy = y; scx = camX; scy = camY; viewport.style.cursor = 'grabbing'; };
  const move = (x, y) => { if (!drag) return; camX = scx + (x - sx); camY = scy + (y - sy); apply(); };
  const end = () => { drag = false; viewport.style.cursor = 'grab'; };
  viewport.addEventListener('mousedown', e => start(e.clientX, e.clientY, e.target));
  window.addEventListener('mousemove', e => move(e.clientX, e.clientY));
  window.addEventListener('mouseup', end);
  viewport.addEventListener('touchstart', e => {
    if (e.touches.length === 1) start(e.touches[0].clientX, e.touches[0].clientY, e.target);
    else if (e.touches.length === 2) { drag = false; pinch = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); pinchScale = camScale; }
  }, {passive: true});
  viewport.addEventListener('touchmove', e => {
    if (e.touches.length === 1) move(e.touches[0].clientX, e.touches[0].clientY);
    else if (e.touches.length === 2) { const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); camScale = Math.max(.25, Math.min(2.2, pinchScale * (d / (pinch || d)))); apply(); }
  }, {passive: true});
  viewport.addEventListener('touchend', end);
  viewport.addEventListener('wheel', e => { e.preventDefault(); camScale = Math.max(.25, Math.min(2.2, camScale + (e.deltaY > 0 ? -0.08 : 0.08))); apply(); }, {passive: false});
  $('#zoomIn').addEventListener('click', () => { camScale = Math.min(2.2, camScale + 0.15); apply(); });
  $('#zoomOut').addEventListener('click', () => { camScale = Math.max(.25, camScale - 0.15); apply(); });
  $('#zoomReset').addEventListener('click', center);
  $$('[data-filter]').forEach(cb => cb.addEventListener('change', drawEdges));
  const fsBtn = $('#toggleFullscreen');
  function fs() {
    const body = $('#graphPanelBody'); const on = !body.classList.contains('is-fullscreen');
    body.classList.toggle('is-fullscreen', on); fsBtn.textContent = on ? '✕ ВЫЙТИ' : '⛶ НА ВЕСЬ ЭКРАН';
    document.body.style.overflow = on ? 'hidden' : ''; setTimeout(center, 30);
  }
  fsBtn.addEventListener('click', fs); $('#fsExitBtn').addEventListener('click', fs);
  document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('#graphPanelBody').classList.contains('is-fullscreen')) fs(); });
  window.addEventListener('resize', () => { if (S.view === 'graph') center(); });
  return {render, center};
})();

/* ---------- normalize ---------- */
$('#normalizeBtn').addEventListener('click', async () => {
  const value = $('#normInput').value.trim(); if (!value) { notify('Введите значение'); return; }
  const r = await act(() => api('POST', '/api/normalize', {value})); if (!r) return;
  const out = $('#normResults'); out.className = '';
  out.innerHTML = Object.entries(r.variants).map(([k, v]) => `<div class="norm-row"><div class="k">${esc(k)}</div><span class="v">${esc(v)}</span></div>`).join('') +
    '<div class="ascii-note">Варианты — техника сравнения при сверке с профилем «это я», а не доказательство совпадения аккаунтов.</div>';
});
$('#clearNorm').addEventListener('click', () => { $('#normInput').value = ''; const o = $('#normResults'); o.className = 'empty-ascii'; o.textContent = 'Введите значение и запустите нормализацию.'; });

/* ---------- assistant: Anthropic API с согласия, иначе заготовки по ключевым словам ---------- */
function assistantLive() {
  const a = S.audit;
  return !!(S.cfg && S.cfg.assistant_configured && a && (a.mode === 'demo' || a.assistant_consent));
}
function renderAssistantMode() {
  const a = S.audit, cfgOk = S.cfg && S.cfg.assistant_configured;
  $('#assistantMode').textContent = assistantLive() ? 'ANTHROPIC API' : 'ЗАГОТОВКИ';
  $('#assistantConsentRow').hidden = !cfgOk || !a || a.mode === 'demo';
  if (a) $('#assistantConsent').checked = !!a.assistant_consent;
  $('#assistantNote').textContent = cfgOk
    ? 'Объясняет находки и подсказывает, как закрыть утечку. С вашего согласия отвечает через Anthropic API на основе сводки отчёта.'
    : 'Объясняет находки и подсказывает, как закрыть утечку. Сейчас — заготовки по ключевым словам; добавьте ANTHROPIC_API_KEY в .env, чтобы подключить Claude.';
}
(() => {
  const RULES = [
    {k: ['утечк', 'breach', 'pwned', 'парол'], a: 'Если адрес в утечке с паролем: смените пароль на этом сервисе и везде, где он повторялся, включите 2FA, заведите менеджер паролей. Утечки без паролей — повод ждать фишинга на этот адрес.'},
    {k: ['коммит', 'commit', 'git', 'noreply'], a: 'Email в публичных коммитах: включите на GitHub «Keep my email addresses private», настройте git на noreply-адрес. Старые коммиты можно переписать через git filter-repo --mailmap, но форки и клоны сохранят историю.'},
    {k: ['ник', 'username', 'maigret', 'чужой', 'не мой'], a: 'Maigret находит сайты, где занят такой же ник — у популярных ников это часто чужие аккаунты. Отметьте «мой / не мой»: «не мой» исключается из раскрытий, «мой» попадает в рекомендации.'},
    {k: ['confidence', 'уверенн'], a: 'Confidence — насколько вероятно, что аккаунт ваш, а не «тот ли это человек». Уникальный длинный ник с цифрами даёт высокий confidence, короткое словарное слово — низкий.'},
    {k: ['подтвер', 'verify', 'txt', 'oauth', 'код'], a: 'Email — код из письма (SMTP в .env), GitHub — вход через OAuth, домен — TXT-запись hidenseek-verify=…, ник — от GitHub или файлом /.well-known/hidenseek.txt на подтверждённом домене. Телефон, ФИО и город не подтверждаются и поиск не запускают.'},
    {k: ['holehe', 'сервис', 'аккаунт', 'забыт'], a: 'Holehe показывает, на каких сервисах зарегистрирована ваша почта. Ненужные аккаунты лучше удалить, нужные — защитить уникальным паролем и 2FA.'},
    {k: ['домен', 'поддомен', 'crt', 'сертификат'], a: 'crt.sh показывает поддомены из журналов сертификатов — они публичны навсегда. Проверьте, что на старых поддоменах нет забытых админок и тестовых сервисов.'},
    {k: ['граф', 'graph'], a: 'Граф строится только от вас: я → мои идентификаторы → где они видны. Пунктир — находка на проверке, красный — «не мой». Связей с другими людьми граф не строит.'},
    {k: ['хран', 'удал', 'диск', 'данн'], a: 'Без отметки «сохранить аудит» на диск ничего не пишется. В «Настройках и данных» — полная выгрузка JSON и удаление всего одной кнопкой.'},
    {k: ['привет', 'hello', 'хай'], a: 'Привет. Спроси про утечки, коммиты, ники, подтверждение или хранение данных.'},
  ];
  const log = $('#assistantLog'), history = [];
  function add(text, who) {
    const d = document.createElement('div'); d.className = 'msg' + (who === 'user' ? ' user' : who === 'wait' ? ' wait' : '');
    d.textContent = text; log.appendChild(d); log.scrollTop = log.scrollHeight; return d;
  }
  const rules = text => {
    const low = text.toLowerCase(), hit = RULES.find(r => r.k.some(k => low.includes(k)));
    return hit ? hit.a : 'Отвечаю по заготовленным правилам. Спроси про утечки, коммиты, ник, confidence, подтверждение или хранение.';
  };
  $('#assistantForm').addEventListener('submit', async e => {
    e.preventDefault(); const inp = $('#assistantInput'), text = inp.value.trim(); if (!text) return;
    add(text, 'user'); inp.value = '';
    if (!assistantLive()) { setTimeout(() => add(rules(text)), 200); return; }
    const wait = add('думаю…', 'wait');
    try {
      const r = await api('POST', `/api/audits/${S.audit.id}/assistant`, {message: text, history: history.slice(-12)});
      wait.remove(); add(r.answer);
      history.push({role: 'user', content: text}, {role: 'assistant', content: r.answer});
    } catch (err) {
      wait.remove(); add('✕ ' + err.message + '\n\nПо заготовкам: ' + rules(text));
    }
  });
  $('#assistantConsent').addEventListener('change', async ev => {
    if (!S.audit) return;
    const a = await act(() => api('PUT', `/api/audits/${S.audit.id}/assistant-consent`, {consent: ev.target.checked}),
      ev.target.checked ? 'Ассистент будет отвечать через Anthropic API' : 'Согласие отозвано — только заготовки');
    if (a) setAudit(a);
  });
  add('На связи. Спроси, что делать с находкой: утечка, email в коммитах, занятый ник, забытый аккаунт.');
})();

/* ---------- theme ---------- */
const themeBtn = $('#themeBtn'), themePanel = $('#themePanel');
function closeTheme() { themePanel.classList.remove('open'); }
function applyTheme(t) {
  document.body.classList.remove('theme-mono', 'theme-crt', 'theme-clean');
  if (t !== 'wired') document.body.classList.add('theme-' + t);
  $$('.theme-opt').forEach(o => o.classList.toggle('active', o.dataset.theme === t));
  $('#settingsTheme').textContent = t.toUpperCase();
}
themeBtn.addEventListener('click', e => { e.stopPropagation(); themePanel.classList.toggle('open'); });
document.addEventListener('click', e => { if (!themePanel.contains(e.target) && e.target !== themeBtn) closeTheme(); });
$$('.theme-opt').forEach(o => o.addEventListener('click', () => { applyTheme(o.dataset.theme); lsSet('hs_theme', o.dataset.theme); closeTheme(); notify('Visual mode: ' + o.dataset.theme.toUpperCase()); }));
applyTheme(['wired', 'mono', 'crt', 'clean'].includes(lsGet('hs_theme')) ? lsGet('hs_theme') : 'wired');
$('#langBtn').addEventListener('click', () => notify('English UI is planned; HidenSeek is RU-first for now.'));

/* ---------- boot ---------- */
(async () => {
  try { await loadConfig(); } catch (e) { notify('✕ API недоступен: ' + e.message); return; }
  const params = new URLSearchParams(location.search);
  if (params.get('verify_error')) notify('✕ ' + params.get('verify_error'));
  const id = params.get('audit') || window.HS_BOOT_AUDIT || lsGet('hs_audit');
  if (params.has('audit') || params.has('verify_error')) history.replaceState(null, '', location.pathname + location.hash);
  if (id) await openAudit(id);
  await loadList();
  render();
  showView((location.hash || '').slice(1) || (S.audit ? 'case' : 'start'), {push: false});
})();
