# domino-mlops

> **Work in progress.** These scripts have only been tested against a local stub server, not a live Domino deployment. See [Unverified assumptions](#unverified-assumptions).

Python scripts for the Domino Data Lab platform API. They target **Domino 6.3.0 or higher** and authenticate with a service-account token sent as a bearer token.

## Setup

```bash
pip install -r requirements.txt
export DOMINO_URL=https://your-domino.example.com
export DOMINO_API_TOKEN=<service-account token>
```

Every script also accepts `--url` and `--token`. `domino-auth.py` is the only one where `--token` is the documented way to pass the token; for the others, prefer the environment variable.

## Scripts

### `domino-auth.py`

Builds an authenticated `requests` session. Domino has no login or token-exchange endpoint, so this means setting `Authorization: Bearer <token>` on a session.

- `--url` / `DOMINO_URL` is required.
- `--token` / `DOMINO_API_TOKEN` is required.
- Run directly, it verifies the credentials with `GET /api/users/v1/self`:

```bash
python domino-auth.py
# OK: authenticated to https://your-domino.example.com as svc-account
```

The other scripts load it with `importlib` because the hyphen in the filename prevents a plain `import`. Its helpers are `get_session()`, `api_request()`, `add_auth_args()` and `fail()`.

### `governance-project-status.py`

Reports whether a governance bundle is fully complete.

```bash
python governance-project-status.py --project-name my-project --bundle-name "Bundle A,Bundle B"
```

| Flag | Required | Description |
|---|---|---|
| `--project-name` | yes | Domino project name (matched exactly against each bundle's `projectName`) |
| `--bundle-name` | yes | Bundle name; comma-separate to check several |

A bundle is **complete** when all of these hold:

1. Every approval is `Approved` or `ConditionallyApproved`.
2. Every required, visible evidence artifact has a latest result. Guidance-type artifacts are skipped, since they take no result.
3. No finding is open (any status other than `Done` or `WontDo`).

Output is JSON with `complete` overall and per bundle, plus `approvals`, `missingEvidence` and `openFindings`.

Exit codes: `0` all bundles complete, `1` something incomplete, `2` error (bad arguments, bundle not found, API failure).

Endpoints used: `GET /api/governance/v1/bundles`, `GET /api/governance/v1/bundles/{id}/approvals`, `POST /api/governance/v1/rpc/compute-policy`.

### `model-metadata.py`

Fetches the MLflow run behind a registered model version, to capture its code commit and Domino Environment.

```bash
python model-metadata.py --model-name my-model --model-version 3
```

| Flag | Required | Description |
|---|---|---|
| `--model-name` | yes | Registered model name |
| `--model-version` | yes | Version number |
| `--project-name` | no | If given, must match the model's project. The registry API does not need it. |
| `--mlflow-uri` | no | MLflow tracking URI. Default: `$MLFLOW_TRACKING_URI`, else `$DOMINO_URL/mlflow` |

Output is JSON: `model`, `version`, `project`, `runId`, the full MLflow `run`, and a `summary` with `git_commit` and `environment`. The summary looks for the `mlflow.source.git.commit` tag first, then any tag or param whose key contains `commit` or `environment`. A value not found is `null`, with a note on stderr.

Endpoints used: `GET /api/registeredmodels/v2/{name}/versions/{version}`, then `GET {mlflow-uri}/api/2.0/mlflow/runs/get`.

## Unverified assumptions

- **MLflow URI.** The default `$DOMINO_URL/mlflow` and the acceptance of the bearer token by Domino's MLflow server are not confirmed in Domino's docs. Override with `--mlflow-uri` if needed.
- **Commit and environment keys.** The docs do not say which tags or params hold these. Check `summary` against a real run; the full `run` is always included.
- **"Complete" rule.** Domino has no single completion field; the rule above is derived from the approvals, compute-policy and findings data.
- **Live testing.** Endpoint paths and fields were checked against the 6.3 `public-api.json` spec, but no script has run against a real deployment.
