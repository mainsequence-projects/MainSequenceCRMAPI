"""ResourceBoardOperations for the governed CRM repository."""

from __future__ import annotations

import uuid
from typing import Any

from ...contracts import validate_payload
from ...metatables import MODELS
from ..errors import ResourceConflict, ResourceNotFound
from ..gateway import GovernedGateway
from ..resources.reads import ResourceReads


class DealBoard(GovernedGateway):
    def __init__(self, registry, reads: ResourceReads):
        super().__init__(registry)
        self.reads = reads

    def pipeline_stages(self, pipeline_uid: uuid.UUID) -> dict[str, Any]:
        pipeline_table = MODELS["pipeline"].__tablename__
        stage_table = MODELS["stage"].__tablename__
        result = self._operation(
            operation="select",
            sql=(
                "SELECT p.uid AS pipeline_uid, p.board_version, "
                "COALESCE(jsonb_agg(to_jsonb(s) ORDER BY s.position, s.uid) "
                "FILTER (WHERE s.uid IS NOT NULL), '[]'::jsonb) AS stages "
                f'FROM "{pipeline_table}" p LEFT JOIN LATERAL '
                f'(SELECT * FROM "{stage_table}" WHERE pipeline_uid=p.uid '
                "AND is_active=TRUE ORDER BY position, uid LIMIT 100) s ON TRUE "
                "WHERE p.uid=CAST(%(pipeline_uid)s AS uuid) "
                "GROUP BY p.uid, p.board_version"
            ),
            parameters={"pipeline_uid": str(pipeline_uid)},
            parameter_types={"pipeline_uid": "uuid"},
            tables={"pipeline": "read", "stage": "read"},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ResourceNotFound("Pipeline not found")
        stages = self._json(rows[0].get("stages"), expected=list, label="pipeline stages")
        for stage in stages:
            validate_payload("Stage", stage)
        return {
            "pipeline_uid": str(pipeline_uid),
            "board_version": int(rows[0]["board_version"]),
            "stages": stages,
        }

    def pipeline_board(self, pipeline_uid: uuid.UUID, page_size: int) -> dict[str, Any]:
        pipeline = self.pipeline_stages(pipeline_uid)
        columns = []
        for stage in pipeline["stages"]:
            columns.append(
                self.board_column(
                    pipeline_uid,
                    uuid.UUID(str(stage["uid"])),
                    int(pipeline["board_version"]),
                    page_size,
                    0,
                    stage=stage,
                )
            )
        return {
            "pipeline_uid": str(pipeline_uid),
            "board_version": int(pipeline["board_version"]),
            "columns": columns,
        }

    def board_column(
        self,
        pipeline_uid: uuid.UUID,
        stage_uid: uuid.UUID,
        expected_board_version: int,
        page_size: int,
        offset: int,
        *,
        stage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if page_size < 1 or page_size > 100 or offset < 0:
            raise ValueError("Invalid board page")
        pipeline_table = MODELS["pipeline"].__tablename__
        stage_table = MODELS["stage"].__tablename__
        select_sql, referenced = self.reads._select_sql("deals")
        sql = (
            "WITH pipeline_state AS (SELECT board_version FROM "
            f'"{pipeline_table}" WHERE uid=CAST(%(pipeline_uid)s AS uuid)), q AS ('
            f"{select_sql} WHERE t.pipeline_uid=CAST(%(pipeline_uid)s AS uuid) "
            "AND t.stage_uid=CAST(%(stage_uid)s AS uuid) AND t.archived_at IS NULL), "
            "paged AS (SELECT q.*, row_number() OVER () AS __row FROM q "
            "ORDER BY q.position, q.uid LIMIT CAST(%(page_size)s AS integer) "
            "OFFSET CAST(%(offset)s AS integer)) SELECT "
            "(SELECT board_version FROM pipeline_state) AS board_version, "
            "COALESCE((SELECT jsonb_agg(to_jsonb(paged)-'__row'-'amount_numeric' ORDER BY __row) "
            "FROM paged), '[]'::jsonb) AS items, (SELECT count(*) FROM q) AS total_items, "
            "COALESCE((SELECT jsonb_object_agg(currency, total::text) FROM "
            "(SELECT currency, sum(amount_numeric) AS total FROM q WHERE amount_numeric IS NOT NULL "
            "GROUP BY currency) totals), '{}'::jsonb) AS amounts_by_currency"
        )
        result = self._operation(
            operation="select",
            sql=sql,
            parameters={
                "pipeline_uid": str(pipeline_uid),
                "stage_uid": str(stage_uid),
                "page_size": page_size,
                "offset": offset,
            },
            parameter_types={
                "pipeline_uid": "uuid",
                "stage_uid": "uuid",
                "page_size": "integer",
                "offset": "integer",
            },
            tables={"pipeline": "read", "deal": "read", **referenced},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ResourceNotFound("Pipeline or stage not found")
        row = rows[0]
        if row.get("board_version") is None:
            raise ResourceNotFound("Pipeline not found")
        if int(row["board_version"]) != expected_board_version:
            raise ResourceConflict("Pipeline board version changed")
        if stage is None:
            stage_result = self._operation(
                operation="select",
                sql=(
                    f'SELECT * FROM "{stage_table}" WHERE '
                    "pipeline_uid=CAST(%(pipeline_uid)s AS uuid) "
                    "AND uid=CAST(%(stage_uid)s AS uuid) AND is_active=TRUE LIMIT 1"
                ),
                parameters={
                    "pipeline_uid": str(pipeline_uid),
                    "stage_uid": str(stage_uid),
                },
                parameter_types={
                    "pipeline_uid": "uuid",
                    "stage_uid": "uuid",
                },
                tables={"stage": "read"},
                max_rows=1,
            )
            stage_rows = stage_result.get("rows")
            if not stage_rows:
                raise ResourceNotFound("Stage not found")
            stage = stage_rows[0]
        validate_payload("Stage", stage)
        items = self._json(row.get("items"), expected=list, label="board column")
        for item in items:
            validate_payload("Deal", item)
        total = int(row.get("total_items", 0))
        amounts = self._json(row.get("amounts_by_currency"), expected=dict, label="board amounts")
        next_offset = offset + len(items)
        return {
            "stage": stage,
            "items": items,
            "total_items": total,
            "next_cursor": str(next_offset) if next_offset < total else None,
            "amounts_by_currency": amounts,
        }

    def move_deal(
        self,
        actor_uid: uuid.UUID,
        deal_uid: uuid.UUID,
        command: dict[str, Any],
    ) -> dict[str, Any]:
        """Move one deal while normalizing every affected stage in one statement."""
        command_uid = uuid.uuid4()
        target_stage_uid = uuid.UUID(command["target_stage_uid"])
        before_deal_uid = (
            uuid.UUID(command["before_deal_uid"])
            if command["before_deal_uid"] is not None
            else None
        )
        pipeline = MODELS["pipeline"].__tablename__
        stage = MODELS["stage"].__tablename__
        deal = MODELS["deal"].__tablename__
        activity = MODELS["activity_event"].__tablename__
        parameters = {
            "actor_uid": str(actor_uid),
            "deal_uid": str(deal_uid),
            "expected_version": command["expected_version"],
            "expected_board_version": command["expected_board_version"],
            "target_stage_uid": str(target_stage_uid),
            "before_deal_uid": None if before_deal_uid is None else str(before_deal_uid),
            "command_uid": str(command_uid),
            "event_uid": str(uuid.uuid5(command_uid, "activity")),
        }
        # The pipeline version update is the serialization gate. The mapping
        # covers all active deals in both stages and writes each row at most once.
        sql = (
            f'WITH moving AS (SELECT d.* FROM "{deal}" d WHERE '
            "d.uid=CAST(%(deal_uid)s AS uuid) AND d.archived_at IS NULL "
            "AND d.version=CAST(%(expected_version)s AS bigint)), "
            f'valid AS (SELECT m.*, p.board_version FROM moving m JOIN "{pipeline}" p '
            "ON p.uid=m.pipeline_uid "
            "AND p.board_version=CAST(%(expected_board_version)s AS bigint) "
            f'JOIN "{stage}" s ON s.pipeline_uid=m.pipeline_uid '
            "AND s.uid=CAST(%(target_stage_uid)s AS uuid) AND s.is_active=TRUE "
            "WHERE %(before_deal_uid)s IS NULL OR EXISTS (SELECT 1 FROM "
            f'"{deal}" before_d WHERE before_d.pipeline_uid=m.pipeline_uid '
            "AND before_d.stage_uid=CAST(%(target_stage_uid)s AS uuid) "
            "AND before_d.uid=CAST(%(before_deal_uid)s AS uuid) "
            "AND before_d.uid<>m.uid AND before_d.archived_at IS NULL)), "
            f'gate AS (UPDATE "{pipeline}" p SET board_version=p.board_version+1, '
            "updated_at=NOW(), updated_by_uid=CAST(%(actor_uid)s AS uuid), version=p.version+1 "
            "FROM valid v WHERE p.uid=v.pipeline_uid "
            "AND p.board_version=CAST(%(expected_board_version)s AS bigint) "
            "RETURNING p.board_version, v.stage_uid AS source_stage_uid), "
            f"source_order AS (SELECT d.uid, d.stage_uid, "
            "row_number() OVER (ORDER BY d.position, d.uid)-1 AS new_position "
            f'FROM "{deal}" d JOIN valid v ON d.pipeline_uid=v.pipeline_uid '
            "AND d.stage_uid=v.stage_uid "
            "WHERE d.archived_at IS NULL AND d.uid<>v.uid "
            "AND v.stage_uid<>CAST(%(target_stage_uid)s AS uuid)), "
            f"destination_base AS (SELECT d.uid, "
            "row_number() OVER (ORDER BY d.position, d.uid)-1 AS base_position "
            f'FROM "{deal}" d JOIN valid v ON d.pipeline_uid=v.pipeline_uid '
            "WHERE d.stage_uid=CAST(%(target_stage_uid)s AS uuid) "
            "AND d.archived_at IS NULL AND d.uid<>v.uid), "
            "insert_position AS (SELECT COALESCE("
            "(SELECT base_position FROM destination_base "
            "WHERE uid=CAST(%(before_deal_uid)s AS uuid)), "
            "(SELECT count(*) FROM destination_base))::bigint AS value), "
            "mapping AS (SELECT uid, stage_uid, new_position FROM source_order UNION ALL "
            "SELECT db.uid, CAST(%(target_stage_uid)s AS uuid), "
            "CASE WHEN db.base_position >= ip.value THEN db.base_position+1 "
            "ELSE db.base_position END FROM destination_base db CROSS JOIN insert_position ip "
            "UNION ALL SELECT v.uid, CAST(%(target_stage_uid)s AS uuid), ip.value "
            "FROM valid v CROSS JOIN insert_position ip), "
            f'changed AS (UPDATE "{deal}" d SET stage_uid=m.stage_uid, position=m.new_position, '
            "updated_at=NOW(), updated_by_uid=CAST(%(actor_uid)s AS uuid), version=d.version+1 "
            "FROM mapping m, gate g WHERE d.uid=m.uid "
            "AND (d.stage_uid<>m.stage_uid OR d.position<>m.new_position) RETURNING d.uid), "
            f'INSERT INTO "{activity}" (uid, entity_type, entity_uid, '
            "kind, occurred_at, recorded_at, actor_uid, origin, command_uid, summary, changes, "
            "source_attribution) SELECT CAST(%(event_uid)s AS uuid), "
            "'deal', CAST(%(deal_uid)s AS uuid), 'moved', "
            "NOW(), NOW(), CAST(%(actor_uid)s AS uuid), 'live', "
            "CAST(%(command_uid)s AS uuid), 'Moved deal', "
            "jsonb_build_object('target_stage_uid', %(target_stage_uid)s, "
            "'board_version', bc.board_version, "
            "'invalidated_stage_uids', CASE WHEN bc.source_stage_uid=CAST(%(target_stage_uid)s AS uuid) "
            "THEN jsonb_build_array(bc.source_stage_uid) ELSE "
            "jsonb_build_array(bc.source_stage_uid, CAST(%(target_stage_uid)s AS uuid)) END), NULL "
            "FROM gate bc RETURNING changes"
        )
        result = self._operation(
            operation="insert",
            sql=sql,
            parameters=parameters,
            parameter_types={},
            tables={
                "pipeline": "write",
                "stage": "read",
                "deal": "write",
                "activity_event": "write",
            },
            max_rows=1,
        )
        rows = result.get("rows")
        if not rows:
            raise ResourceConflict("Deal, stage, or board version precondition failed")
        response = self._json(rows[0].get("changes"), expected=dict, label="move")
        moved = self.reads.detail("deals", deal_uid)
        return validate_payload(
            "MoveResult",
            {
                "command_uid": str(command_uid),
                "board_version": response["board_version"],
                "deal": moved,
                "invalidated_stage_uids": response["invalidated_stage_uids"],
            },
        )
