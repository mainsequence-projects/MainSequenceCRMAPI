# Tasks and notes

Tasks and notes describe work around tracked records, but they have different
rules.

## Tasks

A task belongs to a contact, has nonblank text, an optional owner and due time,
and an optional task type key. Completion and reopening are explicit commands;
they update `completed_at` and `completed_by_uid` rather than accepting those
server fields in a generic patch. Both commands require the expected version.

## Notes

A note belongs to **exactly one** contact or deal. It has nonblank text and an
offset-aware `occurred_at` timestamp, which is distinct from the server's
creation and update timestamps. Live note authorship comes from the caller;
the create payload does not accept an arbitrary `author_uid`. Historic source
author labels may be preserved by import logic without impersonating a user.
Changing a note's parent is not a general patch operation.

See the [engagement API](../api/engagement.md) for the task and note endpoints.
