"""Bounded Google source previews and explicit CRM import decisions."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from email.utils import getaddresses
from typing import Any, Literal
from urllib.parse import quote

import httpx
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from src.crm.models.common import Email, Phone
from src.crm.models.contacts import ContactCreate
from src.crm.models.interactions import InteractionCreate
from src.crm.repositories.errors import ResourceConflict

from .security import CALENDAR_PICKER_SCOPE, SCOPES, digest
from .service import GoogleWorkspaceService, _scopes, _uid


class ContactProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    first_name: str | None = Field(default=None, max_length=255)
    last_name: str | None = Field(default=None, max_length=255)
    title: str | None = Field(default=None, max_length=255)
    emails: list[Email] = Field(default_factory=list, max_length=20)
    phones: list[Phone] = Field(default_factory=list, max_length=20)


class ImportDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preview_token: str = Field(min_length=32, max_length=16000)
    action: Literal["create", "link", "update", "skip"]
    target_uid: uuid.UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)
    company_uid: uuid.UUID | None = None
    contact_uid: uuid.UUID | None = None
    deal_uid: uuid.UUID | None = None
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal["planned", "completed", "cancelled"] | None = None
    contact_fields: ContactProposal | None = None


class PreviewQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["contacts", "gmail", "calendar"]
    page_token: str | None = Field(default=None, max_length=1024)
    gmail_query: str | None = Field(default=None, max_length=200)
    calendar_id: str | None = Field(default=None, min_length=1, max_length=512)
    time_min: AwareDatetime | None = None
    time_max: AwareDatetime | None = None


def _name(value: str | None) -> tuple[str | None, str | None]:
    parts = (value or "").strip().split(None, 1)
    return (parts[0][:255] if parts else None, parts[1][:255] if len(parts) > 1 else None)


def _email(value: str | None) -> str | None:
    if not value or len(value) > 320 or "@" not in value:
        return None
    return value.strip().casefold()


class GoogleImports:
    def __init__(self, oauth: GoogleWorkspaceService):
        self.oauth = oauth

    def _get(self, url: str, access: str, params: dict[str, Any] | None = None) -> dict:
        try:
            response = self.oauth.http.get(
                url, headers={"Authorization": f"Bearer {access}"}, params=params
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("Google response is invalid")
            return body
        except (httpx.HTTPError, ValueError) as exc:
            raise ResourceConflict("Google source could not be read") from exc

    def calendars(self, actor_uid: uuid.UUID) -> dict:
        access, connection = self.oauth.access_token(actor_uid, "calendar")
        if CALENDAR_PICKER_SCOPE not in _scopes(connection.get("granted_scopes")):
            raise ResourceConflict("Google calendar list permission was not granted")
        body = self._get(
            "https://www.googleapis.com/calendar/v3/users/me/calendarList", access,
            {"maxResults": 100, "fields": "items(id,summary,primary),nextPageToken"},
        )
        return {
            "items": [
                {"id": item["id"], "summary": item.get("summary", item["id"]), "primary": bool(item.get("primary"))}
                for item in body.get("items", []) if isinstance(item, dict) and isinstance(item.get("id"), str)
            ],
            "next_page_token": body.get("nextPageToken"),
        }

    def preview(self, actor_uid: uuid.UUID, query: PreviewQuery) -> dict:
        access, connection = self.oauth.access_token(actor_uid, query.source)
        if query.source == "contacts":
            body = self._get(
                "https://people.googleapis.com/v1/people/me/connections", access,
                {"personFields": "names,emailAddresses,phoneNumbers,organizations", "pageSize": 50,
                 **({"pageToken": query.page_token} if query.page_token else {})},
            )
            candidates = self._people(body)
        elif query.source == "gmail":
            if not query.gmail_query or not query.gmail_query.strip():
                raise ValueError("Choose a bounded Gmail query before previewing")
            if not query.time_min or not query.time_max or query.time_max <= query.time_min or query.time_max - query.time_min > timedelta(days=90):
                raise ValueError("Gmail preview needs a date range of at most 90 days")
            bounded_query = (
                f"({query.gmail_query.strip()}) after:{int(query.time_min.timestamp())} "
                f"before:{int(query.time_max.timestamp())}"
            )
            body = self._get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages", access,
                {"q": bounded_query, "maxResults": 25,
                 **({"pageToken": query.page_token} if query.page_token else {})},
            )
            candidates = self._gmail(access, body, connection.get("display_email", ""))
        else:
            if not query.calendar_id or not query.time_min or not query.time_max:
                raise ValueError("Choose a calendar and date range")
            if query.time_max <= query.time_min or query.time_max - query.time_min > timedelta(days=90):
                raise ValueError("Calendar preview range must be at most 90 days")
            body = self._get(
                f"https://www.googleapis.com/calendar/v3/calendars/{quote(query.calendar_id, safe='')}/events",
                access,
                {"timeMin": query.time_min.isoformat(), "timeMax": query.time_max.isoformat(),
                 "singleEvents": "true", "showDeleted": "true", "maxResults": 50,
                 **({"pageToken": query.page_token} if query.page_token else {})},
            )
            candidates = self._events(body, query.calendar_id)
        source_uid = _uid(connection["source_connection_uid"])
        output = []
        entity_type = "interaction" if query.source == "calendar" else "contact"
        existing_by_id = self.oauth.store.source_links(
            source_uid, entity_type, [candidate["external_id"] for candidate in candidates]
        )
        matches_by_email = self.oauth.store.contact_matches_many([
            candidate["email"] for candidate in candidates
            if entity_type == "contact" and candidate.get("email")
            and candidate["external_id"] not in existing_by_id
        ])
        for candidate in candidates:
            existing = existing_by_id.get(candidate["external_id"])
            matches = (
                matches_by_email.get(candidate["email"], [])
                if entity_type == "contact" and candidate.get("email") and not existing else []
            )
            sealed = self.oauth.sealer.seal(
                {"candidate": candidate, "source": query.source, "google_sub": connection["google_sub"],
                 "expires_at": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp())},
                purpose="preview", uid=_uid(connection["uid"]), actor_uid=actor_uid,
            )
            output.append({
                "candidate": {key: value for key, value in candidate.items() if key != "external_id"},
                "preview_token": sealed,
                "existing_target_uid": str(existing["target_uid"]) if existing else None,
                "existing_target_version": int(existing["version"]) if existing and existing.get("version") else None,
                "existing_company_uid": str(existing["company_uid"]) if existing and existing.get("company_uid") else None,
                "existing_target_archived": bool(existing and (existing.get("archived_at") or existing.get("version") is None)),
                "matches": [
                    {"uid": str(match["uid"]), "version": int(match["version"]),
                     "name": " ".join(filter(None, [match.get("first_name"), match.get("last_name")]))}
                    for match in matches
                ],
            })
        return {"items": output, "next_page_token": body.get("nextPageToken")}

    @staticmethod
    def _people(body: dict) -> list[dict]:
        result = []
        for person in body.get("connections", []):
            if not isinstance(person, dict) or not isinstance(person.get("resourceName"), str):
                continue
            names = person.get("names") or []
            primary_name = names[0] if names and isinstance(names[0], dict) else {}
            emails = []
            for item in person.get("emailAddresses") or []:
                address = _email(item.get("value") if isinstance(item, dict) else None)
                if address and address not in emails:
                    emails.append(address)
            phones = []
            for item in person.get("phoneNumbers") or []:
                number = item.get("value") if isinstance(item, dict) else None
                if isinstance(number, str) and 0 < len(number.strip()) <= 100 and number not in phones:
                    phones.append(number.strip())
            first = (primary_name.get("givenName") or "").strip()[:255] or None
            last = (primary_name.get("familyName") or "").strip()[:255] or None
            if not (first or last or emails):
                continue
            result.append({
                "external_id": f"people:{person['resourceName']}", "source": "contacts",
                "first_name": first, "last_name": last, "email": emails[0] if emails else None,
                "emails": emails[:20], "phones": phones[:20],
            })
        return result

    def _gmail(self, access: str, body: dict, self_email: str) -> list[dict]:
        people: dict[str, dict] = {}
        for item in body.get("messages", [])[:25]:
            message_id = item.get("id") if isinstance(item, dict) else None
            if not isinstance(message_id, str) or not message_id:
                continue
            message = self._get(
                f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{quote(message_id, safe='')}",
                access, {"format": "metadata", "metadataHeaders": ["From", "To", "Cc"]},
            )
            headers = message.get("payload", {}).get("headers", [])
            selected = [h.get("value", "") for h in headers if isinstance(h, dict) and h.get("name", "").casefold() in {"from", "to", "cc"}]
            for display, raw_email in getaddresses(selected):
                email = _email(raw_email)
                if not email or email == self_email.casefold() or email in people:
                    continue
                first, last = _name(display)
                people[email] = {
                    "external_id": f"gmail:{email}", "source": "gmail",
                    "first_name": first, "last_name": last, "email": email,
                    "emails": [email], "phones": [],
                }
        return list(people.values())

    @staticmethod
    def _events(body: dict, calendar_id: str) -> list[dict]:
        result = []
        for event in body.get("items", []):
            if not isinstance(event, dict) or event.get("eventType", "default") not in {"default", "fromGmail"}:
                continue
            start = event.get("start") or {}
            when = start.get("dateTime") if isinstance(start, dict) else None
            event_id = event.get("id")
            if not isinstance(when, str) or not isinstance(event_id, str):
                continue
            subject = (event.get("summary") or "Meeting").strip()[:255] or "Meeting"
            result.append({
                "external_id": f"calendar:{calendar_id}:{event_id}", "source": "calendar",
                "subject": subject, "scheduled_at": when,
                "end_at": (event.get("end") or {}).get("dateTime"),
                "time_zone": start.get("timeZone"),
                "organizer": (event.get("organizer") or {}).get("email"),
                "attendees": [a.get("email") for a in (event.get("attendees") or [])[:10] if isinstance(a, dict)],
                "status": "cancelled" if event.get("status") == "cancelled" else "planned",
            })
        return result

    def commit(self, actor_uid: uuid.UUID, decision: ImportDecision) -> dict:
        connection = self.oauth.store.connection(actor_uid)
        if not connection or connection["status"] != "connected":
            raise ResourceConflict("Connect Google before importing")
        payload = self.oauth.sealer.open(
            decision.preview_token, purpose="preview", uid=_uid(connection["uid"]), actor_uid=actor_uid
        )
        if int(payload["expires_at"]) <= int(datetime.now(UTC).timestamp()):
            raise ResourceConflict("Google preview expired; review the source again")
        source = payload["source"]
        if source not in SCOPES or not all(scope in _scopes(connection["granted_scopes"]) for scope in SCOPES[source]):
            raise ResourceConflict("Google source permission is unavailable")
        if payload["google_sub"] != connection["google_sub"]:
            raise ResourceConflict("Google account changed; review the source again")
        candidate = payload["candidate"]
        if decision.action == "skip":
            return {"status": "skipped"}
        entity_type = "interaction" if source == "calendar" else "contact"
        if decision.contact_fields is not None and (entity_type != "contact" or decision.action != "create"):
            raise ValueError("Contact fields are accepted only when creating a Contact")
        source_uid = _uid(connection["source_connection_uid"])
        external_id = candidate["external_id"]
        existing = self.oauth.store.source_link(source_uid, entity_type, external_id)
        if existing and decision.action != "update":
            raise ResourceConflict("Google item is already linked to a CRM record")
        if decision.action == "update" and (not existing or str(existing["target_uid"]) != str(decision.target_uid)):
            raise ResourceConflict("Google item is not linked to this CRM record")
        if entity_type == "contact":
            if decision.action == "update":
                raise ValueError("Edit linked contacts in the CRM contact editor")
            proposed = decision.contact_fields.model_dump(mode="json") if decision.contact_fields is not None else {
                "first_name": candidate.get("first_name"),
                "last_name": candidate.get("last_name"),
                "emails": [{"email": email, "type": "other"} for email in candidate.get("emails", [])],
                "phones": [{"number": number, "type": "other"} for number in candidate.get("phones", [])],
            }
            data = ContactCreate.model_validate(proposed).model_dump(mode="json")
        else:
            if decision.action == "create" and decision.company_uid is None:
                raise ValueError("Choose a CRM Company for this meeting")
            if decision.action == "update" and decision.company_uid is None:
                raise ValueError("Choose the linked meeting's CRM Company")
            data = InteractionCreate.model_validate({
                "company_uid": decision.company_uid, "contact_uid": decision.contact_uid,
                "deal_uid": decision.deal_uid,
                "subject": decision.subject or candidate["subject"],
                "kind": "meeting", "status": decision.status or candidate["status"],
                "scheduled_at": candidate["scheduled_at"],
            }).model_dump(mode="json") if decision.action != "link" else {}
        uid = self.oauth.store.import_candidate(
            actor_uid=actor_uid,
            source_connection_uid=source_uid,
            entity_type=entity_type,
            external_id=external_id,
            payload_hash=digest(json.dumps(candidate, sort_keys=True, separators=(",", ":"))),
            action=decision.action,
            target_uid=decision.target_uid,
            expected_version=decision.expected_version,
            values=data,
        )
        return {"status": "imported", "entity_type": entity_type, "target_uid": str(uid)}
