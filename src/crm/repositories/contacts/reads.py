"""Contact projection with company name, tags, and open-task count."""

from __future__ import annotations

from ...metatables import MODELS


def contact_projection() -> tuple[str, dict[str, str]]:
    table = MODELS["contact"].__tablename__
    company = MODELS["company"].__tablename__
    contact_tag = MODELS["contact_tag"].__tablename__
    task = MODELS["task"].__tablename__
    return (
        "SELECT t.*, trim(concat_ws(' ', t.first_name, t.last_name)) AS display_name, "
        f'(SELECT c.name FROM "{company}" c WHERE c.uid=t.company_uid) '
        "AS company_name, "
        f'COALESCE((SELECT jsonb_agg(ct.tag_uid ORDER BY ct.tag_uid) FROM "{contact_tag}" ct '
        "WHERE ct.contact_uid=t.uid), '[]'::jsonb) AS tag_uids, "
        f'(SELECT count(*) FROM "{task}" k WHERE k.contact_uid=t.uid '
        "AND k.completed_at IS NULL AND k.archived_at IS NULL) "
        f'AS open_task_count FROM "{table}" t',
        {"company": "read", "contact_tag": "read", "task": "read"},
    )
