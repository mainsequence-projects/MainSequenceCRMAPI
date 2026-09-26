# Google Workspace module

**Status: implemented in source, deployment unverified.** The Google routes
mount only when `extensions.google_workspace.active: true` in
`config/crm.yaml`. Migration `0008`,
Google Cloud setup, and CRM Secrets/configuration are required before a user
can connect an account. Creating credentials in Google Cloud alone is not
sufficient. The deployed FastAPI release must also activate exact public
ingress for the OAuth callback and completion page.

This module provides a user-authorized Google connection for three reviewed
imports:

| Google source | CRM result |
| --- | --- |
| Saved Google Contacts through the People API | Create or match [Contacts](../concepts/contacts.md) after review. |
| Gmail message correspondents | Suggest Contacts from selected message headers; never create them automatically. |
| Google Calendar meetings | Create core [Interactions](../concepts/interactions.md) after the user selects a Company; update meetings already linked to the same event after review. |

The CRM continues to use Main Sequence's injected identity and policy. Google
OAuth grants access to the consenting user's Google data; it is not a second
CRM login. The backend receives Google credentials and calls Google APIs. The
Command Center frontend has separate **Google Contacts**, **Gmail
correspondents**, and **Calendar meetings** destinations for connection,
preview, and review. It can show connection state before Google operator
credentials have been configured; starting consent then reports the missing
configuration.

## Module documents

- [ADR 0001: User-authorized Google Workspace intake](adrs/0001-google-workspace-intake.md)
  specifies the OAuth flow, token custody, matching, and import boundaries.
- [Set up Google access](setup.md) gives the Google Cloud Console steps, the
  exact public ingress and callback setup, scopes, Workspace Admin checks,
  and CRM configuration handoff.

The module is separate from the existing file [transfer](../concepts/transfers.md)
adapters. It does not add Google authentication to CRM. See the
[flag-gated API](../api/google-workspace.md) for the implemented paths and
the [verification page](../delivery/verification.md) for outstanding live checks.
