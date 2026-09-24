# Deals and pipelines API

See [deals and pipelines](../concepts/deals-pipelines.md) for the business
model. Paths are under `/api/crm/v1/`.

## Deals

| Method | Path | Body / behavior |
| --- | --- | --- |
| `GET` | `deals/discovery/` | Discovery; `crm.read` |
| `GET` | `deals/` | Paged collection; `crm.read` |
| `POST` | `deals/` | `DealCreate`, `201`, `crm.create` |
| `GET` | `deals/{uid}/` | Detail; `crm.read` |
| `PATCH` | `deals/{uid}/` | `DealPatch`; `crm.edit` |
| `POST` | `deals/{uid}/archive/` | Version command; `crm.archive` |
| `POST` | `deals/{uid}/restore/` | Version command; `crm.archive` |
| `POST` | `deals/{uid}/move/` | `MoveDeal`; `crm.edit` |

`DealCreate` requires `pipeline_uid`, `stage_uid`, `name`, and a three-letter
`currency`. Optional `amount` is a decimal string such as `"4500.50"`, never
a JSON number. `DealPatch` cannot change pipeline or stage; use the move
command for board changes.

```json
{
  "expected_version": 4,
  "expected_board_version": 9,
  "target_stage_uid": "11111111-1111-4111-8111-111111111111",
  "before_deal_uid": null
}
```

The two expected versions fence both the deal and board view.

## Pipeline board reads

| Method | Path | Query / behavior |
| --- | --- | --- |
| `GET` | `pipelines/` | Pipeline collection; `crm.read` |
| `GET` | `pipelines/{uid}/board/` | `page_size` (default 25), optional `search` and `filters`; `crm.read` |
| `GET` | `pipelines/{uid}/stages/{stage_uid}/cards/` | Required `expected_board_version`; optional `page_size`, `cursor`, `search`, `filters`; `crm.read` |

The current stage-card implementation interprets `cursor` as a nonnegative
offset string, not an opaque keyset cursor. A changed board version returns
`409`. Pipeline and stage write routes are not mounted in this API version.
