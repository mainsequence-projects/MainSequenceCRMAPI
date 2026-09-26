# ADR 0004: Reusable role–pain prospecting profiles

- **Status:** Accepted for the profile; general profile links deferred
- **Date:** 2026-09-24
- **Scope:** Shared Solution Selling prospecting knowledge and profile implementation
- **Relates to:** [Diagnosis matrix](0002-diagnosis-matrix.md) and [opportunity key players](0003-key-players-pain-chain.md)

## Context

The existing Solution Selling ADRs describe **specific opportunity work**:
one assessment for a Deal, named Contacts and their assessed pains, and
diagnoses from particular conversations. Prospecting also needs reusable
knowledge **before** identifying a buyer: which business roles in a market
may encounter which problems, and how to investigate them.

That knowledge must not be confused with a finding about a real Contact.
“A research lead may struggle to operationalize approved strategies” is a
potential role–pain pattern. “This Contact confirmed that problem” belongs
to a specific diagnosis and opportunity assessment. Selecting a pattern
must not turn a hypothesis into a buyer-confirmed fact.

## Decision: one profile per context, role, and potential pain

Add one proposed reusable model, `SolutionSellingProspectingProfile`. One
record describes **one potential pain for one business role in one market
context**, with guidance for investigating it. Multiple profiles may share
the same role but describe different pains. The role is a business function
(for example, research lead), not an opportunity-specific purchase role
(for example, sponsor or decision-maker).

The proposed Pydantic business-field declaration is:

```python
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# DiagnosisMatrix is the embedded Pydantic value type from ADR 0002.


class SolutionSellingProspectingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    name: str
    market_context: str
    role: str
    potential_pain: str

    likely_reasons: list[str] = Field(default_factory=list)
    likely_impacts: list[str] = Field(default_factory=list)

    research_guidance: str | None = None
    opening_message: str | None = None
    suggested_next_commitment: str | None = None

    diagnosis_template: DiagnosisMatrix | None = None
```

This is a proposed declaration, not implemented code. `DiagnosisMatrix`
reuses the 3 × 3 open/control/confirming × reasons/impact/capabilities
structure of [ADR 0002](0002-diagnosis-matrix.md). In a profile it contains
**prepared questions only**: every entry's `answer` is null. In an actual
`SolutionSellingDiagnosis`, the copied questions and subsequent answers
belong to that conversation. Changing a reusable template cannot rewrite
an earlier diagnosis.

There is **no** `contact_uid`, `company_uid`, or `deal_uid` on this profile.
It is knowledge to test, not a person, account, opportunity, or assertion
about a buyer. Its text guidance is an approach to investigation, not a
claim that the potential pain is already established.

A reusable [prompter](0006-reusable-prompters.md) may reference a selected
profile's fields when drafting an introduction or call guide. The profile
remains the source of its potential pain; that text need not be copied into
every template.

### A reusable pain-chain pattern

The general chain links **profiles**, not role labels alone: a role may have
several potential pains. Each directed conceptual link has
`from_profile_uid`, `to_profile_uid`, and `explanation`. Both endpoints
identify existing profiles; self-links and duplicate directed links are
invalid. A pattern may branch.

```text
GENERAL PATTERN (reusable)                 SPECIFIC OPPORTUNITY (observed)

Research-lead profile A                    Contact A's assessed pain
  -- possible impact -->                     -- assessed impact -->
Desk-head profile B                        Contact B's assessed pain
  -- possible impact -->                     -- assessed impact -->
Business-head profile C                    Contact C's assessed pain
```

The general relationship suggests a question such as “if this research
problem exists, does it affect the desk head in this way?” It must not
automatically create or confirm a link in the
[opportunity's pain chain](0003-key-players-pain-chain.md). This ADR records
the relationship's meaning and endpoints; the exact persistence shape for
general links is deferred until that feature is implemented. It does not
introduce a separate person, pain, message, or question library model now.

## Applying the knowledge to an actual Contact

A profile is reusable guidance. [ADR 0005](0005-lead-list.md) defines the
proposed `SolutionSellingLead`: a prospecting record for a selected existing
Contact, with optional profile, owner, status, and next Task references.
The lead's status handles initial progress. The earlier idea of separate
`ProspectingTarget` and `ProspectingFunnel` models is **not part of the
current initial proposal**. No profile selection establishes a real buyer's
pain or automatically creates a Deal.

```text
REUSABLE KNOWLEDGE                  ACTUAL CRM WORK

ProspectingProfile
  role + potential pain
  suggested approach
         |
         v
SolutionSellingLead ---------------> existing Contact
         |
         +--------------------------> optional next Task
         |
         v
Interaction -----------------------> SolutionSellingDiagnosis
                                        |
                                        v  deliberate review, not auto-confirmation
                                  SolutionSelling (Deal assessment)
                                  key_players + pain_chain
```

Several Contacts at one Company may later contribute to one Deal and its
optional assessment. Prospecting must not create a new Deal for every
person approached. Diagnosis answers may inform the maintained assessment,
but neither template selection nor recorded answers automatically establish
its facts or statuses.

## Current status

**Current status:** The profile model, table, and optional API are implemented
in migration `0006`. General reusable pain-chain links between profiles are
still deferred as this ADR specified; there is no persistence shape yet.
