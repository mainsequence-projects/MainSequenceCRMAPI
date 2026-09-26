---
name: code-repository-workflows
description: Create and validate backend-managed API 2.3.0 deployment declarations under .mainsequence/workflows for Jobs, FastAPI applications, Static Sites, and the one branch-owned Harness Agent.
---

# Main Sequence CodeRepository Workflows

Repository workflow files are repository-authored deployment intent. Django owns
parsing, validation, permissions, exact-commit resolution, image orchestration,
deployment, and reconciliation. Clients must not implement another parser or
construct a second interpreted deployment payload.

## Deployment Ownership

Django Pod Manager is the deployer. Repository authors declare source paths,
runtime configuration, compute intent, and promotion policy. Django resolves
the exact-commit indexed source, selects or builds the code repository image, creates
or reuses the durable target, creates DeploymentRuns and revisions, and calls
the product deployment adapter. Agents owns the Harness Agent's semantic Agent
record and its provider/model/thinking defaults; Pod Manager owns its bound
ResourceRelease and deployment lifecycle.

Workflow YAML never supplies a Job, source-resource, image, branch, cluster,
Agent, ResourceRelease, revision, or DeploymentRun UID. Those identifiers are
backend-generated results used only after reconciliation.

## Procedure

1. Identify the exact `CodeRepositoryBranch` public UID.
2. GET `/api/v1/code-repository-branches/{uid}/workflow-template/`.
3. Edit the returned YAML using its advertised `api_version`.
4. POST `path` and `content` to
   `/api/v1/code-repository-branches/{uid}/validate-workflow/`.
5. Fix every validation error before committing.
6. Save the file as a direct `.yaml` or `.yml` child of
   `.mainsequence/workflows/` and commit it.
7. Inspect the repository-event action and resulting DeploymentRuns. A Git
   commit alone does not prove that deployment succeeded.

Repository processing is branch-specific. The event repository, exact branch
ref, persisted CodeRepositoryBranch, and full pushed commit must agree. Image
builds consume one backend-materialized, checksummed archive for that commit;
providers do not select branch HEAD. Automatically managed targets receive only
the verified digest-pinned code repository image selected by the backend.

## File Contract

- Every file requires `api_version`, `name`, and `resources`.
- `2.3.0` is current. It accepts `job`, `fastapi`, `static_site`, and
  `harness_agent`.
- Older supported versions accept only their backend-advertised kinds. They do
  not accept `harness_agent`.
- Every resource requires a stable `key`, supported `kind`, and typed `spec`.
- Only direct `.yaml` and `.yml` children are processed.
- Validation is read-only and uses the same validator as event application.
- Unknown fields are errors. Do not use `scheduled_jobs.yaml`.

Target-owned non-secret `env_vars` use this shape:

```yaml
env_vars:
  - name: FEATURE_MODE
    value: conservative
```

Omission preserves existing values, an empty list clears them, and a present
list replaces them. Static sites use `build_environment` instead. Reserved
platform credential, runtime, deployment-control, and transport variables are
rejected.

## Harness Agent

Use exactly one `harness_agent` declaration when the branch's project should
run a repository-backed coding harness.

`harness_agent` is the single concept throughout the deployment contract:

- public workflow kind: `harness_agent`;
- persisted ResourceRelease kind: `harness_agent`;
- DeploymentRun target kind: `harness_agent`;
- runtime label and observability kind: `harness_agent`.

The user does not declare FastAPI. Django uses the Harness Agent product
adapter and existing `coding-agents` namespace; only the product-neutral
Knative builder is shared with FastAPI. The user also does not supply an Agent
identity. Django creates the `Agent`, derives its Organization Environment from
the branch, creates the `harness_agent` release, binds both, and returns
`agent_uid` and `resource_release_uid` as results.

Agent creation requires the indexed `.agents/agent_card.json` at the exact
repository-event commit. Its non-empty top-level `name` and `description`
become the live Agent presentation fields. Missing or malformed cards reject
reconciliation before an Agent exists; repository and branch metadata are not
presentation fallbacks.

Example:

```yaml
api_version: "2.3.0"
name: repository-runtime
resources:
  - key: repository-harness-agent
    kind: harness_agent
    spec:
      source_path: api/agent/main.py
      llm_provider: openai
      llm_model: gpt-5.4
      llm_thinking: medium
      automatic_deployment: true
      automatic_redeployment:
        enabled: true
        tag_regex: null
      revision_retention_count: 3
      cpu_request: "1"
      memory_request: 2Gi
      spot: false
      env_vars:
        - name: FEATURE_MODE
          value: conservative
```

Supported `harness_agent.spec` fields are:

- `source_path`;
- `llm_provider`, `llm_model`, and `llm_thinking`;
- `automatic_deployment`;
- `automatic_redeployment`;
- `revision_retention_count`;
- `cpu_request`, `memory_request`, `gpu_request`, `gpu_type`, and `spot`; and
- `env_vars`.

Never put any of the following in that spec:

- `uid`;
- `resource_uid`;
- `related_image_uid`;
- `agent_uid`;
- `resource_release_uid`;
- `deployment_uid`;
- `cluster_uid`;
- `release_kind`;
- `harness`;
- `agent_type`;
- a branch UID;
- a special SDK or agent-runtime image.

Provider, model, and thinking are required Agent runtime defaults rather than
identity. Validate the combination through Django. Use `llm_thinking: off`
when the selected model has no configurable reasoning level.

A CodeRepositoryBranch owns at most one Harness Agent across all workflow
files. Two declarations are invalid even when their keys, resources, or files
differ. The backend enforces this during per-file validation, cross-file event
validation, branch locking, and the database one-to-one relationship.

Automatic deployment builds/selects the ordinary code repository image for the exact
event commit, creates an immutable ResourceReleaseRevision, and deploys it
through the standard DeploymentRun and Knative lifecycle. It never bootstraps
or overlays a separate coding-agent image.

## Jobs

A Job spec declares its name, description, execution path, schedule, command
arguments, compute, timeout, and automatic-redeployment intent. It never
identifies or adopts an existing Job by UID. Django creates or reuses the Job
through the durable branch, workflow-path, and resource-key declaration
binding, then resolves the exact code repository image after policy eligibility.

`scheduled_command_args` is an argument vector, not a shell string:

```yaml
scheduled_command_args:
  - python
  - -m
  - project.jobs.refresh
```

`task_schedule` uses the backend-advertised crontab fields and an IANA timezone.
Validate it through Django rather than reproducing cron rules locally.

## FastAPI And Static Sites

Use the explicit `fastapi` and `static_site` product kinds. Do not use a
generic `resource_release` wrapper or put `release_kind` in the spec.

Complete FastAPI workflow example for an OAuth callback and webhook:

```yaml
api_version: "2.3.0"
name: provider-api
resources:
  - key: provider-api
    kind: fastapi
    spec:
      source_path: api/provider/main.py
      automatic_deployment: true
      automatic_redeployment:
        enabled: true
        tag_regex: null
      revision_retention_count: 3
      public_ingress:
        - method: GET
          path: /integrations/provider/oauth/callback/
        - method: POST
          path: /integrations/provider/webhook/
```

A single FastAPI application factory may expose both HTTP and WebSocket routes.
Do not create a second release or add a `websocket_enabled` field. Platform
transport, gateway, ticket, and timeout policy remains backend-owned.

### Automatic public callback deployment

The repository author or coding agent sets `spec.public_ingress` in the YAML;
the platform never infers public routes from FastAPI decorators or OpenAPI.
Do not set `FASTAPI_PUBLIC_INGRESS` in `env_vars`. Declare the release in this
workflow; Django derives the runtime setting from the immutable revision when
it deploys the app.

1. Implement the handler at the literal method/path declared above in the
   FastAPI app loaded by `source_path`. A `GET` OAuth callback may receive a
   query string; declare only `/integrations/provider/oauth/callback/`, never
   a query or URL. The app verifies OAuth state and exchanges the code, or
   verifies a webhook signature and replay identifier. Keep secrets out of
   YAML and logs.
2. GET the exact branch's workflow template from the route in **Procedure**.
   Use its advertised `api_version`, edit a direct
   `.mainsequence/workflows/*.yaml` file, and put each public pair under the
   `kind: fastapi` resource's `spec.public_ingress`. `[]` means no public
   routes. `automatic_deployment: true` enables deployment; the nested
   `automatic_redeployment` policy governs later repository events. With
   `enabled: true` and `tag_regex: null`, every synchronized commit is
   eligible; omitting the nested policy uses the branch's default SemVer rule.
3. POST that exact file's `path` and full YAML `content` to the branch
   `validate-workflow` route in **Procedure**. Continue only when `valid` is
   true. The route validates but does not deploy.
4. Commit both the handler and workflow file, then push the intended tracked
   branch. The repository event applies the declaration, resolves its indexed
   source and exact-commit image, creates or updates the release, and records
   a DeploymentRun. A local file edit or validation response does not deploy.
5. Follow the workflow event result and its DeploymentRun until the candidate
   revision is ready and active. Call MCP `resource_release.get` using the
   backend-returned release UID. Confirm the exact pair appears in both
   `public_ingress` and `effective_public_ingress`, and use the returned
   `public_url`; do not construct a hostname or register the provider URL
   before activation. A failed candidate leaves a new pair private.
6. Append the literal path to `public_url`, register that full URI with the
   provider, and verify a provider-style request reaches the handler without
   a Main Sequence Bearer token. Verify an unlisted path and wrong method are
   denied. Admission supplies no User identity or provider authentication.

On removal, commit and push the updated workflow. Once reconciliation writes
the desired policy without that pair, admission stops immediately, even if
an older revision remains active. Recheck `effective_public_ingress` before
using a registered provider URI.

Static Site example:

```yaml
- key: command-center
  kind: static_site
  spec:
    name: Command Center
    root_directory: web
    framework: vite
    output_directory: dist
    routing_mode: spa
    automatic_deployment: true
    automatic_redeployment:
      enabled: true
      tag_regex: null
    revision_retention_count: 3
```

Static sites do not accept `env_vars` or a runtime image. Use the declared
`build_environment` contract. Navigation placement and repository-backed icon
mask fields are accepted only for the workflow versions advertised by the
fresh backend template.
The retired `agent`, `streamlit_dashboard`, and
`code_repository_coding_agent` discriminators are invalid and must not be
translated.

## Automatic Redeployment

`automatic_deployment` is the target's master switch.
`automatic_redeployment` controls later repository-event eligibility:

```yaml
automatic_redeployment:
  enabled: true
  tag_regex: "^v[0-9]+\\.[0-9]+\\.[0-9]+$"
```

Omit the nested policy to use the backend-generated branch-specific SemVer
rule. Use explicit `tag_regex: null` only when every synchronized commit should
be eligible. Matching uses exact short tag names and full-match semantics.
Manual deployment does not silently enable automatic deployment.

For every Job, FastAPI application, or Harness Agent workflow, Django owns the
indexed resource and code-repository-image identities in automatic and non-automatic
paths. Disabling automatic deployment does not expose a UID-based image
selection escape hatch. Static Sites retain their backend-owned build path.

## Runtime Environment And Secrets

Workflow YAML can contain only non-secret target configuration. Never place API
keys, tokens, passwords, private keys, runtime credentials, registry grants, or
secret references in it. Use the platform-owned secret and credential flows.

Harness Agent runtime setup and local development are not owned by the
deployment workflow. Use the `code-repository-to-agent` skill for the handoff
to the installed runtime library's version-matched instructions.

## Observation And Failure Handling

After application, inspect the workflow result and referenced DeploymentRun.
Pending image dependencies, queued/running provider work, candidate revisions,
readiness, and activation are separate durable states. Do not repeat create
calls after an ambiguous provider response; reconcile the existing run.

A failed desired revision does not displace a prior ready active revision.
Retained revisions keep their exact image dependencies until canonical
retention cleanup removes them.

When validation fails, report exact backend paths and error codes. Do not invent
a corrected branch, internal UID, image, Agent UID, or deployment kind.
