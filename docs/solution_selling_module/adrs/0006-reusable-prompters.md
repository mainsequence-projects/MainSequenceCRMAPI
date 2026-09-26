# ADR 0006: One reusable prompter model

- **Status:** Accepted and implemented
- **Date:** 2026-09-24
- **Scope:** Reusable Solution Selling text templates and bounded preview rendering
- **Relates to:** [Prospecting profiles](0004-prospecting-profiles.md) and [leads](0005-lead-list.md)

## Context

The team may need a company discovery message, introduction, follow-up, or
call-preparation guide. These vary in wording and purpose, but do not need
different CRM models. The template is reusable; the Contact, Company, Lead,
profile, Deal, and other facts are supplied **when it is used**. A template
must not embed permanent links to one customer merely because it was used
for that customer once.

This ADR calls the reusable record `SolutionSellingPrompter`. Its output is
prefilled text for review, not an automatically sent communication and not
a mutation of the template.

## Decision

Use one proposed Pydantic model with a Jinja template string:

```python
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SolutionSellingPrompter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uid: UUID
    name: str
    kind: str
    description: str | None = None
    template: str
```

`kind` is a flexible classification, not an enum or another table. Values
such as `discovery_call`, `intro_email`, `follow_up`, `call_preparation`, and
`pain_confirmation` are examples, not an exhaustive allowed list. There is
no `contact_uid`, `company_uid`, or `deal_uid` on the prompter.

The template is text or Markdown using Jinja expressions, conditions, and
loops. It is not arbitrary Python and does not require a custom `@Contact`
language. For example:

```jinja2
Dear {{ contact.first_name }},

I wanted to learn more about your work at {{ company.name }}
and how your team approaches {{ inputs.topic }}.

Would you be open to a discovery call?

Best,
{{ sender.display_name }}
```

With a Contact named Maria, Company named Example Capital, sender named
Jose, and `inputs.topic` set to “moving research into production”, the
rendered text contains those supplied values. It is a draft to inspect,
edit, and use deliberately; rendering does not send it.

### Context supplied for one use

| Context name | Meaning |
| --- | --- |
| `contact` | The authorized existing Contact being approached. |
| `company` | The Company explicitly relevant to this outreach or opportunity. |
| `lead` | Optional `SolutionSellingLead` when working from a lead. |
| `profile` | Optional selected `SolutionSellingProspectingProfile`; its potential pain remains a hypothesis. |
| `deal` | Optional commercial Deal. |
| `solution_selling` | Optional maintained assessment of that Deal. |
| `sender` | Existing platform user preparing the content. |
| `inputs` | Additional values for this rendering, such as topic or proposed date. |

This context is temporary input to rendering, **not** another stored CRM
model. The caller supplies the relevant Company explicitly; the renderer
must not guess from a Contact's current or historical affiliations.
Optional entries may be represented as `None` and handled by an explicit
Jinja condition. A required reference that is missing should fail with a
clear error rather than render a blank salutation or invented value.

A template can reuse profile knowledge without copying it into the
prompter:

```jinja2
{% if profile %}
Potential issue to investigate: {{ profile.potential_pain }}
{% for reason in profile.likely_reasons %}
- Possible reason: {{ reason }}
{% endfor %}
{% endif %}
```

The word *potential* matters: a profile is prospecting guidance, not a
confirmed buyer statement.

### Rendering boundary

The eventual renderer must supply only authorized, plain data projections
with the documented fields above. It must not expose ORM/database objects,
credentials, arbitrary callables, or functions that send messages or mutate
CRM state. Template evaluation is read-only and produces bounded text;
creating a Task, Note, Interaction, or outbound message is a separate
explicit user action.

For user-authored templates, use Jinja's sandbox and strict undefined-value
handling. The sandbox is **not** a complete security boundary by itself:
the implementation must also limit template/input/output size and CPU or
memory use, catch render errors, and restrict what data and template features
are exposed. This follows the [official Jinja sandbox guidance](https://jinja.palletsprojects.com/en/stable/sandbox/)
and [StrictUndefined documentation](https://jinja.palletsprojects.com/en/stable/api/#jinja2.StrictUndefined).
If HTML output is ever supported, it needs an explicit escaping policy;
this initial decision is for text/Markdown drafts.

The prompter and its output are different things. If generated text is later
retained in a Note or communication, that record keeps the text produced
at that time. Editing the reusable template later does not rewrite past
content. No persistent render-history model is introduced here.

```text
SolutionSellingPrompter (reusable template)
              +
authorized Contact / selected Company / optional Lead, Profile, Deal,
SolutionSelling / sender / per-use inputs
              |
              v
reviewable text or Markdown draft
```

## Consequences and current status

One model covers introductions, discovery guides, follow-ups, and other
template kinds. ProspectingProfile supplies reusable role–pain knowledge;
Prompter expresses or investigates it; Lead connects the work to an actual
Contact. No separate model is needed for each document kind or template use.

**Current status:** Migration `0006` adds the reusable prompter record. The
optional [API](../../api/solution-selling.md) renders a bounded, read-only
text preview for explicit Contact and Company context. It does not send or
save the draft.
