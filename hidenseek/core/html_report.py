"""Отчёт в виде одного HTML-файла: можно сохранить, открыть офлайн или распечатать."""
from __future__ import annotations

from datetime import datetime
from html import escape

from .models import Audit

WHAT = {"password": "пароль", "breach": "утечка", "phone": "телефон", "real_name": "имя", "city": "город",
        "email": "почта", "account": "аккаунт", "username": "ник", "subdomain": "поддомен"}
FTYPE = {"profile_url": "профиль на сайте", "registered_service": "аккаунт на сервисе", "breach": "утечка",
         "public_email_in_commits": "email в коммитах", "profile_fields": "поля профиля", "subdomain": "поддомен",
         "certificate": "сертификаты"}
STATUS = {"confirmed": "подтверждено", "review": "проверьте: ваш ли?", "mine": "мой", "not_mine": "не мой"}
SEV = {4: "критично", 3: "высокая", 2: "средняя", 1: "низкая", 0: "инфо"}

CSS = """
:root{--bg:#f6f7f4;--fg:#18201a;--muted:#5d6b60;--line:#d5dbd3;--card:#fff;--s4:#b3261e;--s3:#c4532c;--s2:#a8740c;--s1:#2f7d46;--accent:#1d6b35}
@media (prefers-color-scheme:dark){:root{--bg:#070a08;--fg:#d3dfd5;--muted:#93a599;--line:#203127;--card:#0b100d;--s4:#ff706d;--s3:#ff9a6d;--s2:#e5bb69;--s1:#8cff9e;--accent:#00ff41}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:860px;margin:0 auto;padding:32px max(16px,env(safe-area-inset-left))}
h1{font-size:28px;margin:0 0 4px;letter-spacing:-.02em}h2{font-size:15px;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin:32px 0 8px}
.mono,.meta,.sev{font-family:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace}
.meta{color:var(--muted);font-size:12px}.summary{font-size:17px;margin:16px 0}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin:16px 0}
.stat{border:1px solid var(--line);background:var(--card);padding:10px 12px}.stat b{display:block;font-size:22px}
.item{border:1px solid var(--line);border-left:4px solid var(--line);background:var(--card);padding:12px 14px;margin:10px 0;break-inside:avoid}
.item.s4{border-left-color:var(--s4)}.item.s3{border-left-color:var(--s3)}.item.s2{border-left-color:var(--s2)}.item.s1{border-left-color:var(--s1)}
.item.muted{opacity:.55}.head{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
.title{font-weight:600;overflow-wrap:anywhere}.sev{font-size:12px;white-space:nowrap}
.sev.s4{color:var(--s4)}.sev.s3{color:var(--s3)}.sev.s2{color:var(--s2)}.sev.s1{color:var(--s1)}
ul{margin:8px 0 0;padding-left:20px}li{margin:2px 0}.tag{font-size:11px;border:1px solid var(--line);padding:1px 6px;margin-right:4px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
a{color:var(--accent)}footer{margin-top:40px;color:var(--muted);font-size:12px}
@media print{body{background:#fff;color:#000}.item{border-color:#999}}
"""


def _date(iso: str | None) -> str:
    if not iso:
        return "—"
    return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")


def render(audit: Audit, report: dict, settings_ttl: int) -> str:
    e = escape
    t = report["totals"]
    out = [f"<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
           f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
           f"<title>HidenSeek — отчёт {e(audit.id)}</title><style>{CSS}</style></head><body><main>"]
    who = audit.owner_profile.full_name or "владелец аудита"
    out.append(f"<div class='meta'>HIDENSEEK / SELF-AUDIT / {e(audit.id)}{' / УЧЕБНЫЙ РЕЖИМ' if audit.mode == 'demo' else ''}</div>")
    out.append(f"<h1>Мой цифровой след: {e(who)}</h1>")
    out.append(f"<div class='meta'>Сформирован {datetime.now().strftime('%d.%m.%Y %H:%M')} · запусков: {t['runs']}</div>")
    out.append(f"<p class='summary'>{e(report['summary'])}</p>")
    out.append("<div class='stats'>" + "".join(
        f"<div class='stat'><b>{v}</b><span class='meta'>{k}</span></div>" for k, v in [
            ("находок", t["findings"]), ("раскрытий", t["exposures"]), ("на проверке", t["review"]),
            ("закрыто вами", f"{t['resolved']}/{t['actionable']}"), ("исчезло", t["gone"])]) + "</div>")

    diff = report.get("diff")
    if diff:
        out.append(f"<h2>Изменения с прошлого аудита</h2><p class='meta'>запуск #{diff['run']} · {_date(diff['at'])}: "
                   f"новых {len(diff['new'])}, исчезло {len(diff['gone'])}, изменилось {len(diff['changed'])}</p>")

    out.append("<h2>Что закрыть</h2>")
    for it in report["items"]:
        f = it["finding"]
        if not it["severity"] and not it["gone"]:
            continue
        cls = f"item s{it['severity']}" + (" muted" if it["gone"] else "")
        title = e(f["value"])
        if f.get("url") and str(f["url"]).startswith(("http://", "https://")):
            title = f"<a href='{e(f['url'])}' rel='noopener noreferrer'>{title}</a>"
        tags = "".join(f"<span class='tag'>{e(x)}</span>" for x in filter(None, [
            "исчезло" if it["gone"] else None, "закрыто вами" if it["resolved"] else None,
            {"new": "новое", "changed": "изменилось"}.get(it.get("change") or "")]))
        out.append(f"<div class='{cls}'><div class='head'><div><div class='title'>{title}</div>"
                   f"<div class='meta'>{e(FTYPE.get(f['type'], f['type']))} · {e(f['source'])} · "
                   f"{e(STATUS[f['status']])} · confidence {f['confidence']:.2f} · найдено {_date(f['found_at'])}</div>"
                   f"<div>{tags}</div></div><span class='sev s{it['severity']}'>{SEV[it['severity']]}</span></div>")
        if it["exposures"]:
            out.append("<ul>" + "".join(f"<li><b>{e(WHAT.get(x['what'], x['what']))}</b>: {e(x['detail'])}</li>"
                                        for x in it["exposures"]) + "</ul>")
        if it["recommendations"]:
            out.append("<ul>" + "".join(f"<li>{e(r)}</li>" for r in it["recommendations"]) + "</ul>")
        out.append("</div>")

    out.append("<h2>Идентификаторы</h2><table><tr><th>Тип</th><th>Значение</th><th>Подтверждение</th></tr>")
    for i in audit.identities:
        state = "подтверждён" if audit.is_verified(i, settings_ttl) else i.verification_state(settings_ttl)
        out.append(f"<tr><td>{e(i.type.value)}</td><td class='mono'>{e(i.value)}</td>"
                   f"<td>{e(state)}{' · ' + e(i.verified_by) if i.verified_by else ''}</td></tr>")
    out.append("</table>")
    out.append("<footer>HidenSeek — локальный аудит собственного цифрового следа. Файл создан на вашей машине; "
               "в нём ваши данные — храните его как личный документ.</footer></main></body></html>")
    return "".join(out)
