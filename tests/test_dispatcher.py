import asyncio
from contextlib import asynccontextmanager

from hidenseek.core.dispatcher import run_audit
from hidenseek.core.ingest import add_identity
from hidenseek.core.models import Audit, utcnow
from hidenseek.core.queue import FactQueue
from hidenseek.modules.base import Fact, Module, ModuleError, ModuleResult, NewFact, RawFinding


@asynccontextmanager
async def no_client(settings):
    yield None


class Recorder(Module):
    def __init__(self, name, input_type, result=None, fail_times=0, retry=True):
        self.name, self.title, self.input_type = name, name, input_type
        self.calls, self.result, self.fail_times, self.retry = [], result or ModuleResult(), fail_times, retry

    async def run(self, fact, ctx):
        self.calls.append(fact.value)
        if self.fail_times:
            self.fail_times -= 1
            raise ModuleError("boom", retry=self.retry)
        return self.result


def verified(a, t, v):
    i = add_identity(a, t, v)
    i.verified_by, i.verified_at = "email_code", utcnow()
    return i


def go(audit, reg, settings):
    return asyncio.run(run_audit(audit, reg, settings, client_factory=no_client))


def test_only_verified_identities_run_modules(settings):
    a = Audit()
    verified(a, "email", "me@example.com")
    add_identity(a, "email", "notme@example.com")
    mod = Recorder("m", "email")
    go(a, {"m": mod}, settings)
    assert mod.calls == ["me@example.com"]
    assert any("notme@example.com" in l.text and "не подтверждён" in l.text for l in a.log)


def test_new_fact_queued_only_if_inherits(settings):
    a = Audit()
    verified(a, "username", "me")
    res = ModuleResult(findings=[RawFinding("profile_url", "x: me")],
                       new_facts=[NewFact("email", "other@example.com", inherits=False),
                                  NewFact("email", "mine@example.com", inherits=True)])
    src = Recorder("src", "username", res)
    mail = Recorder("mail", "email")
    go(a, {"src": src, "mail": mail}, settings)
    assert mail.calls == ["mine@example.com"]
    inherited = next(i for i in a.identities if i.value == "mine@example.com")
    assert inherited.parent_id == a.identities[0].id
    assert not any(i.value == "other@example.com" for i in a.identities)


def test_retry_then_success_and_failure_does_not_crash(settings):
    a = Audit()
    verified(a, "email", "me@example.com")
    flaky = Recorder("flaky", "email", ModuleResult(findings=[RawFinding("breach", "B")]), fail_times=1)
    dead = Recorder("dead", "email", fail_times=99, retry=False)
    go(a, {"flaky": flaky, "dead": dead}, settings)
    assert len(flaky.calls) == 2 and a.sources["flaky"].state == "done"
    assert len(dead.calls) == 1 and a.sources["dead"].state == "failed"
    assert [f.value for f in a.findings] == ["B"] and not a.running


def test_rerun_keeps_manual_review(settings):
    a = Audit()
    verified(a, "username", "me")
    mod = Recorder("m", "username", ModuleResult(findings=[RawFinding("profile_url", "s: me", review=True)]))
    go(a, {"m": mod}, settings)
    a.findings[0].status = "not_mine"
    go(a, {"m": mod}, settings)
    assert len(a.findings) == 1 and a.findings[0].status == "not_mine"


def test_queue_stop_conditions():
    q = FactQueue(max_depth=1, max_facts=2)
    assert q.push(Fact("email", "A@x.com", "i", 0))
    assert not q.push(Fact("email", "a@x.com", "i", 0))  # не дважды
    assert not q.push(Fact("email", "b@x.com", "i", 2))  # глубина
    assert q.push(Fact("email", "c@x.com", "i", 1))
    assert not q.push(Fact("email", "d@x.com", "i", 1))  # лимит
    assert len(q.dropped) == 2


def test_disabled_module_is_skipped(settings):
    a = Audit(disabled_modules=["m"])
    verified(a, "email", "me@example.com")
    mod = Recorder("m", "email")
    go(a, {"m": mod}, settings)
    assert mod.calls == []
