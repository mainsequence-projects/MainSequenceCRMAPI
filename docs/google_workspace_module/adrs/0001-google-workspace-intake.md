# ADR 0001: User-authorized Google Workspace intake

- **Status:** Accepted; source implementation is gated and deployed public ingress/OAuth remain unverified
- **Date:** 2026-09-24
- **Scope:** Gmail and Google Contacts contact intake; Google Calendar meeting import
- **Depends on:** [Core Interaction](../../crm_core/adrs/0001-interaction.md) and the existing
  [Contact](../../concepts/contacts.md) and [transfer](../../concepts/transfers.md)
  boundaries
- **Setup:** [Google Cloud and OAuth client guide](../setup.md)

## Context

A CRM user wants to add contacts from their Google account, including people
found in Gmail, and import meetings from Google Calendar. Saved address-book
contacts live in Google Contacts (People API); Gmail messages can reveal
additional correspondents. The existing CRM Contact record can hold a person's
name, email addresses, phone numbers, and company affiliation. The core
Interaction record can hold a meeting, but requires a Company and has only one
optional primary Contact. Existing source connections identify file import
sources; they do not hold OAuth credentials or provide a live Google connector.

Google contacts, email, and calendar data belong to a particular Google
account. A person in an email header is not necessarily a CRM contact, and an
invitation is not evidence that a meeting took place. Importing these into CRM
may expose them to other CRM users according to platform policy. The user must
see and approve that transfer.

## Decision

Build a **read-only, per-user Google connection** for explicit, reviewed
imports. The CRM backend owns the Google API calls and import orchestration;
the Command Center frontend presents connection state, source selection,
bounded previews, matching choices, and results. Google credentials and raw
message payloads stay server-side; the frontend receives only the selected
candidate fields needed for review. The platform's injected identity and
policy remain the authority for CRM actions;
Google authorization only permits reading that user's Google data.

The first release is **user initiated**: connect, choose saved Google Contacts,
a bounded Gmail query, or a calendar and date range; review candidates; then
commit selected items. There is no background mailbox scan, bidirectional
sync, Google Contacts write, Gmail send/modify, or Calendar write. A later ADR
may add ongoing synchronization if needed.

### Connection and permissions

Use **user-delegated Google OAuth 2.0 Authorization Code**, with a confidential
Google **Web application** client on the FastAPI backend, PKCE `S256`, and
OpenID Connect only to identify which Google account granted access. Google
authorization is a connection to a data source; it does not sign the user in
to CRM. The CRM continues to use the platform-injected principal and policy.
Do not use a service account, domain-wide delegation, a user-supplied app
password, or a browser-held Google access token.

#### Google Cloud and runtime setup

Create a Google Cloud project, enable the People, Gmail, and Calendar APIs,
configure the OAuth consent screen for the intended users, and create a Web
application OAuth client. Once the CRM FastAPI release has active exact-path
public ingress for the callback and completion page, register the exact URI
`https://<crm-api-host>/extensions/google/oauth/callback/` for each deployed
environment; use a separately registered localhost URI for local development.
Production uses HTTPS. Store the client ID, client secret, and token-encryption
key as three separate Main Sequence **Secrets** named
`CRM_GOOGLE_OAUTH_CLIENT_ID`, `CRM_GOOGLE_OAUTH_CLIENT_SECRET`, and
`CRM_GOOGLE_TOKEN_ENCRYPTION_KEY`, accessible only to the API runtime. The first
two values come from the Google Cloud Web OAuth client; the third is a
CRM-generated key for encrypting stored per-user Google grants. All three are
required before the API can start a Google connection, even when the extension
is active. The exact callback URI is runtime environment configuration. Credentials do not belong
in the repository, frontend, a Constant, or a CRM MetaTable. Main Sequence
Secrets hold deployment configuration, not one Secret per Google user.
Set `extensions.google_workspace.active: true` in `config/crm.yaml` to mount
this optional extension; the frontend uses `modules.google_workspace` from CRM
bootstrap. The value does not grant a CRM capability. ADR 0004 supersedes the
original environment-switch decision.

Main Sequence workflow API `2.3.0` supports exact `public_ingress` method/path
pairs on a FastAPI release. Declare the two `GET` paths above in the CRM API
workflow, or update the identified existing release through the canonical
`resource_release.update` operation if its live MCP schema accepts the field.
A ready active revision must snapshot the
policy before Google can reach it. Read `resource_release.get` to confirm
`public_ingress`, `effective_public_ingress`, and the backend-issued
`public_url`; append the callback path to that URL and register the result in
Google. All other CRM routes stay bearer protected. Public admission provides
no Main Sequence user identity; the callback consumes the one-time OAuth state
and PKCE verifier. The full [setup procedure](../setup.md#configure-public-callback-routes-on-main-sequence)
includes workflow validation and unauthenticated probes. No public ingress
declaration or deployed callback result has yet been verified for this CRM.

The user grants each source when they open that import feature:

| Source | Google API scope requested with `openid email` | Purpose |
| --- | --- | --- |
| Saved Google Contacts | `https://www.googleapis.com/auth/contacts.readonly` | Read selected address-book people through the People API. |
| Gmail correspondents | `https://www.googleapis.com/auth/gmail.readonly` | Search selected messages and read the headers needed to propose contacts. |
| Calendar meetings | `https://www.googleapis.com/auth/calendar.events.readonly` | Read events from a selected calendar. |
| Calendar picker | `https://www.googleapis.com/auth/calendar.calendarlist.readonly` | List calendars; requested with Calendar authorization, while a manual calendar ID still works if this optional scope is declined. |

Do not request write scopes. The backend checks the scopes actually granted
after each consent; a declined scope leaves only that source unavailable.
Gmail read-only is a **restricted** scope even if the application fetches only
headers. Before production, determine the consent-screen verification and
security-assessment requirements for the chosen Internal or External Google
app audience and complete those that apply.

#### Authorization exchange

The following paths are mounted when the extension flag is enabled:

| Step | Owner and behavior |
| --- | --- |
| `POST /extensions/google/oauth/start/` | Authenticated CRM request with `{ "source": "contacts" | "gmail" | "calendar" }`; require the current platform actor and `crm.transfer.import`. Return an `authorization_url`, opaque `attempt_uid`, and 600-second lifetime, never a Google token. |
| Browser redirect | Open Google's consent page in a top-level browser navigation. Do not use an embedded webview. |
| `GET /extensions/google/oauth/callback/` | Google redirects with `code` and `state` or an error. This endpoint consumes one pending attempt and exchanges the code server-side. It must not require a browser bearer token or create CRM contacts; configure exact public ingress for deployment. |
| `GET /extensions/google/oauth/done/` | Fixed token-free completion page in the new tab; configure exact public ingress for deployment. |
| `GET /extensions/google/oauth/attempts/{uid}/` | The initiating platform actor polls through the normal authenticated transport; a ready result supplies the one-time completion handle. |
| `POST /extensions/google/oauth/complete/` | Frontend sends `{ "completion_handle": "…" }` through the normal authenticated CRM transport. Only the same platform actor who started the attempt can finalize the connection; return a token-free connection summary. |
| `GET /extensions/google/connections/` | Return the actor's Google account label, granted source scopes, and status; never token material. |
| `POST /extensions/google/connections/{uid}/disconnect/` | Require that connection's platform actor and `crm.transfer.import`; disconnect the entire Google grant. |
| `GET /extensions/google/calendars/` | Read the connected user's calendar list when that scope was granted. |
| `POST /extensions/google/preview/` | Bounded People, Gmail-header, or Calendar preview with source-specific selection. |
| `POST /extensions/google/imports/` | One reviewed create, link, update, or skip decision using an actor-bound encrypted preview token. |

At `start`, generate a cryptographically random 256-bit `state`, PKCE verifier
and `S256` challenge, and an OIDC `nonce`. Persist only a hash of `state`, the
encrypted verifier, nonce, initiating platform actor UID, requested scopes,
and expiry in a backend-only MetaTable attempt record shared by API replicas.
The attempt expires after ten minutes and can be consumed once. After consent,
use a fixed API completion page. No redirect target comes from the callback
query.

Redirect to `https://accounts.google.com/o/oauth2/v2/auth` with
`response_type=code`, the configured `client_id`, the exact registered
`redirect_uri`, `scope=openid email` plus the selected source scopes,
`state`, `nonce`, `code_challenge`, `code_challenge_method=S256`,
`access_type=offline`, and `include_granted_scopes=true`. Request
`prompt=consent` for a first connection or when a replacement refresh token
is needed; do not force it on every import.

At the callback, reject missing, expired, or already consumed `state`. On
`access_denied`, consume the attempt and return to the fixed completion page with a
safe denial status; do not exchange a code. Exchange an approved code once at
`https://oauth2.googleapis.com/token` with `grant_type=authorization_code`,
the confidential client credentials, exact redirect URI, and stored
`code_verifier`. Verify the Google ID token's signature, issuer, audience,
expiry, and `nonce`; use its `sub` claim as the Google account key. Email is
display-only and can change. Check the token response's granted scopes before
enabling a source. If an existing actor extends a connection, the returned
`sub` must match that connection. The first release permits one active Google
account per platform actor and one platform actor per Google `sub`; connecting
a different account requires an explicit disconnect.

The callback stores the refresh credential and completion handle only in
encrypted, short-lived pending state, then redirects the new tab to a fixed,
token-free API completion page. The original embedded CRM window polls the
attempt through its authenticated transport; only the initiating platform
actor can receive the one-time completion handle. No authorization code,
access token, refresh token, ID token, or raw Google error appears in a URL.
The pending result expires after five minutes. `complete` rechecks the
platform actor and `crm.transfer.import`, then atomically activates the
connection and consumes the handle. An actor mismatch or expired handle
cannot activate it. A later incremental consent
may omit a refresh token; keep the existing encrypted token in that case, and
fail connection setup if neither an existing nor a new refresh token exists.

#### Credential lifecycle and access boundary

Use a dedicated backend-only `google_oauth_connection` MetaTable, separate
from the existing file-import `SourceConnection`. It records the platform
actor UID, Google `sub`, display email, granted scopes, status, version, and
encrypted refresh-token payload. Enforce uniqueness for an active actor and
an active Google `sub`. Encrypt each refresh token before storage
with AES-256-GCM, a fresh random nonce, key version, and authenticated data
covering the connection UID and actor UID. Keep the encryption key in the
Main Sequence Secret described above; rotate by re-encrypting stored tokens.
The table must not be shared with the frontend or general CRM readers. Never
store token plaintext in MetaTables, `SourceConnection.configuration`, audit
before/after data, logs, URLs, or client state. Access tokens live server-side
only for the current Google request and are refreshed using the stored token
when needed.

Every preview/import request resolves a connection owned by the current
platform actor, checks `crm.transfer.import` and the required granted Google
scope, then calls Google. A denied or revoked scope cannot be bypassed by a
previously saved preview. On Google `invalid_grant` or equivalent revocation,
mark the connection `reauthorization_required`, stop Google reads, and prompt
the actor to reconnect. Do not delete CRM records already imported.

Disconnect stops new reads immediately, revokes the refresh token through
Google's revocation endpoint, deletes local token ciphertext, and marks the
connection disconnected. Google revocation removes the project's grant for
that account, so this first release disconnects all Google sources together;
it does not claim to revoke one scope independently. If remote revocation
fails, remove local access anyway and report that Google account settings may
still show the grant. A background task, if later introduced, must recheck
current platform authorization at each execution boundary and never inherit
an old browser session's authority.

### Google Contacts and Gmail to CRM Contact

Offer saved Google Contacts through the People API with a limited field mask:
names, email addresses, phone numbers, and organization details needed for a
reviewed CRM proposal. Preserve each selected person's Google resource
name as source provenance. A saved Google Contact is a candidate, not a CRM
record until the user confirms it. Do not silently copy every address-book
field or turn a Google organization into a CRM Company.

Read only messages within the user's selected mailbox query or label and
bounded date range. Fetch the headers needed for review, and extract candidate
names and addresses from sender and recipient headers; treat display names as
untrusted hints. Do not fetch message bodies or attachments for contact
discovery.
Normalize email addresses for matching, but retain the displayed original for
review. Exclude the connected account's own address by default and allow the
user to discard any candidate. Show an existing-contact match, an ambiguous
match, or a new-contact proposal. The user chooses create, link, or skip; an
ambiguous address never triggers an automatic merge. Do not infer Company,
owner, newsletter consent, or a completed Interaction from an email alone.
Creating a contact uses the existing versioned, governed CRM command and
platform actor. If the user edits a matched contact, use its expected version.
For a new Contact, open a review form prefilled with the selected Google
candidate's name and contact methods. Saving passes only the reviewed Contact
fields with the sealed preview token; the backend validates them as a CRM
Contact and writes the Contact and source provenance in one governed command.
Opening the form or skipping a candidate never writes a CRM record.
When the same address appears in Google Contacts and Gmail, show a possible
match for review and retain both source references only if the user confirms
they identify the same person.

### Google Calendar to Interaction

Show selected events as meeting candidates, including summary, start/end,
time zone, organizer, attendees, and cancellation state. Filter out event
types that are not meetings (for example all-day birthdays and focus time)
unless the user explicitly includes them. Use the event source key, including
calendar ID and event/recurrence-instance identity, to recognize a prior
import. A recurring occurrence must not collapse into its series or a
different occurrence.

For each selected event, the user must choose a CRM Company, because
`Interaction.company_uid` is required. Contact and Deal are optional and must
obey the Interaction's existing relationship checks. Create `kind="meeting"`;
map the event start to `scheduled_at`. Do not fill `occurred_at` or mark an
event completed just because its scheduled time has passed. Let the user
confirm `planned`, `completed`, or `cancelled`, and edit the subject before
commit. Do not store the full attendee list in `contact_uid`; it identifies
only one primary Contact. Calendar changes or deletions after import do not
silently overwrite or archive a CRM Interaction. A repeat import shows the
existing link and offers a reviewed, version-fenced update.

### Import boundary and failure handling

The Google adapter is distinct from the existing file adapters and must not
pretend to be supported by `ImportAdapterId` or the current upload routes.
Provide a bounded preview with counts, conflicts, missing Company choices,
and per-item decisions. Commit through the existing domain services and
governed MetaTable operations, with the current actor, capability checks,
entity version fences, and source identities. The source identity key is
scoped to the Google account, source kind, and immutable Google item ID, so
repeating a selection finds the same CRM target. Commit each target change,
its source link, and its audit event atomically. After an uncertain response,
read server state before retrying; do not add an `Idempotency-Key` or command
receipt requirement. Partial failures must report which items committed and
which require review. Expired/revoked Google authorization must stop the read
and ask the user to reconnect without pretending that the import succeeded.

Minimize retained Google data: keep source IDs, hashes, chosen CRM fields,
and small diagnostic metadata needed for reconciliation. Do not retain raw
mail bodies, attachments, or complete attendee lists. Avoid logging private
message, contact, or event details. The preview expires; selected CRM records
persist under CRM policy. The user must be told which imported data will
become visible to other authorized CRM users.

## Consequences

- Contact and meeting imports use existing domain records and a separate
  backend-only credential store. The OAuth, preview, and commit routes mount
  only when `extensions.google_workspace.active: true` in `config/crm.yaml`. Provider migration
  `0008` and live Google/deployed verification remain required.
- Gmail's restricted read scope may require significant verification work
  before a production rollout. A pilot cannot be described as production
  ready until Google consent and data-handling requirements are met.
- Source records remain editable CRM records after import. Google is a source
  of reviewed suggestions, not an ongoing authority over local edits.

## Rejected alternatives

| Alternative | Reason |
| --- | --- |
| Read every mailbox or address book and auto-create contacts | Creates false matches, stores excessive private data, and bypasses review. |
| Treat a calendar event as completed after its end time | Scheduled time does not prove the meeting occurred. |
| Use Google sign-in or Workspace directory as CRM identity | Duplicates the platform's established principal and policy boundary. |
| Reuse the file-upload transfer adapter unchanged | It has no Google OAuth, source selection, or live-source provenance contract. |

## Delivery and verification

The source implementation adds the OAuth routes, credential storage, and
source-preview contracts. Before release, verify state/PKCE/nonce replay
protection, exact redirect matching, ID-token account binding, callback without
a platform bearer token, completion by the same actor only, missing refresh
tokens, partial scope grants, cross-principal isolation, revocation and
`invalid_grant`, duplicate and ambiguous contacts, recurring and
cancelled events, missing Company, source re-import, stale CRM versions,
partial failure and restart, and governed atomic rollback. Verify a fresh
process resolves any new MetaTable catalog bindings. Update mounted API and
delivery documentation with only behavior actually shipped, then run the
repository's strict MkDocs and relevant code/contract tests. A production
release also needs Google OAuth verification and any applicable security
assessment.

## Google API references

- [Google Contacts listing and field mask](https://developers.google.com/people/api/rest/v1/people.connections/list)
  and [read-only contact scope](https://developers.google.com/people/v1/contacts)
- [Gmail message list and retrieval](https://developers.google.com/workspace/gmail/api/guides/list-messages)
  and [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)
- [Calendar events and scopes](https://developers.google.com/workspace/calendar/api/auth),
  [recurring events](https://developers.google.com/workspace/calendar/api/guides/recurringevents),
  and [incremental synchronization](https://developers.google.com/workspace/calendar/api/guides/sync)
- [OAuth for server-side web apps](https://developers.google.com/identity/protocols/oauth2/web-server)
- [Google OpenID Connect ID-token validation and `sub`](https://developers.google.com/identity/openid-connect/openid-connect)
- [Google OAuth security practices](https://developers.google.com/identity/protocols/oauth2/resources/best-practices)
- [Main Sequence Constants and Secrets](https://mainsequence-sdk.github.io/mainsequence-sdk/knowledge/infrastructure/constants_and_secrets/)
