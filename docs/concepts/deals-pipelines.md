# Deals and pipelines

A pipeline groups ordered stages. A stage has a stable key, label, position,
active flag, and outcome (`open`, `won`, or `lost`). A deal belongs to one
pipeline and one stage. It may also link a company, an owner, and contacts.

Deal amounts are decimal **strings** with an explicit three-letter currency;
they are not JSON floating-point numbers. A deal also has a board position and
optional expected closing date. The pipeline's `board_version` protects a
multi-card view from mixing stale stages and moves.

The stage is not a general deal patch field. Moving a deal uses a dedicated
command with the deal version, board version, target stage, and optional
`before_deal_uid`. Board reads expose stages and paged card columns; consumers
must handle a changed board version as a conflict.

The current HTTP surface lists pipelines and reads boards, but does not mount
pipeline or stage create/edit endpoints even though typed models exist. See
the [deal and pipeline API](../api/deals-pipelines.md) for mounted routes.
