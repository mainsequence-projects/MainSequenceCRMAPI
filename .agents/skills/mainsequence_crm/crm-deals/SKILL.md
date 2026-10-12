---
name: crm-deals
description: Find, create and edit CRM Deals, review pipelines and stages, and move cards with Deal and board version fences through MCP. Use for opportunity and pipeline requests, including stage placement and currency-aware summaries.
---

# Deals and pipelines

Read [shared MCP guidance](skill://crm-core/references/mcp-usage.md). Use
[CRM core](skill://crm-core/SKILL.md) for Contact, Company, owner and settings lookups;
use [discovery](skill://solution-selling/crm-discovery/SKILL.md) for an opportunity's
Solution Selling evidence.

## Tool selection

| Need | Tools |
| --- | --- |
| Find and inspect opportunities | `crm_deals_list`, `crm_deals_get` |
| Save a new Deal or edit its ordinary fields | `crm_deals_create`, `crm_deals_update` |
| Find a pipeline and inspect its metadata | `crm_pipelines_list`, `crm_pipelines_get` |
| Resolve stage UIDs, order and current board version | `crm_pipelines_stages` |
| Inspect cards and relative placement | `crm_pipelines_board` |
| Move or reorder a Deal | `crm_deals_move` |

## Review a pipeline or save a Deal

1. Resolve the Deal by name plus Company/pipeline or other returned facts.
   For a new Deal, resolve the intended pipeline and a stage belonging to it.
   Use stages when only stage metadata is needed; use the board for cards.
   Stage names can repeat across pipelines.
2. Board card results are bounded. Inspect returned paging before describing
   all Deals or totals; use filtered `crm_deals_list` pages for additional
   records. The catalogue does not expose a dedicated stage-card paging tool.
3. A create needs name, pipeline, stage and three-letter currency. Resolve any
   requested Company, Contact and owner references. Check likely duplicates;
   leave optional unknowns omitted.
4. Represent an amount as a decimal string, such as `"4500.50"`. Clarify an
   ambiguous currency or closing date. Keep currencies separate in summaries
   and label totals computed from incomplete results.
5. Save with create; edit ordinary fields with a fresh Deal version and
   requested changes. Generic update cannot change pipeline or stage. Report
   only the successful business result and returned version.

## Move or reorder

1. Read the Deal and its pipeline's current stages or board. Resolve the target
   stage in the same pipeline. For a requested relative position, verify the
   neighboring Deal belongs to the target stage using current reads.
2. Call `crm_deals_move` with `uid` and a `payload` containing
   `expected_version` from the Deal, `expected_board_version` from the pipeline
   view, `target_stage_uid` and required nullable `before_deal_uid`. Use the
   neighboring Deal UID to insert before it; null places the Deal at the end.
   Do not simulate this atomic command with generic patches or several writes.
3. Inspect the returned Deal, `board_version` and `invalidated_stage_uids`.
   Refresh affected views if the user needs the resulting board.
4. On a version conflict, reread both Deal and board and reconcile the same
   requested placement. Do not reuse stale fences or silently select a new
   destination. Follow shared recovery guidance for an uncertain write.

The catalogue has no pipeline/stage creation or editing, or command for moving
a Deal into a different pipeline. Explain that limit when requested; do not
create stages or duplicate a Deal to imitate a cross-pipeline move.
