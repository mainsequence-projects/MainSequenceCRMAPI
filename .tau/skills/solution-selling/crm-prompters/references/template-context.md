# Supported prompter context

Use this reference when inspecting requirements, authoring a template or
diagnosing a render failure. The tool's current schema and returned validation
remain authoritative. The renderer exposes these bounded projections:

| Root | Fields |
| --- | --- |
| `contact` | `uid`, `first_name`, `last_name`, `title` |
| `company` | `uid`, `name`, `website`, `description` |
| `lead` | `uid`, `status`, `notes` |
| `profile` | `uid`, `name`, `role`, `market_context`, `potential_pain`, `likely_reasons`, `likely_impacts`, `research_guidance`, `opening_message` |
| `deal` | `uid`, `name`, `description`, `amount`, `currency` |
| `solution_selling` | `uid`, `pain_summary`, `power_summary`, `vision_summary`, `value_summary`, `control_summary`, `evaluation_plan` |
| `sender` | `uid`, `display_name` supplied by the service |
| `inputs` | Caller-supplied string keys and string values |

Full record fields are not automatically template fields: Contact emails, for
example, are absent here. The first two references are mandatory in the render
payload; the other business references are optional until the template needs
them. Missing/undefined context fails rendering.

Restricted Jinja supports substitutions, conditionals, `not`, literal string
keys and one-level loops over `profile.likely_reasons` or
`profile.likely_impacts`. Calls, filters, tests, globals, private attributes and
arbitrary loops are unsupported. Do not use `default`, `join` or other ordinary
Jinja filters to conceal missing data.

For example, this template needs Contact and Company references and
`inputs.topic`; profile is optional and sender is automatic:

```jinja
Hello {{ contact.first_name }},

I would like to discuss {{ inputs.topic }} at {{ company.name }}.
{% if profile %}
One question worth exploring is whether {{ profile.potential_pain }} is relevant.
{% endif %}

Best,
{{ sender.display_name }}
```

Inspect both `template` (body) and optional `subject_template`; they use the same
context and restricted syntax. Each source is bounded at 16,384 characters and
each rendered part at 32,768. Technical-limit failures are validation errors.
Optional `constraints.max_characters` and `constraints.max_subject_characters`
are independent business limits on final text, counted as Unicode code points.
Exceeding these returns the full preview with `is_valid: false` and per-field
violations; no text is truncated or saved. An absent subject stays null.
