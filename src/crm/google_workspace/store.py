"""Provider-governed private OAuth state and source provenance."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from src.crm.metatables import MODELS
from src.crm.repositories.errors import ResourceConflict
from src.crm.repositories.gateway import GovernedGateway


class GoogleStore(GovernedGateway):
    def _one(self, result: dict[str, Any], message: str) -> dict[str, Any]:
        rows = result.get("rows")
        if not isinstance(rows, list) or len(rows) != 1:
            raise ResourceConflict(message)
        return rows[0]

    def connection(self, actor_uid: uuid.UUID) -> dict[str, Any] | None:
        table = MODELS["google_oauth_connection"].__tablename__
        result = self._operation(
            operation="select",
            sql=f'SELECT * FROM "{table}" WHERE actor_uid=%(actor_uid)s::uuid LIMIT 1',
            parameters={"actor_uid": str(actor_uid)},
            parameter_types={},
            tables={"google_oauth_connection": "read"},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list):
            raise RuntimeError("Google connection read returned an invalid envelope")
        return rows[0] if rows else None

    def start(
        self,
        *,
        uid: uuid.UUID,
        actor_uid: uuid.UUID,
        connection_uid: uuid.UUID,
        state_hash: str,
        source: str,
        verifier_ciphertext: str,
        nonce: str,
    ) -> None:
        table = MODELS["google_oauth_attempt"].__tablename__
        self._operation(
            operation="delete",
            sql=(
                f'DELETE FROM "{table}" WHERE uid IN (SELECT uid FROM "{table}" '
                "WHERE (status='completed' OR expires_at<NOW()-INTERVAL '1 day' "
                "OR (status IN ('exchanged','redeeming') AND completed_at<NOW()-INTERVAL '1 day')) "
                "ORDER BY expires_at LIMIT 100) RETURNING uid"
            ),
            parameters={}, parameter_types={}, tables={"google_oauth_attempt": "write"}, max_rows=100,
        )
        self._one(
            self._operation(
                operation="insert",
                sql=(
                    f'INSERT INTO "{table}" (uid, state_hash, actor_uid, connection_uid, source, '
                    "verifier_ciphertext, nonce, expires_at, status) VALUES "
                    "(%(uid)s::uuid, %(state_hash)s, %(actor_uid)s::uuid, %(connection_uid)s::uuid, "
                    "%(source)s, %(verifier_ciphertext)s, %(nonce)s, NOW()+INTERVAL '10 minutes', 'started') "
                    "RETURNING uid"
                ),
                parameters={
                    "uid": str(uid), "state_hash": state_hash, "actor_uid": str(actor_uid),
                    "connection_uid": str(connection_uid), "source": source,
                    "verifier_ciphertext": verifier_ciphertext, "nonce": nonce,
                },
                parameter_types={},
                tables={"google_oauth_attempt": "write"},
                max_rows=1,
            ),
            "Google OAuth attempt could not be created",
        )

    def claim(self, state_hash: str) -> dict[str, Any]:
        table = MODELS["google_oauth_attempt"].__tablename__
        result = self._operation(
            operation="update",
            sql=(
                f'UPDATE "{table}" SET status=\'redeeming\' '
                "WHERE state_hash=%(state_hash)s AND status='started' AND expires_at>NOW() "
                "RETURNING uid, actor_uid, connection_uid, source, verifier_ciphertext, nonce"
            ),
            parameters={"state_hash": state_hash},
            parameter_types={},
            tables={"google_oauth_attempt": "write"},
            max_rows=1,
        )
        return self._one(result, "Google OAuth state is expired or already used")

    def exchanged(self, uid: uuid.UUID, completion_hash: str, pending_ciphertext: str) -> None:
        table = MODELS["google_oauth_attempt"].__tablename__
        self._one(
            self._operation(
                operation="update",
                sql=(
                    f'UPDATE "{table}" SET status=\'exchanged\', completion_hash=%(completion_hash)s, '
                    "pending_ciphertext=%(pending_ciphertext)s, completed_at=NOW() "
                    "WHERE uid=%(uid)s::uuid AND status='redeeming' RETURNING uid"
                ),
                parameters={"uid": str(uid), "completion_hash": completion_hash, "pending_ciphertext": pending_ciphertext},
                parameter_types={},
                tables={"google_oauth_attempt": "write"},
                max_rows=1,
            ),
            "Google OAuth exchange could not be completed",
        )

    def fail(self, uid: uuid.UUID) -> None:
        table = MODELS["google_oauth_attempt"].__tablename__
        self._operation(
            operation="update",
            sql=(
                f'UPDATE "{table}" SET verifier_ciphertext=\'\', '
                "pending_ciphertext=NULL, completed_at=NOW() "
                "WHERE uid=%(uid)s::uuid AND status='redeeming' RETURNING uid"
            ),
            parameters={"uid": str(uid)},
            parameter_types={},
            tables={"google_oauth_attempt": "write"},
            max_rows=1,
        )

    def pending(self, actor_uid: uuid.UUID, completion_hash: str) -> dict[str, Any]:
        table = MODELS["google_oauth_attempt"].__tablename__
        result = self._operation(
            operation="select",
            sql=(
                f'SELECT uid, actor_uid, connection_uid, source, pending_ciphertext FROM "{table}" '
                "WHERE actor_uid=%(actor_uid)s::uuid AND completion_hash=%(completion_hash)s "
                "AND status='exchanged' AND completed_at>NOW()-INTERVAL '5 minutes' LIMIT 1"
            ),
            parameters={"actor_uid": str(actor_uid), "completion_hash": completion_hash},
            parameter_types={},
            tables={"google_oauth_attempt": "read"},
            max_rows=1,
        )
        return self._one(result, "Google OAuth completion is expired or already used")

    def attempt_status(self, actor_uid: uuid.UUID, uid: uuid.UUID) -> dict[str, Any] | None:
        table = MODELS["google_oauth_attempt"].__tablename__
        result = self._operation(
            operation="select",
            sql=(
                f'SELECT status, pending_ciphertext, CASE WHEN status=\'redeeming\' '
                "AND verifier_ciphertext='' THEN 'failed' WHEN status='exchanged' "
                "AND completed_at<=NOW()-INTERVAL '5 minutes' THEN 'expired' "
                "WHEN status IN ('started','redeeming') AND expires_at<=NOW() THEN 'expired' "
                f'ELSE status END AS effective_status FROM "{table}" '
                "WHERE uid=%(uid)s::uuid AND actor_uid=%(actor_uid)s::uuid LIMIT 1"
            ),
            parameters={"uid": str(uid), "actor_uid": str(actor_uid)},
            parameter_types={},
            tables={"google_oauth_attempt": "read"},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list):
            raise RuntimeError("Google OAuth status returned an invalid envelope")
        if not rows:
            return None
        return {**rows[0], "status": rows[0]["effective_status"]}

    def activate(
        self,
        *,
        actor_uid: uuid.UUID,
        attempt_uid: uuid.UUID,
        completion_hash: str,
        connection_uid: uuid.UUID,
        google_sub: str,
        email: str,
        scopes: list[str],
        refresh_ciphertext: str,
    ) -> dict[str, Any]:
        attempt = MODELS["google_oauth_attempt"].__tablename__
        connection = MODELS["google_oauth_connection"].__tablename__
        source = MODELS["source_connection"].__tablename__
        source_key = hashlib.sha256(f"{actor_uid}:{google_sub}".encode()).hexdigest()
        source_uid = uuid.uuid5(uuid.NAMESPACE_URL, f"mainsequence-crm:google:{source_key}")
        result = self._operation(
            operation="update",
            sql=(
                "WITH allowed AS ("
                f'SELECT uid FROM "{attempt}" WHERE uid=%(attempt_uid)s::uuid '
                "AND actor_uid=%(actor_uid)s::uuid AND connection_uid=%(connection_uid)s::uuid "
                "AND completion_hash=%(completion_hash)s AND status='exchanged' "
                "AND completed_at>NOW()-INTERVAL '5 minutes'), "
                f'source AS (INSERT INTO "{source}" (uid, created_at, updated_at, created_by_uid, '
                "updated_by_uid, version, name, adapter_id, source_account_key, configuration) "
                "SELECT %(source_uid)s::uuid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, "
                "1, 'Google Workspace', 'google-workspace-v1', %(source_key)s, '{}'::jsonb "
                "FROM allowed ON CONFLICT (adapter_id, source_account_key) DO UPDATE "
                "SET updated_at=EXCLUDED.updated_at RETURNING uid), "
                f'connected AS (INSERT INTO "{connection}" (uid, actor_uid, source_connection_uid, '
                "google_sub, display_email, granted_scopes, refresh_ciphertext, status, version, created_at, updated_at) "
                "SELECT %(connection_uid)s::uuid, %(actor_uid)s::uuid, source.uid, %(google_sub)s, "
                "%(email)s, %(scopes)s::jsonb, %(refresh_ciphertext)s, 'connected', 1, NOW(), NOW() "
                "FROM source ON CONFLICT (actor_uid) DO UPDATE SET "
                "google_sub=EXCLUDED.google_sub, display_email=EXCLUDED.display_email, "
                "granted_scopes=EXCLUDED.granted_scopes, refresh_ciphertext=EXCLUDED.refresh_ciphertext, "
                "status='connected', version="
                f'"{connection}".version+1, updated_at=NOW() '
                f'WHERE "{connection}".uid=EXCLUDED.uid AND '
                f'(\"{connection}\".status=\'disconnected\' OR \"{connection}\".google_sub=EXCLUDED.google_sub) '
                "RETURNING uid, actor_uid, google_sub, display_email, granted_scopes, status, version) "
                f'UPDATE "{attempt}" t SET status=\'completed\', pending_ciphertext=NULL, '
                "verifier_ciphertext='', completion_hash=NULL FROM connected "
                "WHERE t.uid=%(attempt_uid)s::uuid AND t.uid IN (SELECT uid FROM allowed) "
                "RETURNING connected.uid, connected.display_email, connected.granted_scopes, "
                "connected.status, connected.version"
            ),
            parameters={
                "actor_uid": str(actor_uid), "attempt_uid": str(attempt_uid),
                "completion_hash": completion_hash, "connection_uid": str(connection_uid),
                "source_uid": str(source_uid), "source_key": source_key,
                "google_sub": google_sub, "email": email, "scopes": json.dumps(scopes),
                "refresh_ciphertext": refresh_ciphertext,
            },
            parameter_types={"scopes": "jsonb"},
            tables={"google_oauth_attempt": "write", "google_oauth_connection": "write", "source_connection": "write"},
            max_rows=1,
        )
        return self._one(result, "Google connection changed or was already completed")

    def disconnect(self, actor_uid: uuid.UUID, uid: uuid.UUID) -> str | None:
        table = MODELS["google_oauth_connection"].__tablename__
        result = self._operation(
            operation="update",
            sql=(
                f'WITH previous AS (SELECT refresh_ciphertext FROM "{table}" '
                "WHERE uid=%(uid)s::uuid AND actor_uid=%(actor_uid)s::uuid "
                "AND status<>'disconnected' FOR UPDATE) "
                f'UPDATE "{table}" SET refresh_ciphertext=NULL, status=\'disconnected\', '
                "granted_scopes='[]'::jsonb, updated_at=NOW(), version=version+1 "
                "FROM previous WHERE uid=%(uid)s::uuid AND actor_uid=%(actor_uid)s::uuid "
                "AND status<>'disconnected' RETURNING previous.refresh_ciphertext"
            ),
            parameters={"uid": str(uid), "actor_uid": str(actor_uid)},
            parameter_types={},
            tables={"google_oauth_connection": "write"},
            max_rows=1,
        )
        row = self._one(result, "Google connection not found")
        return row.get("refresh_ciphertext")

    def reauthorization_required(self, actor_uid: uuid.UUID, uid: uuid.UUID) -> None:
        table = MODELS["google_oauth_connection"].__tablename__
        self._operation(
            operation="update",
            sql=(
                f'UPDATE "{table}" SET status=\'reauthorization_required\', updated_at=NOW(), '
                "version=version+1 WHERE uid=%(uid)s::uuid AND actor_uid=%(actor_uid)s::uuid "
                "AND status='connected' RETURNING uid"
            ),
            parameters={"uid": str(uid), "actor_uid": str(actor_uid)},
            parameter_types={},
            tables={"google_oauth_connection": "write"},
            max_rows=1,
        )

    def source_link(self, source_connection_uid: uuid.UUID, entity_type: str, external_id: str) -> dict[str, Any] | None:
        table = MODELS["source_identity"].__tablename__
        if entity_type not in {"contact", "interaction"}:
            raise ValueError("Unsupported Google provenance entity")
        target = MODELS[entity_type].__tablename__
        result = self._operation(
            operation="select",
            sql=(
                'SELECT s.target_uid, t.version, t.archived_at, '
                + ("t.company_uid" if entity_type == "interaction" else "NULL::uuid AS company_uid")
                + f' FROM "{table}" s LEFT JOIN "{target}" t ON t.uid=s.target_uid '
                "WHERE s.source_connection_uid=%(connection_uid)s::uuid "
                "AND s.entity_type=%(entity_type)s AND s.external_id=%(external_id)s "
                "LIMIT 1"
            ),
            parameters={"connection_uid": str(source_connection_uid), "entity_type": entity_type, "external_id": external_id},
            parameter_types={},
            tables={"source_identity": "read", entity_type: "read"},
            max_rows=1,
        )
        rows = result.get("rows")
        if not isinstance(rows, list):
            raise RuntimeError("Google provenance read returned an invalid envelope")
        return rows[0] if rows else None

    def source_links(self, source_connection_uid: uuid.UUID, entity_type: str, external_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not external_ids:
            return {}
        if entity_type not in {"contact", "interaction"}:
            raise ValueError("Unsupported Google provenance entity")
        table = MODELS["source_identity"].__tablename__
        target = MODELS[entity_type].__tablename__
        result = self._operation(
            operation="select",
            sql=(
                'SELECT s.external_id, s.target_uid, t.version, t.archived_at, '
                + ("t.company_uid" if entity_type == "interaction" else "NULL::uuid AS company_uid")
                + f' FROM "{table}" s LEFT JOIN "{target}" t ON t.uid=s.target_uid '
                "WHERE s.source_connection_uid=%(connection_uid)s::uuid "
                "AND s.entity_type=%(entity_type)s "
                "AND s.external_id IN (SELECT jsonb_array_elements_text(%(external_ids)s::jsonb))"
            ),
            parameters={"connection_uid": str(source_connection_uid), "entity_type": entity_type,
                        "external_ids": json.dumps(external_ids)},
            parameter_types={"external_ids": "jsonb"},
            tables={"source_identity": "read", entity_type: "read"},
            max_rows=len(external_ids),
        )
        rows = result.get("rows")
        if not isinstance(rows, list):
            raise RuntimeError("Google provenance read returned an invalid envelope")
        return {str(row["external_id"]): row for row in rows}

    def contact_matches(self, email: str) -> list[dict[str, Any]]:
        table = MODELS["contact"].__tablename__
        result = self._operation(
            operation="select",
            sql=(
                f'SELECT uid, version, first_name, last_name FROM "{table}" c '
                "WHERE archived_at IS NULL AND EXISTS (SELECT 1 FROM jsonb_array_elements(c.emails) e "
                "WHERE lower(e->>'email')=%(email)s) ORDER BY uid LIMIT 4"
            ),
            parameters={"email": email.casefold()},
            parameter_types={},
            tables={"contact": "read"},
            max_rows=4,
        )
        rows = result.get("rows")
        if not isinstance(rows, list):
            raise RuntimeError("Google contact match returned an invalid envelope")
        return rows

    def contact_matches_many(self, emails: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not emails:
            return {}
        table = MODELS["contact"].__tablename__
        result = self._operation(
            operation="select",
            sql=(
                "SELECT email, uid, version, first_name, last_name FROM ("
                "SELECT lower(e->>'email') AS email, c.uid, c.version, c.first_name, c.last_name, "
                "row_number() OVER (PARTITION BY lower(e->>'email') ORDER BY c.uid) AS rank "
                f'FROM "{table}" c CROSS JOIN LATERAL jsonb_array_elements(c.emails) e '
                "WHERE c.archived_at IS NULL AND lower(e->>'email') IN "
                "(SELECT jsonb_array_elements_text(%(emails)s::jsonb))"
                ") matches WHERE rank <= 4 ORDER BY email, uid"
            ),
            parameters={"emails": json.dumps(sorted(set(emails)))},
            parameter_types={"emails": "jsonb"},
            tables={"contact": "read"},
            max_rows=4 * len(set(emails)),
        )
        rows = result.get("rows")
        if not isinstance(rows, list):
            raise RuntimeError("Google contact match returned an invalid envelope")
        matches: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            matches.setdefault(str(row["email"]), []).append(row)
        return matches

    def import_candidate(
        self,
        *,
        actor_uid: uuid.UUID,
        source_connection_uid: uuid.UUID,
        entity_type: str,
        external_id: str,
        payload_hash: str,
        action: str,
        target_uid: uuid.UUID | None,
        expected_version: int | None,
        values: dict[str, Any],
    ) -> uuid.UUID:
        if entity_type not in {"contact", "interaction"} or action not in {"create", "link", "update"}:
            raise ValueError("Unsupported Google import action")
        target = MODELS[entity_type].__tablename__
        identity = MODELS["source_identity"].__tablename__
        activity = MODELS["activity_event"].__tablename__
        uid = target_uid if target_uid is not None else uuid.uuid4()
        command_uid = uuid.uuid4()
        parameters: dict[str, Any] = {
            "uid": str(uid), "actor_uid": str(actor_uid),
            "source_connection_uid": str(source_connection_uid),
            "external_id": external_id, "payload_hash": payload_hash,
            "source_identity_uid": str(uuid.uuid4()),
            "job_uid": str(command_uid), "event_uid": str(uuid.uuid4()),
            "command_uid": str(command_uid), "entity_type": entity_type,
            "source_attribution": json.dumps({"source": "google_workspace"}),
            "expected_version": expected_version,
        }
        types = {"source_attribution": "jsonb"}
        if action == "create":
            if target_uid is not None:
                raise ValueError("Create cannot specify a target")
            if entity_type == "contact":
                parameters.update({
                    "first_name": values.get("first_name"),
                    "last_name": values.get("last_name"),
                    "emails": json.dumps(values.get("emails", [])),
                    "phones": json.dumps(values.get("phones", [])),
                })
                types.update({"emails": "jsonb", "phones": "jsonb"})
                changed = (
                    f'INSERT INTO "{target}" (uid, created_at, updated_at, created_by_uid, '
                    "updated_by_uid, version, archived_at, first_name, last_name, emails, phones, socials) "
                    "SELECT %(uid)s::uuid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, "
                    "1, NULL, %(first_name)s, %(last_name)s, %(emails)s::jsonb, %(phones)s::jsonb, '{}'::jsonb FROM gate "
                    "RETURNING uid, version"
                )
                scopes = {"contact": "write"}
            else:
                parameters.update({
                    "company_uid": str(values["company_uid"]),
                    "contact_uid": str(values["contact_uid"]) if values.get("contact_uid") else None,
                    "deal_uid": str(values["deal_uid"]) if values.get("deal_uid") else None,
                    "subject": values["subject"], "status": values["status"],
                    "scheduled_at": values["scheduled_at"],
                })
                company = MODELS["company"].__tablename__
                contact = MODELS["contact"].__tablename__
                deal = MODELS["deal"].__tablename__
                changed = (
                    f'INSERT INTO "{target}" (uid, created_at, updated_at, created_by_uid, '
                    "updated_by_uid, version, archived_at, company_uid, contact_uid, deal_uid, "
                    "subject, kind, status, scheduled_at, occurred_at) "
                    "SELECT %(uid)s::uuid, NOW(), NOW(), %(actor_uid)s::uuid, %(actor_uid)s::uuid, "
                    "1, NULL, %(company_uid)s::uuid, %(contact_uid)s::uuid, %(deal_uid)s::uuid, "
                    "%(subject)s, 'meeting', %(status)s, %(scheduled_at)s::timestamptz, NULL FROM gate "
                    f'WHERE EXISTS (SELECT 1 FROM "{company}" c WHERE c.uid=%(company_uid)s::uuid AND c.archived_at IS NULL) '
                    f'AND (%(contact_uid)s::uuid IS NULL OR EXISTS (SELECT 1 FROM "{contact}" c '
                    "WHERE c.uid=%(contact_uid)s::uuid AND c.archived_at IS NULL)) "
                    f'AND (%(deal_uid)s::uuid IS NULL OR EXISTS (SELECT 1 FROM "{deal}" d '
                    "WHERE d.uid=%(deal_uid)s::uuid AND d.company_uid=%(company_uid)s::uuid AND d.archived_at IS NULL)) "
                    "RETURNING uid, version"
                )
                scopes = {"interaction": "write", "company": "read", "contact": "read", "deal": "read"}
        elif action == "link":
            if target_uid is None:
                raise ValueError("Link requires a CRM target")
            changed = (
                f'SELECT uid, version FROM "{target}" WHERE uid=%(uid)s::uuid AND archived_at IS NULL '
                "AND EXISTS (SELECT 1 FROM gate)"
            )
            scopes = {entity_type: "read"}
        else:
            if target_uid is None or expected_version is None:
                raise ValueError("Update requires a target and expected version")
            if entity_type == "contact":
                raise ValueError("Contact updates require the CRM contact editor")
            parameters.update({
                "company_uid": str(values["company_uid"]),
                "subject": values["subject"], "status": values["status"],
                "scheduled_at": values["scheduled_at"],
            })
            changed = (
                f'UPDATE "{target}" t SET subject=%(subject)s, status=%(status)s, '
                "scheduled_at=%(scheduled_at)s::timestamptz, updated_at=NOW(), "
                "updated_by_uid=%(actor_uid)s::uuid, version=t.version+1 "
                "WHERE t.uid=%(uid)s::uuid AND t.version=%(expected_version)s::bigint "
                "AND t.company_uid=%(company_uid)s::uuid AND t.archived_at IS NULL "
                "AND EXISTS (SELECT 1 FROM gate) "
                f'AND EXISTS (SELECT 1 FROM "{identity}" s WHERE '
                "s.source_connection_uid=%(source_connection_uid)s::uuid "
                "AND s.entity_type=%(entity_type)s AND s.external_id=%(external_id)s "
                "AND s.target_uid=t.uid) "
                "RETURNING t.uid, t.version"
            )
            scopes = {"interaction": "write"}
        if action == "update":
            identity_write = (
                f'UPDATE "{identity}" s SET source_payload_hash=%(payload_hash)s, '
                "last_imported_target_version=changed.version, last_import_job_uid=%(job_uid)s::uuid, updated_at=NOW() "
                "FROM changed WHERE s.source_connection_uid=%(source_connection_uid)s::uuid "
                "AND s.entity_type=%(entity_type)s AND s.external_id=%(external_id)s "
                "AND s.target_uid=changed.uid RETURNING s.target_uid"
            )
        else:
            identity_write = (
                f'INSERT INTO "{identity}" (uid, source_connection_uid, entity_type, external_id, '
                "target_uid, source_payload_hash, source_updated_at, last_imported_target_version, "
                "last_import_job_uid, created_at, updated_at) "
                "SELECT %(source_identity_uid)s::uuid, %(source_connection_uid)s::uuid, "
                "%(entity_type)s, %(external_id)s, changed.uid, %(payload_hash)s, NULL, "
                "changed.version, %(job_uid)s::uuid, NOW(), NOW() FROM changed RETURNING target_uid"
            )
        result = self._operation(
            operation="insert",
            sql=(
                f'WITH gate AS (SELECT uid FROM "{MODELS["google_oauth_connection"].__tablename__}" '
                "WHERE actor_uid=%(actor_uid)s::uuid AND source_connection_uid=%(source_connection_uid)s::uuid "
                "AND status='connected' FOR SHARE), "
                f"changed AS ({changed}), linked AS ({identity_write}) "
                f'INSERT INTO "{activity}" (uid, entity_type, entity_uid, kind, occurred_at, '
                "recorded_at, actor_uid, origin, command_uid, summary, changes, source_attribution) "
                "SELECT %(event_uid)s::uuid, %(entity_type)s, linked.target_uid, "
                "'imported', NOW(), NOW(), %(actor_uid)s::uuid, 'import', %(command_uid)s::uuid, "
                "'Reviewed Google import', '{}'::jsonb, %(source_attribution)s::jsonb "
                "FROM linked RETURNING entity_uid"
            ),
            parameters=parameters,
            parameter_types=types,
            tables={**scopes, "source_identity": "write", "activity_event": "write", "source_connection": "read", "google_oauth_connection": "read"},
            max_rows=1,
        )
        self._one(result, "Google import precondition failed")
        return uid
