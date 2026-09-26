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

When starting a Solution Selling opportunity, the user may select an existing
Deal or quickly create one in the default pipeline. The new Deal is linked to
an explicitly selected or newly created Company and an active open stage; its Company is then
carried into the opportunity assessment. An assessment still requires its Deal
and Company to match. Company and Deal creation are separate commits; quick
creation does not create the assessment until the user saves that form.
