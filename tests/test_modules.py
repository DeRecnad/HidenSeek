import asyncio

import httpx

from hidenseek.modules.base import Fact, RunContext
from hidenseek.modules.crtsh_mod import CrtShModule
from hidenseek.modules.github_mod import GitHubModule
from hidenseek.modules.hibp_mod import HibpModule
from hidenseek.modules.maigret_mod import username_confidence


def ctx_with(settings, handler):
    return RunContext(settings=settings, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def test_github_takes_only_own_commits(settings):
    def handler(req):
        if req.url.path == "/users/octo":
            return httpx.Response(200, json={"login": "octo", "name": "Octo Cat", "location": "Kazan",
                                             "html_url": "https://github.com/octo"})
        if req.url.path == "/search/commits":
            return httpx.Response(200, json={"items": [
                {"author": {"login": "octo"}, "commit": {"author": {"email": "octo@example.com", "name": "Octo"}},
                 "repository": {"full_name": "octo/r"}, "html_url": "u1"},
                {"author": {"login": "someone-else"}, "commit": {"author": {"email": "else@example.com"}},
                 "repository": {"full_name": "octo/r"}},
                {"author": {"login": "octo"}, "commit": {"author": {"email": "1+octo@users.noreply.github.com"}},
                 "repository": {"full_name": "octo/r"}},
            ]})
        return httpx.Response(404)

    res = asyncio.run(GitHubModule().run(Fact("github", "octo", "i"), ctx_with(settings, handler)))
    emails = [f.value for f in res.findings if f.type == "public_email_in_commits"]
    assert emails == ["octo@example.com"]
    assert [(n.value, n.inherits) for n in res.new_facts] == [("octo@example.com", True)]


def test_crtsh_filters_foreign_names(settings):
    def handler(req):
        return httpx.Response(200, json=[
            {"name_value": "*.example.com\nwww.example.com", "not_before": "2020-01-01"},
            {"name_value": "evil.com", "not_before": "2020-01-01"},
        ])

    res = asyncio.run(CrtShModule().run(Fact("domain", "example.com", "i"), ctx_with(settings, handler)))
    subs = [f.value for f in res.findings if f.type == "subdomain"]
    assert subs == ["www.example.com"]


def test_hibp_requires_key_and_validates_format(settings):
    assert HibpModule().available(settings)[0] is False
    settings.hibp_api_key = "k"

    def handler(req):
        assert req.headers["hibp-api-key"] == "k"
        return httpx.Response(200, json=[{"Name": "X", "Title": "X", "DataClasses": ["Passwords"]}])

    res = asyncio.run(HibpModule().run(Fact("email", "a@b.co", "i"), ctx_with(settings, handler)))
    assert res.findings[0].data["data_classes"] == ["Passwords"]


def test_unexpected_format_is_an_error(settings):
    import pytest
    from hidenseek.modules.base import ModuleError

    with pytest.raises(ModuleError, match="формат"):
        asyncio.run(CrtShModule().run(Fact("domain", "example.com", "i"),
                                      ctx_with(settings, lambda r: httpx.Response(200, json={"oops": 1}))))


def test_username_confidence_orders_uniqueness():
    assert username_confidence("persik") < 0.45 < username_confidence("alice-testova-1987")
