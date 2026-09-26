"""HTTP transport adapters for durable CRM imports and exports."""

from __future__ import annotations

import uuid
from email.parser import BytesParser
from email.policy import default

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from api.crm.query import parse_page, parse_query
from src.crm.models.import_mapping import ImportMapping
from src.crm.models.transfers import (
    CreateExport,
    CreateImport,
    ImportCommitRequest,
    SourceConnectionCreate,
)
from src.crm.platform.runtime import request_port
from src.crm.services.transfers import (
    MAX_UPLOAD_BYTES,
    TransferOperations,
    parse_import_rows,
)

from .service_adapter import context_for, invoke

router = APIRouter(prefix="/api/crm/v1")


def _service(request: Request) -> TransferOperations:
    return TransferOperations(context_for(request), request_port(request, "crm_transfers"))


def _page(request: Request) -> tuple[int, int]:
    page = invoke(lambda: parse_page(dict(request.query_params)))
    return page.page_index, page.page_size


@router.get("/source-connections/")
def list_source_connections(request: Request):
    service = _service(request)
    invoke(lambda: service.context.require("crm.transfer.import"))
    page_index, page_size = _page(request)
    return invoke(lambda: service.source_connections(page_index, page_size))


@router.post("/source-connections/", status_code=201)
def create_source_connection(request: Request, payload: SourceConnectionCreate):
    return invoke(lambda: _service(request).create_source_connection(payload))


@router.get("/transfers/discovery/")
def transfer_discovery(request: Request):
    invoke(lambda: _service(request).context.require("crm.read"))
    invoke(lambda: parse_query("transfers", dict(request.query_params), discovery=True))
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
    service = _service(request)
    invoke(lambda: service.context.require("crm.read"))
    scope = invoke(lambda: parse_query("transfers", dict(request.query_params)))
    return invoke(lambda: service.list_transfers(scope))


@router.post("/imports/", status_code=201)
def create_import(request: Request, payload: CreateImport):
    return invoke(lambda: _service(request).create_import(payload))


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


# Compatibility for existing parsing tests; the implementation is in src/crm.
_parse_rows = parse_import_rows


@router.post("/imports/{uid}/file/")
async def upload_import(uid: uuid.UUID, request: Request):
    service = _service(request)
    invoke(lambda: service.context.require("crm.transfer.import"))
    length = request.headers.get("content-length")
    if length and int(length) > MAX_UPLOAD_BYTES + 64 * 1024:
        raise HTTPException(status_code=413, detail="Import file exceeds 20 MiB")
    body = await request.body()
    filename, content_type, content = _multipart_file(request.headers.get("content-type", ""), body)
    return invoke(lambda: service.upload_import(uid, filename, content_type, content))


@router.put("/imports/{uid}/mapping/")
def save_mapping(uid: uuid.UUID, request: Request, payload: ImportMapping):
    return invoke(lambda: _service(request).save_mapping(uid, payload))


@router.post("/imports/{uid}/validate/")
def validate_import(uid: uuid.UUID, request: Request):
    return invoke(lambda: _service(request).validate_import(uid))


@router.get("/imports/{uid}/plan/")
def import_plan(uid: uuid.UUID, request: Request):
    return invoke(lambda: _service(request).import_plan(uid))


@router.post("/imports/{uid}/commit/", status_code=202)
def commit_import(uid: uuid.UUID, request: Request, payload: ImportCommitRequest):
    return invoke(lambda: _service(request).commit_import(uid, payload))


@router.get("/transfers/{uid}/")
def transfer_detail(uid: uuid.UUID, request: Request):
    return invoke(lambda: _service(request).transfer_detail(uid))


@router.get("/transfers/{uid}/issues/")
def transfer_issues(uid: uuid.UUID, request: Request):
    service = _service(request)
    invoke(lambda: service.context.require("crm.read"))
    page_index, page_size = _page(request)
    return invoke(lambda: service.transfer_issues(uid, page_index, page_size))


@router.get("/transfers/{uid}/errors.csv")
def transfer_errors(uid: uuid.UUID, request: Request):
    report = invoke(lambda: _service(request).transfer_errors(uid))
    return Response(
        report,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="crm-import-errors.csv"'},
    )


@router.post("/transfers/{uid}/cancel/", status_code=202)
def cancel_transfer(uid: uuid.UUID, request: Request):
    return invoke(lambda: _service(request).transfer_action(uid, "cancel"))


@router.post("/transfers/{uid}/retry/", status_code=202)
def retry_transfer(uid: uuid.UUID, request: Request):
    return invoke(lambda: _service(request).transfer_action(uid, "retry"))


def create_export(request: Request, payload: CreateExport):
    return invoke(lambda: _service(request).create_export(payload))


def download_export(uid: uuid.UUID, request: Request):
    content, content_type, filename = invoke(lambda: _service(request).download_export(uid))
    return Response(
        content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
