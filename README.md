# gitlab-pat-manager

Manage per-repo GitLab **Project Access Tokens** used as read-only `git clone`
credentials, intended to be attached to a Domino Data Lab Service Account so
a Domino project can clone the codebase over HTTPS.

## Context / where this fits

This repo answers one narrow piece of a larger pipeline:

1. A GitLab CI run fires.
2. Something (not this repo) idempotently creates a **Domino Service
   Account** if it doesn't already exist, and mints/refreshes a **Domino API
   token** for it. That token is cycled by its own separate process.
3. **This repo** mints/rotates a **GitLab Project Access Token**, scoped
   `read_repository`, for the specific repo the Domino project needs to
   clone.
4. Something (not this repo) takes that GitLab token and attaches it to the
   Domino Service Account as its git credential.

`gitlab_pat_manager` only ever talks to the GitLab API. It never touches
Domino, and it never decides whether a Domino Service Account exists — it
just guarantees a given repo has a live, read-only, not-about-to-expire
clone token, and hands the secret value back to whatever calls it.

See `.gitlab-ci.example.yml` for a sample pipeline showing this script as the
middle stage between Domino SA provisioning and the Domino-side attach step.

### Why Project Access Tokens, not personal access tokens

GitLab has two mechanisms that could plausibly be called a "per-repo PAT":

- **Project Access Token** (what this tool uses): `POST
  /projects/:id/access_tokens`. Natively scoped to exactly one repo, needs
  only Maintainer/Owner rights on that repo (no GitLab admin), and is a
  first-class read-only clone credential. It creates its own bot user per
  project, which is irrelevant here — the token value is just a bearer
  credential for `git clone`/API calls, regardless of whose bot user nominally
  owns it.
- **Real user Personal Access Token**, minted via the admin-only `POST
  /users/:user_id/personal_access_tokens`. Requires instance-admin rights and
  isn't naturally scoped to one repo (scope comes from the user's project
  memberships instead).

Project Access Tokens were chosen because they need no admin rights, are
naturally one-token-per-repo, and the resulting token works as a plain HTTPS
git credential — Domino-side association with the Service Account is a
separate concern handled outside this repo.

## Install

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

Or just install the two runtime dependencies and run as a module:

```bash
pip install requests PyYAML
python -m gitlab_pat_manager --help
```

## Authentication

All commands need a "root" token with the GitLab `api` scope and
Maintainer/Owner rights on the target project(s) — e.g. an existing
project- or group-level access token. Set it as a **masked, protected** CI/CD
variable and never pass it on the command line (it would show up in shell
history / process listings):

```bash
export GITLAB_URL=https://gitlab.example.com   # default: https://gitlab.com
export GITLAB_ROOT_TOKEN=glpat-...
```

## Commands

Global flags (apply to every subcommand):

| Flag | Env fallback | Default | Notes |
|---|---|---|---|
| `--gitlab-url` | `GITLAB_URL` | `https://gitlab.com` | GitLab instance base URL |
| `--root-token` | `GITLAB_ROOT_TOKEN` | — | Prefer the env var over this flag |
| `--timeout` | — | `30.0` | HTTP timeout in seconds |
| `-v`, `--verbose` | — | off | Debug logging on stderr, plus the GitLab response body on API errors |

### `create`

Create a brand-new project access token.

```bash
gitlab-pat-manager create --project group/repo --name domino-clone-ro \
  --expires-in-days 30
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--project` | yes | — | Numeric project ID or `group/subgroup/repo` path |
| `--name` | yes | — | Token name |
| `--expires-in-days` | no | `30` | Token lifetime from today |
| `--scopes` | no | `read_repository` | One or more token scopes |
| `--access-level` | no | `20` (Reporter) | `10` Guest / `20` Reporter / `30` Developer / `40` Maintainer / `50` Owner |

### `list`

List all project access tokens on a repo. Never includes secret values (the
API itself doesn't return them except on create/rotate).

```bash
gitlab-pat-manager list --project group/repo
```

| Flag | Required | Description |
|---|---|---|
| `--project` | yes | Numeric project ID or path |

### `rotate`

Revoke an existing token and mint a replacement with the same name/scopes,
identified by either its numeric ID or its name.

```bash
gitlab-pat-manager rotate --project group/repo --name domino-clone-ro --expires-in-days 30
```

| Flag | Required | Description |
|---|---|---|
| `--project` | yes | Numeric project ID or path |
| `--token-id` | one of `--token-id`/`--name` | Token ID to rotate |
| `--name` | one of `--token-id`/`--name` | Token name to look up and rotate |
| `--expires-in-days` | no (default `30`) | New expiry from today |

### `revoke`

```bash
gitlab-pat-manager revoke --project group/repo --name domino-clone-ro
```

| Flag | Required | Description |
|---|---|---|
| `--project` | yes | Numeric project ID or path |
| `--token-id` | one of `--token-id`/`--name` | Token ID to revoke |
| `--name` | one of `--token-id`/`--name` | Token name to look up and revoke |

### `ensure` (idempotent, single repo)

Creates the named token if it doesn't exist, rotates it if it's within
`--rotate-within-days` of expiring, and no-ops otherwise. Safe to run on
every pipeline execution.

```bash
gitlab-pat-manager ensure --project group/repo --name domino-clone-ro \
  --expires-in-days 30 --rotate-within-days 7
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--project` | yes | — | Numeric project ID or path |
| `--name` | yes | — | Token name |
| `--expires-in-days` | no | `30` | Lifetime applied to any newly created/rotated token |
| `--rotate-within-days` | no | `7` | Rotate an existing token if it expires within this window |
| `--scopes` | no | `read_repository` | Scopes applied only when creating (not on rotate) |
| `--access-level` | no | `20` (Reporter) | Access level applied only when creating |

### `sync` (idempotent, batch)

Runs the same `ensure` logic across every repo listed in a config file.

```bash
gitlab-pat-manager sync --config repos.yaml
```

| Flag | Required | Description |
|---|---|---|
| `--config` | yes | Path to a YAML or JSON repo list (see `repos.example.yaml`) |

Config file shape (`repos.yaml`):

```yaml
repos:
  - project: my-group/my-subgroup/repo-a   # numeric ID or group/.../repo path
    name: domino-clone-ro                  # default: domino-clone-ro
    scopes: [read_repository]              # default: [read_repository]
    access_level: 20                       # default: 20 (Reporter)
    expires_in_days: 30                    # default: 30
    rotate_within_days: 7                  # default: 7
  - project: 123456                        # only `project` is required
```

A JSON file with the same `{"repos": [...]}` shape also works.

## Output contract

- **stdout** carries only the JSON result of the command. On `create`,
  `rotate`, and on `ensure`/`sync` when a token was actually created or
  rotated, this JSON includes the one-time secret `token` field — GitLab
  never returns the value again after that response. A no-op `ensure`/`sync`
  run returns the token's metadata only, with no secret to leak.
- **stderr** carries all logging (`-v` for debug detail, including the
  GitLab response body on API errors).

Treat stdout as sensitive: pipe it straight into a secrets store or a masked
CI `dotenv` artifact (see `.gitlab-ci.example.yml`), not into a log file.

## Out of scope

- Creating or rotating the Domino Service Account itself.
- Creating or rotating the Domino API token used to authenticate to Domino.
- Attaching the GitLab clone token to the Domino Service Account's git
  credentials (the Domino-side API call).

These are handled by separate scripting; this repo's only output is a
narrowly-scoped, read-only GitLab credential.

## Tests

```bash
python -m unittest discover -s tests -v
```
