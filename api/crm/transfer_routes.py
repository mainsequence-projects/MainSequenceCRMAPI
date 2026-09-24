"""HTTP contracts for durable CRM imports and exports."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from email.parser import BytesParser
from email.policy import default

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from api.crm.query import QueryError, parse_page, parse_query
from src.crm.models.import_mapping import ImportMapping
from src.crm.models.transfers import (
    CreateExport,
    CreateImport,
    ImportCommitRequest,
    SourceConnectionCreate,
)
from src.crm.platform.runtime import request_port
from src.crm.repositories.resources.store import ResourceConflict, ResourceNotFound
from src.crm.repositories.transfers.store import GovernedTransferStore

from .route_support import _authorized

router = APIRouter(prefix="/api/crm/v1")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_ROWS = 20_000


def _store(request: Request) -> GovernedTransferStore:
    return request_port(request, "crm_transfers") or GovernedTransferStore()


def _page(request: Request) -> tuple[int, int]:
    try:
        page = parse_page(dict(request.query_params))
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {exc.field}: {exc}") from exc
    return page.page_index, page.page_size


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ResourceNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ResourceConflict):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail="CRM transfer operation failed")


@router.get("/source-connections/")
def list_source_connections(request: Request):
    _authorized(request, "crm.transfer.import")
    return _store(request).source_connections(*_page(request))


@router.post("/source-connections/", status_code=201)
def create_source_connection(
    request: Request,
    payload: SourceConnectionCreate,
):
    context = _authorized(request, "crm.transfer.import")
    try:
        return _store(request).create_source_connection(
            context.actor_uid,
            payload.model_dump(mode="json"),
        )
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc


@router.get("/transfers/discovery/")
def transfer_discovery(request: Request):
    _authorized(request, "crm.read")
    try:
        parse_query("transfers", dict(request.query_params), discovery=True)
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {exc.field}: {exc}") from exc
    return {
        "contract": "command-center.resource_discovery@v1",
        "resource": {
            "id": "transfers",
            "label": "Data transfers",
            "item_label": "Data transfer",
            "identity": {"fields": ["uid"]},
        },
        "list": {
            "controls": {
                "search": {"placeholder": "Search data transfers", "fields": ["display_name"]},
                "filters": [
                    {
                        "key": "direction",
                        "label": "Direction",
                        "type": "select",
                        "options": [
                            {"value": "import", "label": "Import"},
                            {"value": "export", "label": "Export"},
                        ],
                    },
                    {"key": "status", "label": "Status", "type": "text"},
                ],
                "ordering": ["created_at", "updated_at"],
            },
            "columns": [
                {
                    "id": "direction",
                    "header": "Direction",
                    "value_path": "direction",
                    "data_type": "text",
                    "default_visible": True,
                    "hideable": False,
                    "importance": "primary",
                },
                {
                    "id": "status",
                    "header": "Status",
                    "value_path": "status",
                    "data_type": "text",
                    "default_visible": True,
                    "hideable": False,
                    "importance": "secondary",
                },
                {
                    "id": "updated-at",
                    "header": "Updated",
                    "value_path": "updated_at",
                    "data_type": "datetime",
                    "default_visible": True,
                    "hideable": True,
                    "importance": "tertiary",
                    "sortable_key": "updated_at",
                },
            ],
        },
        "bulk_actions": [],
    }


@router.get("/transfers/")
def list_transfers(request: Request):
    context = _authorized(request, "crm.read")
    try:
        scope = parse_query("transfers", dict(request.query_params))
    except QueryError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid {exc.field}: {exc}") from exc
    return _store(request).transfers(context.actor_uid, scope)


@router.post("/imports/", status_code=201)
def create_import(
    request: Request,
    payload: CreateImport,
):
    context = _authorized(request, "crm.transfer.import")
    try:
        return _store(request).create_import(
            context.actor_uid,
            payload.model_dump(mode="json"),
        )
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc


def _multipart_file(content_type: str, body: bytes) -> tuple[str, str, bytes]:
    message = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode() + body
    )
    if not message.is_multipart():
        raise HTTPException(status_code=422, detail="Expected multipart file upload")
    for part in message.iter_parts():
        if part.get_param("name", header="content-disposition") == "file":
            payload = part.get_payload(decode=True) or b""
            return (
                part.get_filename() or "upload",
                part.get_content_type() or "application/octet-stream",
                payload,
            )
    raise HTTPException(status_code=422, detail="Upload must contain a file field")


def _parse_rows(adapter: str, entity_type: str | None, content: bytes) -> tuple[list[dict], str]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=422, detail="Upload must be UTF-8") from exc
    if adapter.endswith("csv-v1"):
        if not entity_type:
            raise HTTPException(status_code=422, detail="CSV imports require an entity type")
        try:
            rows = [dict(row) for row in csv.DictReader(io.StringIO(text, newline=""))]
        except csv.Error as exc:
            raise HTTPException(status_code=422, detail="Invalid CSV input") from exc
        return rows, entity_type
    try:
        document = json.loads(text, parse_int=str, parse_float=str)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Invalid JSON input") from exc
    if not isinstance(document, dict):
        raise HTTPException(status_code=422, detail="JSON import must be an object")
    rows: list[dict] = []
    if adapter == "mainsequence-portable-v1":
        records = document.get("entities")
        if document.get("format") != "mainsequence.crm.portable@v1" or not isinstance(
            records, dict
        ):
            raise HTTPException(status_code=422, detail="Invalid portable CRM envelope")
        supported = {
            "companies": "company",
            "contacts": "contact",
            "tags": "tag",
            "pipelines": "pipeline",
            "stages": "stage",
            "deals": "deal",
            "notes": "note",
            "tasks": "task",
            "contact_company_affiliations": "contact_company_affiliation",
        }
        for group, values in records.items():
            if group not in supported:
                raise HTTPException(status_code=422, detail=f"Unsupported portable group: {group}")
            if not isinstance(values, list):
                raise HTTPException(status_code=422, detail=f"Portable {group} must be an array")
            for value in values:
                if not isinstance(value, dict):
                    raise HTTPException(
                        status_code=422, detail=f"Portable {group} row must be an object"
                    )
                rows.append({**value, "__entity_type": supported[group]})
        return rows, "bundle"
    tables = document.get("tables", document)
    if not isinstance(tables, dict):
        raise HTTPException(status_code=422, detail="JSON table bundle must be an object")
    for group, values in tables.items():
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                rows.append({"__entity_type": group.removesuffix("s"), **value})
    return rows, "bundle"


@router.post("/imports/{uid}/file/")
async def upload_import(uid: uuid.UUID, request: Request):
    context = _authorized(request, "crm.transfer.import")
    length = request.headers.get("content-length")
    if length and int(length) > MAX_UPLOAD_BYTES + 64 * 1024:
        raise HTTPException(status_code=413, detail="Import file exceeds 20 MiB")
    body = await request.body()
    filename, content_type, content = _multipart_file(request.headers.get("content-type", ""), body)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Import file exceeds 20 MiB")
    try:
        job = _store(request)._job_row(uid, context.actor_uid)
        manifest = job.get("input_manifest")
        if isinstance(manifest, str):
            manifest = json.loads(manifest)
        rows, fallback_type = _parse_rows(
            job["adapter_id"], (manifest or {}).get("entity_type"), content
        )
        if len(rows) > MAX_ROWS:
            raise HTTPException(status_code=413, detail="Import exceeds 20,000 rows")
        # Bundles keep the per-row type.  The store receives one batch label for
        # the deterministic UID and uses the embedded value in later adapters.
        return _store(request).stage_upload(
            context.actor_uid,
            uid,
            filename,
            content_type,
            hashlib.sha256(content).hexdigest(),
            rows,
            fallback_type,
        )
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc


@router.put("/imports/{uid}/mapping/")
def save_mapping(
    uid: uuid.UUID,
    request: Request,
    payload: ImportMapping,
):
    context = _authorized(request, "crm.transfer.import")
    try:
        return _store(request).save_mapping(
            context.actor_uid,
            uid,
            payload.model_dump(mode="json"),
        )
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc


@router.post("/imports/{uid}/validate/")
def validate_import(uid: uuid.UUID, request: Request):
    context = _authorized(request, "crm.transfer.import")
    try:
        return _store(request).validate_import(context.actor_uid, uid)
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc


@router.get("/imports/{uid}/plan/")
def import_plan(uid: uuid.UUID, request: Request):
    context = _authorized(request, "crm.transfer.import")
    try:
        return _store(request).plan(context.actor_uid, uid)
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc


@router.post("/imports/{uid}/commit/", status_code=202)
def commit_import(
    uid: uuid.UUID,
    request: Request,
    payload: ImportCommitRequest,
):
    context = _authorized(request, "crm.transfer.import")
    try:
        return _store(request).commit_import(
            context.actor_uid,
            uid,
            payload.model_dump(mode="json"),
        )
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc


@router.get("/transfers/{uid}/")
def transfer_detail(uid: uuid.UUID, request: Request):
    context = _authorized(request, "crm.read")
    try:
        return _store(request).transfer_detail(uid, context.actor_uid)
    except ResourceNotFound as exc:
        raise _translate_error(exc) from exc


@router.get("/transfers/{uid}/issues/")
def transfer_issues(uid: uuid.UUID, request: Request):
    context = _authorized(request, "crm.read")
    try:
        return _store(request).issues(context.actor_uid, uid, *_page(request))
    except ResourceNotFound as exc:
        raise _translate_error(exc) from exc


@router.get("/transfers/{uid}/errors.csv")
def transfer_errors(uid: uuid.UUID, request: Request):
    context = _authorized(request, "crm.read")
    try:
        report = _store(request).errors_csv(context.actor_uid, uid)
    except ResourceNotFound as exc:
        raise _translate_error(exc) from exc
    return Response(
        report,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="crm-import-errors.csv"'},
    )


def _transfer_action(uid: uuid.UUID, request: Request, action: str):
    context = _authorized(request, "crm.read")
    store = _store(request)
    try:
        job = store._job_row(uid, context.actor_uid)
        required = "crm.transfer.import" if job["direction"] == "import" else "crm.transfer.export"
        if required not in context.capabilities:
            raise HTTPException(status_code=403, detail=f"{required} access denied")
        return getattr(store, action)(context.actor_uid, uid)
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc


@router.post("/transfers/{uid}/cancel/", status_code=202)
def cancel_transfer(
    uid: uuid.UUID,
    request: Request,
):
    return _transfer_action(uid, request, "cancel")


@router.post("/transfers/{uid}/retry/", status_code=202)
def retry_transfer(
    uid: uuid.UUID,
    request: Request,
):
    return _transfer_action(uid, request, "retry")


def create_export(
    request: Request,
    payload: CreateExport,
):
    context = _authorized(request, "crm.transfer.export")
    try:
        return _store(request).create_export(
            context.actor_uid,
            payload.model_dump(mode="json"),
        )
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc


def download_export(uid: uuid.UUID, request: Request):
    context = _authorized(request, "crm.transfer.export")
    try:
        content, content_type, filename = _store(request).download_export(context.actor_uid, uid)
    except (ResourceConflict, ResourceNotFound) as exc:
        raise _translate_error(exc) from exc
    return Response(
        content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
