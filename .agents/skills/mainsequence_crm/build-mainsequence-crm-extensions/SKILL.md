---
name: build-mainsequence-crm-extensions
description: Implement or change optional CRM extension APIs and provider callbacks. Use when adding an extension route, feature switch, frontend API call, or public ingress policy.
---

# CRM extension API routes

Read `AGENTS.md`, the relevant module's documentation under `docs/`, and the project CRM API skill before editing routes. Use the installed Main Sequence FastAPI and CodeRepository workflow skills for release policy; do not edit SDK-managed skills as application guidance.

## Route boundary

- Put **every optional extension API endpoint** under the literal root `/extensions/<extension-slug>/`. Define a router with that prefix and mount it only when its exact backend feature switch is enabled. Do not place extension API endpoints under `/api/crm/v1/`, which is for core CRM endpoints.
- Existing slugs are `google` and `solution-selling`. The shared core Interaction routes stay under `/api/crm/v1/interactions/`. Frontend page URLs are navigation URLs and do not need to match API routes.
- Route extension calls through the same Command Center delegated FastAPI transport as core CRM calls. Allow `/extensions/` in the frontend API path guard and local Vite proxy. Never put Google OAuth credentials in the frontend.
- Keep ordinary extension API routes protected by platform Bearer authentication and application policy. An externally invoked callback cannot use the caller's injected CRM identity; verify provider state, PKCE, signature, or equivalent proof in the handler.

## Public provider ingress

- Add only the exact method and literal path of an external callback or completion page to the FastAPI resource's `spec.public_ingress` in `.mainsequence/workflows/*.yaml`. For Google these are `GET /extensions/google/oauth/callback/` and `GET /extensions/google/oauth/done/`. Do not make OAuth start, attempt status, completion exchange, connection, preview, or import routes public.
- Fetch the exact branch workflow template and validate the complete declaration with `validate-workflow/`. A valid local YAML file does not activate ingress. After deployment, check both desired and `effective_public_ingress` on the active release, derive the redirect URI from its backend-issued `public_url`, and test public admission and protected-path denial without a Bearer token.
- Google requires `INCLUDE_GOOGLE_WORKSPACE_EXTENSION=true` in the API runtime. Its registered redirect URI must match `/extensions/google/oauth/callback/` exactly, including the trailing slash.

## Completion checks

Update the module ADR/setup page, MkDocs API and delivery pages, and frontend instructions for any changed route or release policy. Test flag-off and flag-on OpenAPI inventories, public callback handling without CRM identity, authenticated route denial without identity, and the frontend build. Run `mkdocs build --strict` and report local validation separately from active release or Google consent verification.
