"""Граф: я → мои идентификаторы → где они видны. Без связей с другими людьми."""
from __future__ import annotations

from ..config import Settings
from .models import Audit


def build(audit: Audit, settings: Settings) -> dict:
    ttl = settings.verify_ttl_days
    sev: dict[str, int] = {}
    whats: dict[str, list[str]] = {}
    for e in audit.exposures:
        sev[e.finding_id] = max(sev.get(e.finding_id, 0), e.severity)
        whats.setdefault(e.finding_id, []).append(e.what)

    nodes = [{"id": "me", "kind": "me", "label": audit.owner_profile.full_name or "Я", "sub": "владелец аудита"}]
    edges = []
    for i in audit.identities:
        state = "verified" if audit.is_verified(i, ttl) else i.verification_state(ttl)
        nodes.append({"id": i.id, "kind": "identity", "label": i.value, "sub": i.type.value, "state": state,
                      "verified_by": i.verified_by})
        parent = i.parent_id if i.parent_id and audit.identity(i.parent_id) else "me"
        edges.append({"from": parent, "to": i.id, "link": "confirmed" if state == "verified" else "hypo"})
    for f in audit.findings:
        nodes.append({"id": f.id, "kind": "finding", "label": f.value, "sub": f.type, "source": f.source,
                      "status": f.status, "severity": sev.get(f.id, 0), "exposes": whats.get(f.id, []),
                      "url": f.url})
        link = {"confirmed": "confirmed", "mine": "confirmed", "review": "hypo", "not_mine": "conflict"}[f.status]
        edges.append({"from": f.identity_id, "to": f.id, "link": link})
    return {"nodes": nodes, "edges": edges}
