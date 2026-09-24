# Mounted route index

This is the exact method/path inventory exposed by `api.crm.main:app`.
The grouped pages explain payloads and behavior. Updating a mounted route also
requires updating this index; `tests/test_documentation.py` compares it with
FastAPI's generated OpenAPI paths.

| Method | Path | Reference |
| --- | --- | --- |
| `GET` | `/healthz` | [Service and settings](service.md) |
| `GET` | `/api/crm/v1/readiness/` | [Service and settings](service.md) |
| `GET` | `/api/crm/v1/bootstrap/` | [Service and settings](service.md) |
| `GET` | `/api/crm/v1/principals/` | [Service and settings](service.md) |
| `GET` | `/api/crm/v1/settings/` | [Service and settings](service.md) |
| `PATCH` | `/api/crm/v1/settings/` | [Service and settings](service.md) |
| `GET` | `/api/crm/v1/pipelines/{uid}/board/` | [Deals and pipelines](deals-pipelines.md) |
| `GET` | `/api/crm/v1/pipelines/{uid}/stages/{stage_uid}/cards/` | [Deals and pipelines](deals-pipelines.md) |
| `POST` | `/api/crm/v1/deals/{uid}/move/` | [Deals and pipelines](deals-pipelines.md) |
| `POST` | `/api/crm/v1/contacts/{uid}/merge/preview/` | [Contacts and companies](contacts-companies.md) |
| `POST` | `/api/crm/v1/contacts/{uid}/merge/` | [Contacts and companies](contacts-companies.md) |
| `POST` | `/api/crm/v1/contacts/{uid}/company-transition/` | [Contacts and companies](contacts-companies.md) |
| `GET` | `/api/crm/v1/contacts/{uid}/affiliations/` | [Contacts and companies](contacts-companies.md) |
| `POST` | `/api/crm/v1/contacts/{uid}/affiliations/` | [Contacts and companies](contacts-companies.md) |
| `GET` | `/api/crm/v1/contacts/{uid}/affiliations/{affiliation_uid}/` | [Contacts and companies](contacts-companies.md) |
| `PATCH` | `/api/crm/v1/contacts/{uid}/affiliations/{affiliation_uid}/` | [Contacts and companies](contacts-companies.md) |
| `GET` | `/api/crm/v1/companies/discovery/` | [Contacts and companies](contacts-companies.md) |
| `GET` | `/api/crm/v1/companies/` | [Contacts and companies](contacts-companies.md) |
| `POST` | `/api/crm/v1/companies/` | [Contacts and companies](contacts-companies.md) |
| `GET` | `/api/crm/v1/companies/{uid}/` | [Contacts and companies](contacts-companies.md) |
| `PATCH` | `/api/crm/v1/companies/{uid}/` | [Contacts and companies](contacts-companies.md) |
| `POST` | `/api/crm/v1/companies/{uid}/archive/` | [Contacts and companies](contacts-companies.md) |
| `POST` | `/api/crm/v1/companies/{uid}/restore/` | [Contacts and companies](contacts-companies.md) |
| `GET` | `/api/crm/v1/contacts/discovery/` | [Contacts and companies](contacts-companies.md) |
| `GET` | `/api/crm/v1/contacts/` | [Contacts and companies](contacts-companies.md) |
| `POST` | `/api/crm/v1/contacts/` | [Contacts and companies](contacts-companies.md) |
| `GET` | `/api/crm/v1/contacts/{uid}/` | [Contacts and companies](contacts-companies.md) |
| `PATCH` | `/api/crm/v1/contacts/{uid}/` | [Contacts and companies](contacts-companies.md) |
| `POST` | `/api/crm/v1/contacts/{uid}/archive/` | [Contacts and companies](contacts-companies.md) |
| `POST` | `/api/crm/v1/contacts/{uid}/restore/` | [Contacts and companies](contacts-companies.md) |
| `GET` | `/api/crm/v1/deals/discovery/` | [Deals and pipelines](deals-pipelines.md) |
| `GET` | `/api/crm/v1/deals/` | [Deals and pipelines](deals-pipelines.md) |
| `POST` | `/api/crm/v1/deals/` | [Deals and pipelines](deals-pipelines.md) |
| `GET` | `/api/crm/v1/deals/{uid}/` | [Deals and pipelines](deals-pipelines.md) |
| `PATCH` | `/api/crm/v1/deals/{uid}/` | [Deals and pipelines](deals-pipelines.md) |
| `POST` | `/api/crm/v1/deals/{uid}/archive/` | [Deals and pipelines](deals-pipelines.md) |
| `POST` | `/api/crm/v1/deals/{uid}/restore/` | [Deals and pipelines](deals-pipelines.md) |
| `GET` | `/api/crm/v1/tasks/discovery/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/tasks/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/tasks/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/tasks/{uid}/` | [Tasks, notes, tags, and activity](engagement.md) |
| `PATCH` | `/api/crm/v1/tasks/{uid}/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/tasks/{uid}/archive/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/tasks/{uid}/complete/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/tasks/{uid}/reopen/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/notes/discovery/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/notes/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/notes/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/notes/{uid}/` | [Tasks, notes, tags, and activity](engagement.md) |
| `PATCH` | `/api/crm/v1/notes/{uid}/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/notes/{uid}/archive/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/notes/{uid}/restore/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/tags/discovery/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/tags/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/tags/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/tags/{uid}/` | [Tasks, notes, tags, and activity](engagement.md) |
| `PATCH` | `/api/crm/v1/tags/{uid}/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/tags/{uid}/archive/` | [Tasks, notes, tags, and activity](engagement.md) |
| `POST` | `/api/crm/v1/tags/{uid}/restore/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/activity/discovery/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/activity/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/activity/{uid}/` | [Tasks, notes, tags, and activity](engagement.md) |
| `GET` | `/api/crm/v1/pipelines/` | [Deals and pipelines](deals-pipelines.md) |
| `GET` | `/api/crm/v1/source-connections/` | [Imports and transfers](transfers.md) |
| `POST` | `/api/crm/v1/source-connections/` | [Imports and transfers](transfers.md) |
| `GET` | `/api/crm/v1/transfers/discovery/` | [Imports and transfers](transfers.md) |
| `GET` | `/api/crm/v1/transfers/` | [Imports and transfers](transfers.md) |
| `POST` | `/api/crm/v1/imports/` | [Imports and transfers](transfers.md) |
| `POST` | `/api/crm/v1/imports/{uid}/file/` | [Imports and transfers](transfers.md) |
| `PUT` | `/api/crm/v1/imports/{uid}/mapping/` | [Imports and transfers](transfers.md) |
| `POST` | `/api/crm/v1/imports/{uid}/validate/` | [Imports and transfers](transfers.md) |
| `GET` | `/api/crm/v1/imports/{uid}/plan/` | [Imports and transfers](transfers.md) |
| `POST` | `/api/crm/v1/imports/{uid}/commit/` | [Imports and transfers](transfers.md) |
| `GET` | `/api/crm/v1/transfers/{uid}/` | [Imports and transfers](transfers.md) |
| `GET` | `/api/crm/v1/transfers/{uid}/issues/` | [Imports and transfers](transfers.md) |
| `GET` | `/api/crm/v1/transfers/{uid}/errors.csv` | [Imports and transfers](transfers.md) |
| `POST` | `/api/crm/v1/transfers/{uid}/cancel/` | [Imports and transfers](transfers.md) |
| `POST` | `/api/crm/v1/transfers/{uid}/retry/` | [Imports and transfers](transfers.md) |

Export creation and download routes are not mounted and therefore do not
appear here.
