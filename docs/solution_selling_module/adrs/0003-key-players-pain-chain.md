# ADR 0003: Key players and pain chain are embedded attributes

- **Status:** Accepted and implemented
- **Date:** 2026-09-24
- **Amends:** [ADR 0001: Simple assessment model](0001-simple-assessment-model.md), replacing its free-text `pain_chain`
- **Relates to:** [ADR 0002: Diagnosis matrix](0002-diagnosis-matrix.md)

## Context

The `SolutionSelling` record is the maintained assessment of an opportunity.
It needs to identify **which existing Contacts have which primary business
problems** and **how those problems affect one another**. This is more
specific than one overall `pain_summary`, but it does not require new
Stakeholder, Pain, or PainChain entities in the initial design.

ADR 0001 declared `pain_chain` as free text. This ADR replaces that one
field with typed, embedded links and adds an embedded `key_players` list.
The two lists remain attributes of the same `SolutionSelling` record.

## Decision

Each `KeyPlayerPain` entry references an existing `Contact`. It records that
Contact's **one primary pain in this opportunity**, zero or more reasons,
and the current assessment status. A Contact can appear once in a given
`SolutionSelling.key_players` list and can have a different pain in another
opportunity. An entry may exist before its pain is understood.

Each `PainChainLink` connects the primary pains of two different Contacts
already present in the same `key_players` list. The direction means the
first pain contributes to the second. The explanation describes the
business relationship, **not** a reporting line or organization chart.
The chain may branch; it need not be a single path.

The proposed Pydantic value types and amended assessment fields are:

```python
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


AssessmentStatus = Literal["hypothesis", "reported", "confirmed"]


class KeyPlayerPain(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_uid: UUID                 # Reference -> existing Contact.uid
    pain: str | None
    reasons: list[str]
    status: AssessmentStatus


class PainChainLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_contact_uid: UUID            # Contact in this assessment's key_players
    to_contact_uid: UUID              # Another Contact in the same key_players
    explanation: str
    status: AssessmentStatus


# Replace/extend these fields inside the SolutionSelling class in ADR 0001:
key_players: list[KeyPlayerPain] = Field(default_factory=list)
pain_chain: list[PainChainLink] = Field(default_factory=list)
```

The last two lines show **only the amended fields**, not a second
`SolutionSelling` declaration. Its UID, Deal and Company foreign keys,
summaries, primary-contact references, and `evaluation_plan` remain as in
ADR 0001. `KeyPlayerPain` and `PainChainLink` are embedded Pydantic value
types, **not** independent CRM models, identities, tables, or endpoints.

### Relationships and invariants

| Rule | Meaning |
| --- | --- |
| One key-player entry per Contact per assessment | `contact_uid` is unique within one `key_players` list. It is not a new person identity. |
| One primary pain per key player | `pain` may be null while discovery continues; `reasons` may be empty. |
| Link endpoints exist locally | Both Contact UIDs in a link must occur in this assessment's `key_players`. |
| Linked pains are known | Both endpoint entries need a recorded pain before a link is valid. |
| Directed, nontrivial links | Reject a self-link and duplicate `(from_contact_uid, to_contact_uid)` pairs. Reverse direction is a distinct claim. |
| Independent status | The status on each pain and on each link is assessed separately. Confirming both pains does not confirm their relationship. |

```text
SolutionSelling (one Deal / one Company)
|
+-- key_players[]
|   +-- Contact A -> primary pain A -> reasons[] -> status
|   +-- Contact B -> primary pain B -> reasons[] -> status
|   +-- Contact C -> primary pain C -> reasons[] -> status
|
+-- pain_chain[]
    +-- Contact A / pain A --[explanation, status]--> Contact B / pain B
    +-- Contact B / pain B --[explanation, status]--> Contact C / pain C
    +-- Contact A / pain A --[explanation, status]--> Contact C / pain C
```

The final link illustrates branching. These arrows connect **pains**, using
Contact UIDs as endpoints because this initial version has one primary pain
per Contact. They do not imply job seniority or reporting relationships.

A reusable [prospecting profile pattern](0004-prospecting-profiles.md) links
potential pains by **profile UID** before named buyers are known. This
opportunity-specific chain instead links the actual Contacts' assessed pains.
The general pattern may suggest what to investigate, but must never populate
or confirm this chain automatically.

### Assessment status

| Value | Meaning |
| --- | --- |
| `hypothesis` | The seller's current assumption. |
| `reported` | Someone described it, but it has not been directly established with the relevant buyer. |
| `confirmed` | The specific pain or specific link was explicitly acknowledged. |

The status does not identify who made or confirmed a statement. This small
version has no separate evidence model; users must not present an unverified
link as confirmed merely because its endpoint pains are confirmed.

## Relationship to diagnosis

A [Solution Selling diagnosis](0002-diagnosis-matrix.md) belongs to a
particular Interaction and Contact; the two attributes in this ADR belong to
the maintained opportunity assessment. Answers about **reasons** can inform
the Contact's pain and its reasons. Answers about **impact** can inform
pain-chain links. Answers about **capabilities** can inform the assessment's
buying vision. None of these updates is automatic, and a diagnosis answer
does not by itself change an assessment status.

## Consequences and limits

This design makes the pain chain inspectable and validates its links without
adding tables for stakeholders, pains, links, or questions. It deliberately
supports only one linked primary pain per Contact. If a later version needs
several separately linked pains for one Contact, it will need pain-specific
identifiers and a new ADR rather than overloading Contact UIDs.

**Current status:** Pydantic validates the embedded values and relationships;
migration `0006` stores them as typed assessment content. The optional
[assessment API](../../api/solution-selling.md) exposes them without new
stakeholder or pain tables.
