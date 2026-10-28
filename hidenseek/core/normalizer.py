"""Нормализация: транслит, уменьшительные имена, единый формат телефона, ники."""
from __future__ import annotations

import re
import unicodedata

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}

# Варианты латиницы, которые встречаются в профилях для одних и тех же букв.
_LATIN_VARIANTS = [
    ("kh", "h"), ("ts", "c"), ("yu", "iu"), ("ya", "ia"), ("shch", "sch"),
    ("zh", "j"), ("y", "i"), ("ks", "x"),
]

# Полное имя -> уменьшительные. Сравнение идёт по «канонической» форме.
_DIMINUTIVES = {
    "александр": ["саша", "шура", "санёк", "саня", "алекс"],
    "александра": ["саша", "шура"],
    "алексей": ["лёша", "леша", "алёша", "алеша"],
    "анастасия": ["настя", "стася"],
    "анна": ["аня", "анечка", "нюра"],
    "владимир": ["вова", "володя", "вовка"],
    "дмитрий": ["дима", "митя", "димон"],
    "евгений": ["женя"],
    "евгения": ["женя"],
    "екатерина": ["катя", "катерина"],
    "елена": ["лена", "алёна"],
    "иван": ["ваня"],
    "мария": ["маша", "маруся"],
    "михаил": ["миша"],
    "наталья": ["наташа", "наталия"],
    "николай": ["коля"],
    "ольга": ["оля"],
    "павел": ["паша"],
    "сергей": ["серёжа", "сережа", "серёга"],
    "татьяна": ["таня"],
    "юлия": ["юля"],
    "андрей": ["андрюша"],
    "антон": ["тоша"],
    "артём": ["тёма", "артем", "тема"],
    "виктория": ["вика"],
    "денис": ["дэн"],
    "кирилл": ["киря"],
    "максим": ["макс"],
    "никита": ["ник"],
    "роман": ["рома"],
}
# Западные формы тех же имён, которые часто пишут в англоязычных профилях.
_WESTERN = {
    "alice": "алиса", "alisa": "алиса", "alexander": "александр", "alex": "александр", "alexey": "алексей",
    "anastasia": "анастасия", "ann": "анна", "anne": "анна", "andrew": "андрей", "catherine": "екатерина",
    "katherine": "екатерина", "kate": "екатерина", "daniel": "даниил", "dmitry": "дмитрий", "eugene": "евгений",
    "helen": "елена", "elena": "елена", "ivan": "иван", "john": "иван", "julia": "юлия", "maria": "мария",
    "mary": "мария", "michael": "михаил", "mike": "михаил", "natalie": "наталья", "nicholas": "николай",
    "nick": "николай", "olga": "ольга", "paul": "павел", "peter": "пётр", "sergey": "сергей", "tatiana": "татьяна",
    "victoria": "виктория", "vladimir": "владимир", "george": "георгий", "yury": "юрий", "yuri": "юрий",
}
_CANON: dict[str, str] = {}  # заполняется ниже, после fold()


def _strip_marks(c: str) -> str:
    return "".join(x for x in unicodedata.normalize("NFD", c) if unicodedata.category(x) != "Mn")


def fold(text: str) -> str:
    """Нижний регистр, ё→е, без диакритики и лишних пробелов."""
    text = unicodedata.normalize("NFKC", text or "").lower().replace("ё", "е")
    # диакритику снимаем только с латиницы: иначе «й» превратится в «и»
    text = "".join(c if "\u0400" <= c <= "\u04ff" else _strip_marks(c) for c in text)
    return re.sub(r"\s+", " ", text).strip()


def translit(text: str) -> str:
    return "".join(_TRANSLIT.get(c, c) for c in fold(text))


def latin_key(text: str) -> str:
    """Ключ для сравнения строк в разной записи: «Юлия» и «Yuliya»/«Iulia» дают один ключ."""
    key = re.sub(r"[^a-z0-9 ]", "", translit(text))
    for a, b in _LATIN_VARIANTS:
        key = key.replace(a, b)
    key = re.sub(r"(.)\1+", r"\1", key)  # «Kirill» / «Kiril»
    return key.strip()


def _build_canon() -> None:
    for full, short in _DIMINUTIVES.items():
        _CANON[fold(full)] = fold(full)
        for v in short:
            _CANON.setdefault(fold(v), fold(full))
    for western, full in _WESTERN.items():
        _CANON.setdefault(western, fold(full))


def canonical_first_name(name: str) -> str:
    n = fold(name)
    return _CANON.get(n, n)


def name_tokens(full_name: str) -> list[str]:
    return [latin_key(canonical_first_name(t)) for t in re.split(r"[\s,.\-_]+", full_name or "") if t]


_build_canon()


def phone_e164(raw: str, default_country: str = "7") -> str:
    """+7 999 123-45-67 / 8 (999) 1234567 / 9991234567 → +79991234567."""
    digits = re.sub(r"\D", "", raw or "")
    if not digits:
        return ""
    if len(digits) == 11 and digits.startswith("8") and default_country == "7":
        digits = "7" + digits[1:]
    elif len(digits) == 10 and default_country == "7":
        digits = "7" + digits
    return "+" + digits


def username_variants(raw: str) -> dict[str, str]:
    compact = re.sub(r"[^a-z0-9а-я@._+-]", "", fold(raw))
    return {
        "Исходное значение": raw,
        "Нижний регистр": fold(raw),
        "Без пробелов и спецсимволов": compact,
        "Компактный вариант": re.sub(r"[._+-]", "", compact),
        "Транслитерация": translit(raw),
    }


def normalize_email(raw: str) -> str:
    return (raw or "").strip().lower()


def normalize_domain(raw: str) -> str:
    d = (raw or "").strip().lower()
    d = re.sub(r"^[a-z]+://", "", d).split("/")[0].split(":")[0]
    return d.removeprefix("www.").rstrip(".")


def normalize_username(raw: str) -> str:
    return (raw or "").strip().lstrip("@")


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](-*[a-z0-9])*\.)+[a-z]{2,63}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{2,64}$")
