# Tags and activity

Tags are reusable labels for contacts. A tag has a name and a semantic `tone`
(`neutral`, `info`, `success`, `warning`, or `danger`). A source color may be
preserved as legacy metadata, but callers should use `tone` for presentation.
Contact tag membership is edited through the contact's `tag_uids` replacement.

Activity events record entity changes and their origin. They are read-only on
the mounted HTTP surface: callers can list, discover, and read events but
cannot create or patch one directly. An activity event is not a task or note.

See the [tag and activity API](../api/engagement.md) for paths.
