"""Company projection, including active contact and deal counts."""

from __future__ import annotations

from ...metatables import MODELS


def company_projection() -> tuple[str, dict[str, str]]:
    table = MODELS["company"].__tablename__
    contact = MODELS["contact"].__tablename__
    affiliation = MODELS["contact_company_affiliation"].__tablename__
    deal = MODELS["deal"].__tablename__
    return (
        f'SELECT t.*, (SELECT count(DISTINCT c.uid) FROM "{contact}" c '
        f'JOIN "{affiliation}" a ON a.contact_uid=c.uid '
        "WHERE c.archived_at IS NULL AND a.company_uid=t.uid "
        "AND a.status='current' AND a.archived_at IS NULL) AS contact_count, "
        f'(SELECT count(*) FROM "{deal}" d WHERE d.company_uid=t.uid) '
        f'AS deal_count FROM "{table}" t',
        {"contact": "read", "contact_company_affiliation": "read", "deal": "read"},
    )
