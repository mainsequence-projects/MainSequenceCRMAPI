# Google Workspace module

**Status: implemented in source, deployment unverified.** The Google routes
mount only when `extensions.google_workspace.active: true` in
`config/crm.yaml`. Migrations `0008` and `0009`,
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
| Google Calendar events | Review organizers and attendees, then create core [Interactions](../concepts/interactions.md) with optional Company context; update linked Interactions after review. |

The CRM continues to use Main Sequence's injected identity and policy. Google
OAuth grants access to the consenting user's Google data; it is not a second
CRM login. The backend receives Google credentials and calls Google APIs. The
Command Center frontend has separate **Google Contacts**, **Gmail
correspondents**, and **Calendar events** destinations for connection,
preview, and review. It can show connection state before Google operator
credentials have been configured; starting consent then reports the missing
configuration.
One **Connect Google Workspace** action requests read permissions for all
three destinations together. The connection summary shows which permissions
Google granted; a declined source remains unavailable until the user chooses
**Complete Google permissions**. No Google data is imported at consent time.
Opening the module reads the current connection once per CRM session so the
page can show the connected account. An unfinished OAuth attempt is checked
when the user returns to the tab or presses **Check connection**; the page
does not repeatedly poll the CRM store in the background. Google source data
is read only after **Preview selected source** is pressed; Calendar lists are
loaded by a separate button. Preview checks existing CRM links and matches in
bounded batches and does not create records. Clicking a Contact candidate
opens a create modal prefilled with the Google details. Saving the reviewed
form creates the CRM Contact and its Google source link together.
Calendar previews request ascending start-time order from Google, so the
nearest event appears first across pages. An event's review opens the shared
CRM dialog. Each participant can remain email-only or link to a Contact through
the standard searchable picker, which can create a missing Contact. Company is
optional context and has the same quick-create option. The Interaction is
imported only when its review is saved.

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
