# ADR 0002: Diagnosis uses an embedded 3 × 3 matrix

- **Status:** Accepted and implemented
- **Date:** 2026-09-24
- **Scope:** Solution Selling diagnosis domain, persistence, and optional API
- **Depends on:** Proposed core CRM [Interaction](../../crm_core/adrs/0001-interaction.md) and optional [Solution Selling assessment](0001-simple-assessment-model.md)

## Context

An [Interaction](../../crm_core/adrs/0001-interaction.md) records a particular
conversation and remains useful to all of CRM. A `SolutionSelling` assessment
holds the maintained understanding of a Deal. Diagnosis is the
methodology-specific work done in relation to a conversation: the business
issue explored, questions asked, answers recorded, and conclusion reached.
It belongs to the Solution Selling module, **not** to the core Interaction.

A flat question list would lose the structure of the nine diagnostic cells.
Each cell is the intersection of a **question approach** (open, control /
focused, confirming) and a **diagnostic subject** (reasons, impact,
capabilities). The position of a question in the matrix identifies both
dimensions; an entry does not repeat them as fields.

## Decision

Add one proposed record type, `SolutionSellingDiagnosis`. Its `matrix` is
embedded structured content in that record. `DiagnosisEntry`, `DiagnosisRow`,
and `DiagnosisMatrix` below are **Pydantic value types**, not CRM entities,
MetaTables, or independently addressable question records.

```python
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DiagnosisEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str
    answer: str | None = None


class DiagnosisRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reasons: list[DiagnosisEntry] = Field(default_factory=list)
    impact: list[DiagnosisEntry] = Field(default_factory=list)
    capabilities: list[DiagnosisEntry] = Field(default_factory=list)


class DiagnosisMatrix(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open: DiagnosisRow = Field(default_factory=DiagnosisRow)
    control: DiagnosisRow = Field(default_factory=DiagnosisRow)
    confirming: DiagnosisRow = Field(default_factory=DiagnosisRow)


class SolutionSellingDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    interaction_uid: UUID                      # FK -> Interaction.uid; required
    contact_uid: UUID                          # FK -> Contact.uid; required
    solution_selling_uid: UUID | None = None   # FK -> SolutionSelling.uid

    business_issue: str
    matrix: DiagnosisMatrix = Field(default_factory=DiagnosisMatrix)
    conclusion: str | None = None
```

This is the typed domain declaration used by implemented code and a physical
storage prescription. The eventual persisted diagnosis is **one record**;
its matrix is validated through these Pydantic types. All nine cells are
represented, but each list may be empty or contain several entries. No
question, answer, row, or cell table is introduced by this ADR.

### The nine cells

| Question approach ↓ / Diagnostic subject → | Reasons | Impact | Capabilities |
| --- | --- | --- | --- |
| **Open** | Explore why the problem exists. | Explore its consequences. | Explore what the buyer needs to do differently. |
| **Control / focused** | Investigate specific causes. | Investigate specific consequences. | Explore specific required capabilities. |
| **Confirming** | Confirm the understanding of causes. | Confirm the understanding of impact. | Confirm the buyer's required capabilities. |

For example, a focused question about impact belongs in
`matrix.control.impact`:

```python
diagnosis.matrix.control.impact.append(
    DiagnosisEntry(
        question="Does this delay reduce the number of strategies you can evaluate?",
        answer="Yes, but we have not measured how many.",
    )
)
```

`business_issue` is context for the whole square. `conclusion` records what
the diagnosis established. An unanswered prepared question has `answer=None`;
it is not silently treated as confirmed. Questions and answers remain on
this diagnosis even if the maintained `SolutionSelling` summary changes.

### Relationships

| Relationship | Cardinality and rule |
| --- | --- |
| `Interaction` → `SolutionSellingDiagnosis` | One Interaction may have multiple diagnoses; each diagnosis references exactly one Interaction. |
| `Contact` → `SolutionSellingDiagnosis` | Each diagnosis identifies one existing Contact; a Contact can appear in many diagnoses. There is no new person model. |
| `SolutionSelling` → `SolutionSellingDiagnosis` | Optional. A diagnosis may precede an assessment; one assessment may later be linked to many diagnoses. |

```text
CORE CRM                                SOLUTION SELLING MODULE

Interaction (1) <---------------------- SolutionSellingDiagnosis (many)
Contact (1)     <----------------------          |
                                               +-- business_issue
                                               +-- matrix
                                               |    open       x reasons / impact / capabilities
                                               |    control    x reasons / impact / capabilities
                                               |    confirming x reasons / impact / capabilities
                                               +-- conclusion
SolutionSelling (0..1) <----------------          |
```

There is no reverse `solution_selling_uid` on Interaction. If a diagnosis
links to a `SolutionSelling` assessment, the assessment and Interaction must
refer to the same Company. If the Interaction also references a Deal, it must
be the assessment's Deal. A diagnosis can be recorded before either Deal or
assessment exists; the optional link can be added later without moving the
original conversation. `contact_uid` is explicit and is not inferred from
Interaction's optional primary contact or from a company affiliation.

## Consequences and limits

The model preserves the 3 × 3 structure without creating nine columns or
nine child tables. It supports multiple questions per cell and keeps the
generic Interaction free of methodology-specific data. It does not define a
separate evidence system, automatic propagation into `pain_summary`, or a
requirement to fill every cell. Updating the maintained assessment is a
separate, deliberate action.

The proposed [key-player and pain-chain attributes](0003-key-players-pain-chain.md)
are maintained on `SolutionSelling`, not on this conversation-specific
diagnosis. Answers about reasons and impact may inform them, but do not
automatically overwrite or confirm them.

A reusable [prospecting profile](0004-prospecting-profiles.md) may supply a
starting question matrix. The diagnosis retains its own copy of the
questions actually used and the answers recorded; editing the profile later
does not rewrite this Interaction's history.

**Current status:** Pydantic validates the nine-cell matrix; migration `0006`
adds the diagnosis table, and the optional [API](../../api/solution-selling.md)
exposes it. General evidence automation remains outside this decision.
