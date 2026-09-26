# ADR 0005: A lead is the prospecting record for a Contact

- **Status:** Accepted and implemented
- **Date:** 2026-09-24
- **Scope:** Solution Selling prospecting model, persistence, and optional API
- **Relates to:** Reusable [prospecting profiles](0004-prospecting-profiles.md) and existing CRM [Contacts](../../concepts/contacts.md) and [Tasks](../../concepts/tasks-notes.md)

## Context

A Contact is a person and their contact information. It does not mean that
the team is pursuing that person. A Task is a particular piece of work, such
as making a call. The Solution Selling prospecting list needs a record of
**why a Contact was selected, who is responsible, how far the outreach has
progressed, and which Task is next**. It must not create another person or
copy contact details.

The provisional `ProspectingTarget`/`ProspectingFunnel` ideas mentioned in
earlier discussion are replaced for this initial design by **one lead model
and its status**. There is no separate `Lead` and `Prospect` pair, and no
funnel-stage table in this version.

## Decision

Add one proposed module-owned model, `SolutionSellingLead`. It references
an existing Contact. A lead can be created as soon as that person is
selected for outreach; a profile, next Task, Deal, or confirmed pain is
**not** required.

```python
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SolutionSellingLead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    contact_uid: UUID                 # FK -> Contact.uid; required
    profile_uid: UUID | None = None   # FK -> SolutionSellingProspectingProfile.uid
    owner_uid: UUID | None = None     # Existing platform user, not a CRM user table

    status: Literal[
        "to_contact",
        "contacted",
        "qualified",
        "nurture",
        "disqualified",
    ]

    next_task_uid: UUID | None = None  # FK -> existing Task.uid
    notes: str | None = None
```

This is a proposed Pydantic business-field declaration, not implemented
code. Standard CRM record metadata, versioning, and authorship are omitted.
The initial lead list has at most one `SolutionSellingLead` per Contact;
re-engagement updates that record rather than creating another person or
a duplicate prospecting row. A future need for multiple concurrent
campaigns concerning one Contact would require an explicit new scope.

### Relationships and meaning

| Field | Relationship / meaning |
| --- | --- |
| `contact_uid` | Required existing Contact. Name, email, phone, and history remain on Contact. |
| `profile_uid` | Optional reusable role–potential-pain hypothesis from ADR 0004. Selecting it does not establish that Contact's actual pain. |
| `owner_uid` | Optional existing platform user responsible for pursuing the lead; no new CRM identity model. |
| `next_task_uid` | Optional pointer to the **current next action** in the existing Task model, not the lead's whole task or Interaction history. |
| `notes` | Lead-specific prospecting context, not copied Contact data or a replacement for Task details. |

```text
SolutionSellingProspectingProfile (0..1)
                 ^
                 | profile_uid
          SolutionSellingLead
             |          |
 contact_uid |          | next_task_uid (0..1)
             v          v
        Contact (1)   Task (0..1)
```

If `next_task_uid` is set, the Task must belong to the same Contact as the
lead. The next-action pointer should name an open Task; when that Task is
completed, the pointer must be cleared or changed before it is presented as
upcoming work. The Task owns its text, type, due date, owner, and completion
state. The lead does not duplicate those fields. A lead without a Task still
belongs in the list and can be shown as needing a next action.

The lead does not have `company_uid`, `deal_uid`, or `solution_selling_uid`
in this initial model. Contact affiliations can be historical or multiple;
the lead does not infer a target Company from one. A later opportunity may
involve several leads, but qualifying a lead does not automatically create
a Deal or a `SolutionSelling` assessment.

When a [prompter](0006-reusable-prompters.md) is used for this lead, the
relevant Company is selected for that use. It is not silently inferred from
the Contact's possibly multiple affiliations.

### Status is progress, not outreach history

| Status | Meaning |
| --- | --- |
| `to_contact` | Selected for outreach; first meaningful contact has not yet been made. |
| `contacted` | Outreach has occurred; relevance is not yet established. |
| `qualified` | Relevant problem or opportunity has been established sufficiently to pursue. This does not imply a Deal exists. |
| `nurture` | Not ready for active pursuit; retain for later follow-up. |
| `disqualified` | Not being pursued under the present assessment. |

Status is not a count of calls or emails. Those actions belong to Tasks and
eventual [Interactions](../../crm_core/adrs/0001-interaction.md). No
`ProspectingFunnel` or separate `Prospect` model is needed for these initial
states. Status changes must not turn a selected profile's potential pain
into a confirmed fact.

## Consequences and current status

The lead list can combine the Contact, optional profile, lead status, and
current Task to show whom to call or follow up. The lead belongs to the
Solution Selling prospecting module, not to an opportunity's assessment.
This preserves the distinction **Contact = person; Lead = prospecting
effort; Task = next action**.

**Current status:** The lead table and Pydantic/API contracts are implemented
in migration `0006`. It references existing Contact and Task records, not
new identity or work models. The [API](../../api/solution-selling.md) is
available only when the module flag is on.
