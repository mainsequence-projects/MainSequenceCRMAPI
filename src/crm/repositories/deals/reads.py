"""Deal projection with decimal-safe amount and linked contacts."""

from __future__ import annotations

from ...metatables import MODELS


def deal_projection() -> tuple[str, dict[str, str]]:
    table = MODELS["deal"].__tablename__
    link = MODELS["deal_contact"].__tablename__
    return (
        "SELECT t.uid, t.created_at, t.updated_at, t.created_by_uid, "
        "t.updated_by_uid, t.version, t.archived_at, t.owner_uid, t.company_uid, "
        "t.pipeline_uid, t.stage_uid, t.name, t.category_key, t.description, "
        "t.amount::text AS amount, t.amount AS amount_numeric, t.currency, "
        "t.expected_closing_date, t.position, t.source_created_at, t.source_updated_at, "
        f'COALESCE((SELECT jsonb_agg(dc.contact_uid ORDER BY dc.contact_uid) FROM "{link}" dc '
        f"WHERE dc.deal_uid=t.uid), '[]'::jsonb) "
        f'AS contact_uids FROM "{table}" t',
        {"deal_contact": "read"},
    )
