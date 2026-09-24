# HTTP API

This section describes the routes mounted by `api.crm.main:app`. The base path
is `/api/crm/v1/`; `/healthz` is outside that prefix. Paths keep their trailing
slash. The running FastAPI app exposes generated OpenAPI at `/openapi.json` and
interactive schemas at `/docs`.

Start with [request conventions](conventions.md), then use the route group for
the concept you need:

| Route group | Purpose |
| --- | --- |
| [Contacts and companies](contacts-companies.md) | People, organizations, archive/restore, contact merge |
| [Deals and pipelines](deals-pipelines.md) | Opportunities, board reads, deal moves |
| [Tasks, notes, tags, and activity](engagement.md) | Follow-up work, narrative, labels, read-only history |
| [Imports and transfers](transfers.md) | Source connections, staged imports, job state and reports |
| [Service and settings](service.md) | Readiness, bootstrap, principal, settings, process health |

The API is consumed through Command Center's delegated transport. The API
does not accept a browser-supplied identity or application tenant selector as authority.
Only mounted routes are documented as available; [delivery status](../delivery/verification.md)
records the separate live-platform checks still required.
