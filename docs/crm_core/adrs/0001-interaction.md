# ADR 0001: Interaction is a people-centered core CRM model

- **Status:** Accepted; amended 2026-09-27 by migration `0009`
- **Original date:** 2026-09-24
- **Scope:** Core CRM domain model, persistence, and mounted API

## Context

An Interaction records one planned, completed, or cancelled call, meeting,
workshop, or email exchange. The original `0006` schema required a Company and
stored one optional primary Contact. That lost the people attending a Calendar
event and prevented conversations that had no Company context. Notes and
activity events do not own a conversation's preparation and outcome.

## Amended decision

An Interaction belongs to **core CRM**. Its central relationship is a
`participants` list of one or more people. Each participant has an optional
`contact_uid`, `email`, `display_name`, and `role` (`organizer` or `attendee`).
At least one of Contact, email, or name identifies each person. A linked
Contact must exist and be active. Email-only and named participants remain
valid; importing an attendee does not silently create a Contact. Duplicate
participant identities are rejected. Manual and Google-created Interactions
use this same model.

`company_uid` is optional organizational context. `deal_uid` is optional;
when present, a Company is required and the Deal must belong to it. No
Company is inferred from a participant or that person's affiliations.
The former `contact_uid` column and single-primary-Contact concept are
superseded. Migration `0009` moves existing primary Contacts into one
participant entry, then removes that column and allows a null Company.
Existing rows without a Contact remain readable with an empty participant
list until edited; every new Interaction requires a person.

The conversation fields remain `subject`, `kind`, `status`, `scheduled_at`,
`occurred_at`, `objective`, `research_notes`, `discussion_plan`,
`outcome_notes`, and `next_steps`. A scheduled past event is not automatically
completed. The record has no Solution Selling foreign key or methodology
specific fields. Solution Selling diagnoses may reference an Interaction.

## Consequences

The CRM list and detail show people first and Company only when present.
The editor supports multiple people and optional Contact links. Google Calendar
review presents organizer and attendees for explicit editing before import;
source links and version checks still fence a reviewed update. The API accepts
`participants` on create and patch and can filter Interactions by a linked
participant `contact_uid`. See [Interactions](../../concepts/interactions.md)
and the [Interactions API](../../api/interactions.md).

The migration and governed write paths require provider-scoped verification
and a fresh-process catalog binding before the new behavior can be called
deployed. See [verification](../../delivery/verification.md).
