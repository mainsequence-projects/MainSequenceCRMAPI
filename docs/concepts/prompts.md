# Agent Prompts

A Prompt, labeled **Agent Prompt** in the frontend, is a reusable, named document of **fixed Markdown** instructions. It
belongs to the core CRM and is available even when optional modules are off.
The frontend renders it for reading and offers a formatted inline editor and
source mode. Markdown is the canonical stored content; saving or copying a
Prompt does not invoke a model, send a message, or evaluate variables.

`{{ contact.first_name }}`, code blocks, and other braces are ordinary text.
This library is separate from the optional Solution Selling **Prompters**, which
have a Jinja template and a personalized-draft rendering workflow. Neither
feature replaces the other.

Each Prompt has a UUID, name, optional description, Markdown body, version,
creation/update audit fields, and an archive marker. Names need not be unique.
The body must be non-blank, contain no NUL characters, and fit within 64 KiB in
UTF-8. There are no attachments, contact references, prompt variables, version
history, or per-document sharing settings in this initial feature.

CRM capabilities govern read, create, edit, and archive/restore. Version fences
reject stale saves without overwriting a newer document. The UI retains a
conflicting draft and requires a fresh read and explicit comparison before
another save. An uncertain write is not automatically replayed. Archive keeps
the document and allows restoration; it is not permanent deletion.

Lists contain metadata only and search names/descriptions, not full bodies.
Markdown is fetched for an individual document. The reader never executes raw
HTML/MDX, loads remote images, or follows unsafe URL schemes. The formatted
editor handles standard Markdown; unsupported constructs remain editable in
source mode. Editing formatted content may normalize Markdown syntax; merely
switching modes or saving unchanged content does not rewrite the source.

The assistant can find saved Agent Prompts with `crm_prompts_list` and read a
selected document with `crm_prompts_get`. Reads require `crm.read`, include
the exact saved Markdown in the detail result, and do not execute or send it.
These fixed instruction documents are separate from Solution Selling Prompters.

See the [Prompt API](../api/prompts.md) for payloads and permissions.
