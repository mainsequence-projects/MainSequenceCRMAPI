# Set up Google access for the CRM

**Status: callback and public ingress are declared in source; deployment and
a real Google consent flow remain unverified.**
The extension is enabled in this repository's `config/crm.yaml`. Complete the
Google-side steps, apply CRM migration `0008`, and configure the API runtime
before using the
[mounted routes](../api/google-workspace.md).

## What you create

Create a **Google Cloud project** and a **Web application OAuth client** in
Google Auth Platform. This is the “app” whose consent screen a user sees when
connecting their Google account. This design does **not** require a Google
Workspace Marketplace listing or a Workspace add-on. A Workspace administrator
may also need to allow that OAuth client under organization API controls.
Google documents the [project](https://developers.google.com/workspace/guides/create-project),
[consent screen](https://developers.google.com/workspace/guides/configure-oauth-consent),
and [OAuth client](https://developers.google.com/workspace/guides/create-credentials)
as separate setup steps.

You need permission to create/select a Google Cloud project and OAuth client,
an externally reachable HTTPS **CRM API callback**, and a support email. For a
personal `@gmail.com` account or users outside one Workspace
organization, choose **External** audience. **Internal** works only for users
in the Google Cloud project's Workspace organization. The Google account that
will authorize the connection is chosen later by each CRM user; it is not
entered as an application credential. See Google's [app audience guidance](https://support.google.com/cloud/answer/15549945).

## Configure public callback routes on Main Sequence

The CRM defines `GET /extensions/google/oauth/callback/` and
`GET /extensions/google/oauth/done/` without a CRM bearer dependency. The
CRM API workflow `.mainsequence/workflows/crm-api.yaml` declares those
two exact public ingress pairs. The persisted `config/crm.yaml` enables the
extension. The platform does not infer public
paths from FastAPI decorators or CORS settings. Read the installed
`.agents/skills/mainsequence/pod_manager/code_repository_workflows/SKILL.md`
and `resource_release/SKILL.md` for the current platform contract.

1. Resolve the exact CodeRepositoryBranch and fetch its backend
   `workflow-template/`. Use the returned API version (currently `2.3.0`).
   Maintain the existing `crm-api` declaration for `api/crm/main.py`:

   ```yaml
   public_ingress:
     - method: GET
       path: /extensions/google/oauth/callback/
     - method: GET
       path: /extensions/google/oauth/done/
   ```

   Declare literal paths only, without query strings or full URLs. Keep every
   other CRM path out of this list. If the branch already has an externally
   managed CRM API release, reconcile that exact release before activating the
   workflow so there is only one CRM API target.
2. Validate the complete workflow file with the branch's
   `validate-workflow/` endpoint. The current API 2.3.0 declaration passed
   that branch validator with no errors or warnings. Commit and push the validated declaration
   and callback handler. Follow the repository event and DeploymentRun until
   the new revision is ready and active. A local YAML edit or successful
   validation does not expose the route.
3. Read `resource_release.get` for the exact CRM API release. Confirm both
   method/path pairs appear in `public_ingress` **and**
   `effective_public_ingress`. Use its backend-issued `public_url`; append the
   callback path to that URL without constructing a hostname. If the URL has
   an unexpected path prefix, reconcile the application's configured callback
   path before registering it in Google.
4. From outside the platform, request the completion page without an
   Authorization header and confirm `200`. Send a callback request with an
   invalid state and confirm it reaches application validation rather than
   gateway authentication. Confirm an unlisted path such as
   `/extensions/google/connections/` and the wrong method on a listed path
   remain denied without a bearer token. Public admission supplies no Main
   Sequence user identity; the callback relies on one-time OAuth state and
   PKCE, while authenticated CRM routes still use platform identity.

Only after these checks should you register the exact callback URI in Google
and set `GOOGLE_OAUTH_REDIRECT_URI` to the same value. Localhost testing
through `api/crm/local.py` is separate from deployed gateway admission.

## Google Cloud Console steps

1. **Create or select a project.** In the [Google Cloud Console](https://console.cloud.google.com/),
   open **Menu → IAM & Admin → Create a Project**. Give it a durable name such
   as `Main Sequence CRM Google integration`. If this is Internal, put it under
   the intended Workspace organization. Select the resulting project before
   continuing. [Google project instructions](https://developers.google.com/workspace/guides/create-project).

2. **Enable the APIs.** Open **Menu → APIs & Services → Library**. Search for
   and enable **People API**, **Gmail API**, and **Google Calendar API** in that
   project. Their service IDs are `people.googleapis.com`,
   `gmail.googleapis.com`, and `calendar-json.googleapis.com`. The People API
   reads saved Google Contacts; Gmail reads selected correspondent headers;
   Calendar reads meeting events. [Google API enablement guide](https://developers.google.com/workspace/guides/enable-apis).

3. **Configure the consent screen.** Open **Menu → Google Auth Platform →
   Branding** and click **Get Started** if prompted. Enter the app name (for
   example `Main Sequence CRM`), user support email, and developer contact
   email. Under **Audience**, choose **Internal** only for your own Workspace
   organization; otherwise choose **External**. For an External app in
   **Testing**, open **Audience → Test users → Add users** and add the Google
   accounts that will test the connection. Set the branding and privacy-policy
   fields required for the audience and eventual publication. [Google consent
   setup](https://developers.google.com/workspace/guides/configure-oauth-consent).

4. **Declare data access.** For an External app, open **Google Auth Platform →
   Data Access → Add or Remove Scopes** and add the scopes for the features you
   intend to enable. The CRM asks for them incrementally when the user opens a
   feature; configuring them in Google does not grant them to the CRM.

   | Feature | Scope |
   | --- | --- |
   | Identify the connected Google account | `openid` and `email` |
   | Import saved Google Contacts | `https://www.googleapis.com/auth/contacts.readonly` |
   | Suggest Contacts from Gmail headers | `https://www.googleapis.com/auth/gmail.readonly` |
   | Import Calendar meetings | `https://www.googleapis.com/auth/calendar.events.readonly` |
   | Let users choose among their calendars | `https://www.googleapis.com/auth/calendar.calendarlist.readonly` |

   Internal apps might not show scopes on the consent screen, but the backend
   still requests and checks them. Gmail read-only is a **restricted** scope.
   Google's [Gmail scope list](https://developers.google.com/workspace/gmail/api/auth/scopes)
   and [consent guide](https://developers.google.com/workspace/guides/configure-oauth-consent)
   describe the distinction. Save the Data Access configuration before
   creating the client.

5. **Create the OAuth client.** Open **Google Auth Platform → Clients → Create
   Client**, select **Application type: Web application**, and give it a name
   such as `Main Sequence CRM API production`. Under **Authorized redirect
   URIs**, add the full callback URI derived from the release's verified
   `public_url` in the preceding section. For a root URL it looks like:

   ```text
   https://YOUR_CRM_API_HOST/extensions/google/oauth/callback/
   ```

   Use the actual backend-issued URL and preserve any path prefix; do not
   derive the hostname from a release UID. It is the **API URL**, not the
   Command Center frontend URL. Match the scheme,
   hostname, path, and trailing slash exactly; otherwise Google returns
   `redirect_uri_mismatch`. The backend performs the token exchange, so this
   design does not use an Authorized JavaScript origin. Create a separate
   localhost Web client for development if needed, with its own exact
   `http://localhost:<port>/extensions/google/oauth/callback/` URI. Click
   **Create** and save the client ID and client secret shown at creation in
   protected operator storage. Google may show the full secret only once.
   [Web OAuth client instructions](https://developers.google.com/workspace/guides/create-credentials),
   [client-secret handling](https://support.google.com/cloud/answer/15549257),
   and [redirect matching](https://developers.google.com/identity/protocols/oauth2/web-server).

6. **Check Workspace Admin controls if a Workspace user is blocked.** A
   Workspace administrator can open **Google Admin console → Security → Access
   and data control → API controls → Manage App Access**, find or add the OAuth
   client ID, and grant the organization's approved level of Google data
   access. This is conditional on the organization's policy; do not broadly
   trust the client without reviewing the requested scopes. An External app
   can still be blocked by Workspace policy even after Google verification.
   [Google Workspace Admin guidance](https://support.google.com/a/answer/7281227).

7. **Prepare an External app for production when the CRM module is ready.**
   An External app can remain in **Testing** while named test users try the
   integration, but its grants for these scopes normally expire after seven
   days. Before broad use, complete the applicable branding and scope review
   in Google Auth Platform, then use **Audience → Publish app** to move to
   **In production**. Gmail read-only is restricted; if the backend handles
   restricted Gmail data, Google's review can include a security assessment.
   An Internal app used only by its own Workspace organization has a different
   verification path, though organization API controls still apply. Review
   [Google's app states](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview)
   and [restricted-scope process](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification)
   before enabling Gmail for production users.

## Configure the CRM deployment

Before a user can select **Connect**, create all three named Main Sequence
Secrets in the Environment used by the CRM API runtime and grant that runtime
access. The first two values come from the Google Cloud Web OAuth client. The
third is a CRM-generated encryption key; Google does not issue it. The API
loads all three when starting an OAuth attempt. Missing or placeholder values
leave the integration unconfigured even when the extension appears in CRM.
Do not share these Secrets with the frontend. Only the exact callback URI is
an API runtime environment value.

| Runtime value | Where it belongs |
| --- | --- |
| `extensions.google_workspace.active: true` | Persisted `config/crm.yaml` value; route mounting and bootstrap use the same snapshot. |
| `CRM_GOOGLE_OAUTH_CLIENT_ID` | Main Sequence Secret: identifies the Web OAuth client created in Google Cloud in Step 5. |
| `GOOGLE_OAUTH_REDIRECT_URI` | Nonsecret API runtime configuration; exactly the URI registered in Step 5. |
| `CRM_GOOGLE_OAUTH_CLIENT_SECRET` | Main Sequence Secret: authenticates that Web OAuth client when the API exchanges Google's authorization code for tokens. |
| `CRM_GOOGLE_TOKEN_ENCRYPTION_KEY` | Separate Main Sequence Secret: 32 random bytes encoded as URL-safe base64, used by CRM to encrypt stored per-user Google grants. Generate and store it once; do not replace it while active grants exist or those grants become unreadable. |

Main Sequence Secret values cannot be patched after creation. If the local
client ID and client secret records were created with setup placeholders, run
`.venv/bin/python scripts/configure_google_oauth_secrets.py` from the API
repository root. Its masked terminal prompts accept the two real Google values,
replace only the placeholder records, and leave the encryption key untouched.
The placeholder strings are not usable Google credentials.
Do not paste credentials into chat or commit them to Git.

Apply provider-scoped migration `0008` **before** starting the API with this
code. The new private MetaTables hold one-time OAuth attempts and encrypted
per-user refresh tokens. The persisted extension activation controls route and frontend
availability; as with Solution Selling, the migration-owned tables still
need to exist in the catalog. The CRM frontend reads the module value from
bootstrap and shows the Google Workspace navigation entry only to users with
`crm.transfer.import`. The activation value is not a Google credential or a CRM permission.

The CRM will create and protect its own per-user Google connection records.
Do not put the client ID, client secret, downloaded OAuth JSON, refresh tokens, or the
token-encryption key in Git, `.env` committed to Git, a Constant, the frontend,
or this documentation. See the [Main Sequence Secret guidance](https://mainsequence-sdk.github.io/mainsequence-sdk/knowledge/infrastructure/constants_and_secrets/).

## Connect and verify

1. Sign in to CRM through Main Sequence and open the Google Workspace module.
2. Choose a source and **Connect**. The CRM opens Google authorization in a
   separate browser tab; use the fallback link if the browser blocks that tab.
   Choose the Google account to connect.
3. Grant the requested source scope. Google's callback opens a token-free
   completion page. Return to the original CRM window; it polls the one-time
   attempt through the authenticated API and finalizes the grant for the
   same CRM user. Confirm that it shows
   the connected account email and granted sources without exposing tokens.
4. Preview one saved Google Contact, one Gmail correspondent in a selected
   query and date range if Gmail access is enabled, and one Calendar meeting.
   Commit only the chosen items
   and confirm their CRM records and source links.
5. Disconnect and confirm that future Google reads require reconnection. The
   CRM records already imported remain governed by CRM retention and access.

Migration `0008` and a synthetic governed import probe passed on the
configured local provider. Real Google consent and a deployed frontend/API
check have not been reported for this implementation yet. The
[verification guide](../delivery/verification.md) distinguishes source tests
from live integration evidence.
The [ADR's verification section](adrs/0001-google-workspace-intake.md#delivery-and-verification)
defines the implementation tests and live release gates.

## Common setup failures and release limits

| Symptom | Check |
| --- | --- |
| `redirect_uri_mismatch` | Compare the deployed API callback URI with the Web client's Authorized redirect URI character for character. |
| `org_internal` or account cannot consent | Internal audience excludes accounts outside that Workspace organization; choose External if those accounts must connect. |
| External test user denied | Add the exact Google account under **Audience → Test users** while the app is in Testing. |
| Workspace admin blocks access | Ask the admin to review the OAuth client ID under **API controls → Manage App Access**. |
| `invalid_grant` after a prior connection | The grant or refresh token may have expired or been revoked; reconnect the account. |
| Local **Connect** stays at “Preparing Google authorization” | Check the protected CRM bootstrap and Main Sequence `/api/v1/users/me/` first. OAuth start reads three platform Secrets and uses governed table operations; a slow Main Sequence backend delays the Google URL. The CRM waits for the API response before opening Google's consent page. |

External apps in **Testing** issue refresh tokens that normally expire after
seven days for these nonidentity scopes. Internal apps do not need Google's
additional OAuth scope verification for use solely within their organization.
For External production access, Gmail's restricted scope may require Google's
verification and a security assessment when restricted data is handled on the
server. Google's [OAuth app states](https://developers.google.com/identity/protocols/oauth2/production-readiness/overview),
[token expiration guidance](https://developers.google.com/identity/protocols/oauth2),
and [Gmail data policy](https://developers.google.com/workspace/workspace-api-user-data-developer-policy)
are the release references. The policy names CRM email-productivity features
as an approved use case but disallows one-time/manual **email export**; the
Gmail correspondent design must be reviewed against that distinction before
requesting production Gmail scope approval. Saved Google Contacts and Calendar
can be built and verified separately.
