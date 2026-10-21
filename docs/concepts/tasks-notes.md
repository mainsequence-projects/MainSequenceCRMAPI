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

Notes hold free-form relationship context without requiring an interaction,
task or category. An optional plain-text `title` gives the note a short heading.
Titles are trimmed, must be a single nonblank line when supplied, and are limited
to 255 characters. Existing notes keep a null title and display “Untitled note”. The `text` body stores Markdown source (plain text also
works), up to 100,000 characters. Status and attachments are optional. The
contact Notes tab provides Add note and Edit note with Title, Date and Body;
creation preselects the contact and defaults the date/time to now. The editor
shares the Agent Prompts rich Markdown editor and safe reader. Unsupported
formatted content stays in source mode. HTML/code is not executed and remote
images are not loaded automatically.

Edits use the current version fence, preserve the original date on body-only
edits, and retain drafts on conflicts or uncertain saves. Users must read
server state before retrying an uncertain write. The assistant can use
`crm_notes_create` with `contact_uid`, optional `title`, `text`, and offset-aware `occurred_at`;
the date remains an explicit required tool/API argument. `crm_notes_update` can
change the title with the same version fence: omit it to preserve it or send
`null` to clear it. The Notes list shows the title, body preview and date, and
search matches both title and body.

See the [engagement API](../api/engagement.md) for the task and note endpoints.
