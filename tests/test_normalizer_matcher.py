from hidenseek.core import matcher
from hidenseek.core.models import Audit, Finding, OwnerProfile
from hidenseek.core.normalizer import canonical_first_name, latin_key, phone_e164, translit


def test_translit_keeps_short_i():
    assert translit("Сергей") == "sergey"
    assert latin_key("Сергей") == latin_key("Sergei") == latin_key("Sergey")


def test_latin_key_variants():
    assert latin_key("Юлия") == latin_key("Iulia") == latin_key("Yuliya")
    assert latin_key("Кирилл") == latin_key("Kiril")


def test_diminutives_and_western_forms():
    assert canonical_first_name("Саша") == "александр"
    assert canonical_first_name("Серёжа") == "сергей"
    assert canonical_first_name("Alice") == "алиса"


def test_phone_e164():
    assert phone_e164("8 (900) 123-45-67") == "+79001234567"
    assert phone_e164("9001234567") == "+79001234567"
    assert phone_e164("+7 900 123 45 67") == "+79001234567"


def test_name_matching():
    assert matcher.name_matches("Алиса Тестова", "Alice Testova")
    assert matcher.name_matches("Александр Петров", "Саша Петров")
    assert not matcher.name_matches("Иван Петров", "Ivan Sidorov")


def _audit(**profile):
    return Audit(owner_profile=OwnerProfile(**profile))


def test_profile_with_name_and_city_is_high_severity():
    a = _audit(full_name="Алиса Тестова", city="Новосибирск")
    a.findings.append(Finding(type="profile_fields", value="github.com/x", source="github", identity_id="i",
                              data={"fields": {"name": "Alice Testova", "location": "Novosibirsk, Russia"}}))
    matcher.apply(a)
    sev = {e.what: e.severity for e in a.exposures}
    assert sev["real_name"] == 3 and sev["city"] == 3


def test_breach_with_password_is_critical():
    a = _audit()
    a.findings.append(Finding(type="breach", value="X", source="hibp", identity_id="i",
                              data={"data_classes": ["Email addresses", "Passwords"]}))
    matcher.apply(a)
    assert [e.what for e in a.exposures] == ["password"] and a.exposures[0].severity == 4


def test_not_mine_is_not_an_exposure():
    a = _audit()
    a.findings.append(Finding(type="profile_url", value="site: persik", source="maigret", identity_id="i",
                              status="not_mine"))
    matcher.apply(a)
    assert a.exposures == []


def test_phone_found_in_data():
    a = _audit(phones=["+7 900 123-45-67"])
    a.findings.append(Finding(type="profile_fields", value="p", source="x", identity_id="i",
                              data={"fields": {"bio": "звоните 8 900 123 45 67"}}))
    matcher.apply(a)
    assert "phone" in {e.what for e in a.exposures}


def test_city_conflict_keeps_both_values():
    a = _audit()
    for loc in ("Novosibirsk", "Москва"):
        a.findings.append(Finding(type="profile_fields", value=loc, source="s", identity_id="i",
                                  data={"fields": {"location": loc}}))
    conflicts = matcher.city_conflicts(a)
    assert len(conflicts) == 1 and {v["value"] for v in conflicts[0]["values"]} == {"Novosibirsk", "Москва"}
