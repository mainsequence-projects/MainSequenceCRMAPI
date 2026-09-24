# Domain map

The CRM tracks people, organizations, opportunities, follow-up work, and their
history in the CRM application. Platform identity and policy govern access;
the application does not define a workspace or tenant record.

| Concept | Relationship | Details |
| --- | --- | --- |
| [Contact](contacts.md) | May have multiple dated company affiliations; may have tags, tasks, notes, and deals | A person with names and/or email methods |
| [Company](companies.md) | May have contacts and deals | An organization record, not an account or login |
| [Deal](deals-pipelines.md) | Belongs to a pipeline and stage; may link a company and contacts | A currency-specific opportunity |
| [Task](tasks-notes.md) | Belongs to a contact | Follow-up work with explicit completion state |
| [Note](tasks-notes.md) | Belongs to exactly one contact or deal | Time-stamped narrative with server-owned authorship |
| [Tag](tags-activity.md) | May label contacts | Reusable classification with a semantic tone |
| [Activity event](tags-activity.md) | Refers to an entity and command | Read-only audit history |
| [Transfer](transfers.md) | Belongs to an initiating principal | Durable import/export job state |

Records have stable UUIDs and relationships to other CRM records. Versions protect edits from
overwriting newer data. Archive is a marker, not a general permanent delete.
The [API conventions](../api/conventions.md) explain how those rules appear on
the wire.
