"""ИИ-ассистент: объясняет находки и подсказывает, как закрыть утечку (Anthropic API).

Работает только с ANTHROPIC_API_KEY и только после явного согласия в аудите: вопрос и
сводка отчёта уходят в Anthropic. Перед отправкой адреса почты и телефоны маскируются,
ФИО из профиля «это я» не отправляется. Учебный режим (синтетические данные) согласия не требует.
"""
from __future__ import annotations

import re
from typing import Optional

from ..config import Settings

SYSTEM = """Ты — помощник в HidenSeek, локальном инструменте аудита СОБСТВЕННОГО цифрового следа.
Пользователь проверяет, что видно о нём самом, и хочет понять, что закрыть.
Отвечай по-русски, коротко и по делу: что раскрыто, чем это грозит и какие конкретные шаги сделать
(настройки сервиса, удаление аккаунта, смена пароля, 2FA, git filter-repo / .mailmap / noreply-адрес GitHub).
Опирайся на сводку отчёта ниже. Если в отчёте нет ответа, так и скажи.
Не помогай искать информацию о других людях и не предлагай способы это сделать — это вне назначения инструмента."""

MAX_HISTORY = 12
MAX_QUESTION = 2000

EMAIL_RE = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
PHONE_RE = re.compile(r"\+?\d[\d\s()\-]{8,}\d")


class AssistantError(Exception):
    pass


def mask(text: str) -> str:
    text = EMAIL_RE.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)
    return PHONE_RE.sub(lambda m: _mask_digits(m.group(0)), text)


def _mask_digits(phone: str, keep: int = 2) -> str:
    """Оставить только последние цифры номера: +7 900 123-45-67 → +• ••• •••-••-67."""
    left = sum(c.isdigit() for c in phone) - keep
    out = []
    for c in phone:
        if c.isdigit() and left > 0:
            out.append("•")
            left -= 1
        else:
            out.append(c)
    return "".join(out)


def report_context(report: dict, limit: int = 25) -> str:
    lines = [f"Сводка: {report['summary']}"]
    for it in report["items"][:limit]:
        f = it["finding"]
        if it.get("gone"):
            continue
        exps = "; ".join(f"{e['what']}: {e['detail']}" for e in it["exposures"]) or "—"
        state = f["status"] + (", закрыто пользователем" if it.get("resolved") else "")
        lines.append(f"- [{it['severity_label']}] {f['type']} «{f['value']}» (источник {f['source']}, {state}). "
                     f"Раскрыто: {exps}")
    return mask("\n".join(lines))


def configured(settings: Settings) -> bool:
    return bool(settings.anthropic_api_key)


async def ask(settings: Settings, report: dict, question: str, history: Optional[list[dict]] = None) -> str:
    import anthropic

    question = (question or "").strip()[:MAX_QUESTION]
    if not question:
        raise AssistantError("Пустой вопрос")
    messages = []
    for h in (history or [])[-MAX_HISTORY:]:
        if h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str) and h["content"].strip():
            messages.append({"role": h["role"], "content": mask(h["content"][:MAX_QUESTION])})
    while messages and messages[0]["role"] != "user":
        messages.pop(0)
    messages.append({"role": "user", "content": mask(question)})

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    try:
        response = await client.beta.messages.create(
            model=settings.assistant_model,
            max_tokens=4000,
            system=[{"type": "text", "text": SYSTEM},
                    {"type": "text", "text": "Отчёт пользователя:\n" + report_context(report)}],
            messages=messages,
            output_config={"effort": "low"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.AuthenticationError as e:
        raise AssistantError("Anthropic отклонил ключ — проверьте ANTHROPIC_API_KEY") from e
    except anthropic.RateLimitError as e:
        raise AssistantError("Превышен лимит запросов к Anthropic — попробуйте через минуту") from e
    except anthropic.BadRequestError as e:
        raise AssistantError(f"Запрос отклонён: {e.message}") from e
    except anthropic.APIStatusError as e:
        raise AssistantError(f"Ошибка Anthropic API ({e.status_code})") from e
    except anthropic.APIConnectionError as e:
        raise AssistantError("Нет связи с Anthropic API") from e
    finally:
        await client.close()

    if response.stop_reason == "refusal":
        raise AssistantError("Модель отказалась отвечать на этот вопрос")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        raise AssistantError("Пустой ответ модели")
    return text
