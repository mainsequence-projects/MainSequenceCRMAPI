# ADR 0001: Simple Solution Selling assessment model

- **Status:** Accepted and implemented; amended by [ADR 0003](0003-key-players-pain-chain.md)
- **Date:** 2026-09-24
- **Scope:** Initial assessment domain model, persistence, and optional API
- **Input:** User-supplied “Solution Selling — simple API domain model,” with the direct Company relationship added here

## Context

Solution Selling is an optional sales methodology applied to an existing CRM
Deal. The initial model records the business problem, purchasing authority,
buyer's desired capabilities, expected value, and decision process. It does
not need separate entities for each dimension or for a person's role in the
opportunity.

The supplied draft obtains the company through `Deal.company_uid`. This ADR
adds a **direct `company_uid` foreign key to `Company` on the assessment**.
Company identity must not be inferred from a selected Contact or their
affiliation: a Contact may have worked for several companies, and the selected
pain, power, and sponsor contacts can differ.

## Decision

Introduce one proposed module-owned model, `SolutionSelling`. A Deal has zero
or one assessment; each assessment belongs to exactly one Deal and one
Company. `deal_uid` is unique. `company_uid` is required and references the
existing Company model. The three person fields reference existing Contacts;
there is no `OpportunityStakeholder` or other wrapper around Contact.

The business-field declaration is:

> **Amendment:** The declaration below records ADR 0001's initial shape.
> [ADR 0003](0003-key-players-pain-chain.md) adds `key_players` and replaces
> the free-text `pain_chain` with a structured list of links. Read the two
> ADRs together for the current proposed model.

```python
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SolutionSelling(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    deal_uid: UUID                    # FK -> Deal.uid; UNIQUE; required
    company_uid: UUID                 # FK -> Company.uid; required

    pain_summary: str | None = None
    pain_contact_uid: UUID | None = None     # FK -> Contact.uid

    power_summary: str | None = None
    power_contact_uid: UUID | None = None    # FK -> Contact.uid
    sponsor_contact_uid: UUID | None = None  # FK -> Contact.uid

    vision_summary: str | None = None
    value_summary: str | None = None
    control_summary: str | None = None

    pain_chain: str | None = None  # Replaced by ADR 0003
    evaluation_plan: str | None = None
```

This is a **Pydantic domain declaration**, not an implemented class or a
database constraint. The eventual SQLAlchemy MetaTable must enforce the
stated foreign keys and unique Deal relationship. Standard record metadata,
versioning, and authorship follow CRM conventions and are omitted here.

### Relationship rules

| Relationship | Cardinality / rule |
| --- | --- |
| `Deal` → `SolutionSelling` | One Deal has zero or one assessment; `deal_uid` is required and unique. |
| `Company` → `SolutionSelling` | One Company can have many assessments; each assessment has exactly one direct `company_uid` foreign key. |
| `Contact` → `SolutionSelling` | A Contact may be selected in any of the three optional roles on many assessments. The roles may reference the same Contact. |

```text
Deal (1) ----------- (0..1) SolutionSelling
  |                            |
  | company_uid                | company_uid --------> Company (1)
  +----------------------------+ (must identify the same Company)
                               |
                               +-- pain_contact_uid ---> Contact (0..1)
                               +-- power_contact_uid --> Contact (0..1)
                               +-- sponsor_contact_uid --> Contact (0..1)
```

Because the Deal already has `company_uid`, the two company references must
not diverge. An assessment can be created only for a Deal with a Company, and
`SolutionSelling.company_uid` must equal `Deal.company_uid`. Any later Deal
company change must preserve this invariant atomically or be rejected. This
direct FK is intentional: the assessment can identify its Company without
traversing the Deal or guessing from Contact affiliations. It does **not**
make Contact affiliation or a selected person's employer the account source.

### Attribute meanings

| Attribute | Meaning |
| --- | --- |
| `pain_summary` | Problem, causes, consequences, and what is known versus assumed. |
| `pain_contact_uid` | Main known Contact experiencing or owning the problem. |
| `power_summary` | Purchasing authority and access as currently understood. |
| `power_contact_uid` | Principal identified Contact with relevant authority. |
| `sponsor_contact_uid` | Principal Contact helping advance the opportunity. |
| `vision_summary` | Buyer's desired capabilities, not the seller's product-feature list. |
| `value_summary` | Expected business improvement, measurements, and assumptions; distinct from Deal amount. |
| `control_summary` | Decision process, commitments, and outstanding decisions. |
| `pain_chain` | Originally a narrative; replaced by the structured links in [ADR 0003](0003-key-players-pain-chain.md). |
| `evaluation_plan` | Proposed or agreed evaluation, responsibilities, criteria, and next commitments. |

All assessment text and person roles may be missing while discovery is in
progress. Selecting a Contact does not prove that person's authority or
agreement. Narratives should distinguish seller assumptions from buyer
statements and proposed steps from agreed commitments. This first version
does not add a confirmation or evidence model.

## Module boundary and consequences

The CRM's Deal, Company, and Contact records remain the source of their
ordinary commercial and identity fields. The assessment adds only the
methodology-specific fields above. No stakeholder, pain, capability,
value-measure, evaluation-step, evidence, or relationship-table models are
part of this initial design. ADR 0003 retains the single assessment record
but makes `key_players` and `pain_chain` embedded structured attributes;
`evaluation_plan` remains text. No independent Pain or PainChain table is
introduced.

The proposed [core CRM Interaction](../../crm_core/adrs/0001-interaction.md)
records a particular conversation, its preparation, and its outcome.
`SolutionSelling` is the maintained assessment across conversations. An
Interaction may reference the same Deal, but neither record has a direct
foreign key to the other.

The module is optional under `extensions.solution_selling.active` in
`config/crm.yaml` (ADR 0004 supersedes the original environment switch).
Activation is deployment availability, not authorization; existing platform
identity and policy still govern access. Disabling
the module must not be interpreted as deleting stored assessments.

**Implementation status:** Migration `0006` adds the assessment table and a
composite Deal–Company foreign key. Pydantic contracts validate its embedded
key players and pain chain. The [Solution Selling API](../../api/solution-selling.md)
mounts only when the flag is enabled.
