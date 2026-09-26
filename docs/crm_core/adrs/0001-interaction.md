# ADR 0001: Interaction is a core CRM model

- **Status:** Accepted; implemented in migration `0006`
- **Date:** 2026-09-24
- **Scope:** Core CRM domain model, persistence, and mounted API
- **Input:** User-supplied Interaction declaration and relationship rules

## Context

The CRM needs a record for a particular planned or completed conversation:
what was known beforehand, what the user intended to establish, and what was
actually learned. Calls, meetings, workshops, and email exchanges are useful
even when a team does not use Solution Selling. They can also happen before
a Deal exists.

The current CRM has Notes and read-only Activity events, but no `Interaction`
model. A Note is narrative attached to a contact or deal; an Activity event
records a CRM change. Neither owns the lifecycle and preparation/outcome of
one conversation.

## Decision

`Interaction` belongs to **core CRM**. One record represents one planned,
completed, or cancelled call, meeting, workshop, or email exchange. It has
a required direct Company reference, an optional primary Contact, and an
optional Deal. It does not have a `solution_selling_uid`, methodology-specific
columns, or a required opportunity.

The proposed Pydantic business-field declaration is:

```python
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict


class Interaction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    company_uid: UUID                 # FK -> Company.uid; required
    contact_uid: UUID | None = None   # FK -> Contact.uid; primary contact
    deal_uid: UUID | None = None      # FK -> Deal.uid; optional

    subject: str
    kind: Literal["call", "meeting", "workshop", "email"]
    status: Literal["planned", "completed", "cancelled"]

    scheduled_at: AwareDatetime | None = None
    occurred_at: AwareDatetime | None = None

    objective: str | None = None
    research_notes: str | None = None
    discussion_plan: str | None = None

    outcome_notes: str | None = None
    next_steps: str | None = None
```

The implemented Pydantic model also carries normal record metadata,
versioning, and authorship. SQLAlchemy MetaTable migration `0006` created the
table; the [Interactions API](../../api/interactions.md) describes mounted routes.

### Relationships

| Relationship | Cardinality and rule |
| --- | --- |
| `Company` → `Interaction` | One Company has many Interactions; each Interaction belongs to exactly one Company. |
| `Contact` → `Interaction` | One Contact may be primary on many Interactions; `contact_uid` is optional and is **not** a full attendee list. |
| `Deal` → `Interaction` | One Deal may have many Interactions; `deal_uid` is optional, allowing pre-deal conversations. |

```text
Company (1) <-------- (many) Interaction
                             |
                             +-- contact_uid (optional) --> Contact
                             |
                             +-- deal_uid (optional) ----> Deal
                                                            |
                                                            +-- optional SolutionSelling
                                                                assessment (separate module)
```

If an Interaction names a Deal, the Deal must identify the same Company as
`Interaction.company_uid`. A Deal without a company cannot be linked until
its company is set. The Interaction's Company must **not** be derived from
the primary Contact or that Contact's company affiliations. A Contact can
have historical affiliations or participate as an adviser; this ADR does
not impose an affiliation requirement on `contact_uid`.

### Conversation fields

| Field | Meaning |
| --- | --- |
| `objective` | Intended result of the conversation. |
| `research_notes` | Known context and assumptions to verify beforehand. |
| `discussion_plan` | Topics and questions to cover. |
| `outcome_notes` | What was actually discussed, learned, or confirmed. |
| `next_steps` | Follow-up agreed afterward, distinct from the hoped-for objective. |

Research and questions remain text in this first version. There are no
question, research, or participant models in this ADR. The one `contact_uid`
is the primary contact, not an assertion that no one else attended.

## Relationship to Solution Selling

The optional [Solution Selling assessment](../../solution_selling_module/adrs/0001-simple-assessment-model.md)
stores the maintained understanding of a Deal. An Interaction stores what
happened in **one** conversation. When both reference the same Deal, the
conversation may inform the assessment, but this is a conceptual relationship
through the Deal, not a new foreign key or automatic synchronization.

For example, `outcome_notes` may say that a desk head reported deployment
delays. `SolutionSelling.pain_summary` may later summarize the current
understanding of that problem. Recording the conversation does not itself
mark the assessment as buyer-confirmed. Generic CRM and other modules can
use Interaction without enabling Solution Selling.

The proposed [Solution Selling diagnosis](../../solution_selling_module/adrs/0002-diagnosis-matrix.md)
is an add-on record that references an Interaction. It does not add a
`solution_selling_uid` or a question matrix to the core Interaction model.

## Deferred decisions

This small model does not define a complete attendee list, structured
questions, evidence links, automated extraction, or status-specific timestamp
validation. Those need separate decisions if required; they are not reasons
to make Interaction a Solution Selling-owned object now.

**Current status:** Implemented as a core CRM model, without a Solution Selling
foreign key. The API is mounted regardless of the optional module flag.
