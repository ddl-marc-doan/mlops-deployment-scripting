#!/usr/bin/env python3
"""Mint a GitLab Personal Access Token with scopes read_api and read_repo.

Authenticates with the GITLAB_PRIV_TOKEN environment variable (must have the
`api` scope). Set GITLAB_URL to target a self-managed instance
(default: https://gitlab.com).

Prints JSON to stdout including the token `id`, which is what delete_pat.py
needs, and the secret `token` value (only returned once, at creation).
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

SCOPES = ["read_api", "read_repo"]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--name",
        default="read-api-repo-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        help="name for the new token (default: read-api-repo-<timestamp>)",
    )
    parser.add_argument(
        "--expires-in-days",
        type=int,
        default=30,
        help="days until the token expires (default: 30; GitLab max is 365)",
    )
    args = parser.parse_args()

    priv_token = os.environ.get("GITLAB_PRIV_TOKEN")
    if not priv_token:
        sys.exit("error: GITLAB_PRIV_TOKEN environment variable is not set")
    base_url = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")

    expires_at = (
        datetime.date.today() + datetime.timedelta(days=args.expires_in_days)
    ).isoformat()
    body = json.dumps(
        {"name": args.name, "scopes": SCOPES, "expires_at": expires_at}
    ).encode()
    req = urllib.request.Request(
        f"{base_url}/api/v4/user/personal_access_tokens",
        data=body,
        method="POST",
        headers={"PRIVATE-TOKEN": priv_token, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"error: GitLab returned HTTP {e.code}: {e.read().decode(errors='replace')}")
    except urllib.error.URLError as e:
        sys.exit(f"error: could not reach {base_url}: {e.reason}")

    print(
        json.dumps(
            {
                "id": data["id"],
                "name": data["name"],
                "scopes": data["scopes"],
                "expires_at": data.get("expires_at"),
                "token": data["token"],
            },
            indent=2,
        )
    )
    print(f"To delete: python delete_pat.py {data['id']}", file=sys.stderr)


if __name__ == "__main__":
    main()
