#!/usr/bin/env python3
"""Fetch MLflow metadata for a Domino registered model version.

Looks up the version in the Domino model registry to find its source MLflow
run, then fetches that run from Domino's MLflow server. Prints JSON with the
full run plus a `summary` that picks out the code commit and Domino
Environment (null when no matching tag/param is found).

The MLflow URI defaults to <DOMINO_URL>/mlflow and is UNVERIFIED against
Domino's docs; override with --mlflow-uri or MLFLOW_TRACKING_URI.
"""
import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path

import requests


def load_auth():
    spec = importlib.util.spec_from_file_location(
        "domino_auth", Path(__file__).with_name("domino-auth.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


auth = load_auth()

COMMIT_KEYS = ("mlflow.source.git.commit",)
COMMIT_HINT = "commit"
ENV_HINT = "environment"


def find_key(entries, exact, hint):
    """Return (key, value) from a {key: value} dict: exact keys first, then substring match."""
    for key in exact:
        if key in entries:
            return key, entries[key]
    for key, value in entries.items():
        if hint in key.lower():
            return key, value
    return None, None


def summarize(run):
    data = run.get("data") or {}
    tags = {t["key"]: t["value"] for t in data.get("tags") or []}
    params = {p["key"]: p["value"] for p in data.get("params") or []}
    summary = {}
    for label, exact, hint in (("git_commit", COMMIT_KEYS, COMMIT_HINT), ("environment", (), ENV_HINT)):
        key, value = find_key(tags, exact, hint)
        source = "tag"
        if key is None:
            key, value = find_key(params, exact, hint)
            source = "param"
        summary[label] = {"value": value, "source": f"{source}:{key}"} if key else None
        if key is None:
            print(f"note: no {label} tag or param found on the run", file=sys.stderr)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-name", required=True, help="registered model name")
    parser.add_argument("--model-version", required=True, type=int, help="registered model version number")
    parser.add_argument(
        "--project-name",
        help="optional; if given, must match the project that owns the model (the registry API does not need it)",
    )
    parser.add_argument(
        "--mlflow-uri", help="MLflow tracking URI (default: $MLFLOW_TRACKING_URI or <DOMINO_URL>/mlflow)"
    )
    auth.add_auth_args(parser)
    args = parser.parse_args()

    session, base_url = auth.get_session(args.url, args.token)
    version = auth.api_request(
        session,
        "GET",
        f"{base_url}/api/registeredmodels/v2/{requests.utils.quote(args.model_name, safe='')}"
        f"/versions/{args.model_version}",
    ).json()

    project = version.get("project") or {}
    if args.project_name and project.get("name") != args.project_name:
        auth.fail(
            f"model '{args.model_name}' version {args.model_version} belongs to project "
            f"'{project.get('name')}', not '{args.project_name}'"
        )
    run_id = version.get("experimentRunId")
    if not run_id:
        auth.fail("registered model version has no experimentRunId")

    mlflow_uri = (args.mlflow_uri or os.environ.get("MLFLOW_TRACKING_URI") or f"{base_url}/mlflow").rstrip("/")
    run = auth.api_request(
        session, "GET", f"{mlflow_uri}/api/2.0/mlflow/runs/get", params={"run_id": run_id}
    ).json().get("run", {})

    print(
        json.dumps(
            {
                "model": args.model_name,
                "version": args.model_version,
                "project": project,
                "runId": run_id,
                "summary": summarize(run),
                "run": run,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
