#!/usr/bin/env python3
"""Delete (revoke) a GitLab Personal Access Token by its numeric id.

The id is printed by create_pat.py. Authenticates with the GITLAB_PRIV_TOKEN
environment variable. Set GITLAB_URL to target a self-managed instance
(default: https://gitlab.com).
"""
import argparse
import os
import sys
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("token_id", type=int, help="id of the token to delete")
    args = parser.parse_args()

    priv_token = os.environ.get("GITLAB_PRIV_TOKEN")
    if not priv_token:
        sys.exit("error: GITLAB_PRIV_TOKEN environment variable is not set")
    base_url = os.environ.get("GITLAB_URL", "https://gitlab.com").rstrip("/")

    req = urllib.request.Request(
        f"{base_url}/api/v4/personal_access_tokens/{args.token_id}",
        method="DELETE",
        headers={"PRIVATE-TOKEN": priv_token},
    )
    try:
        with urllib.request.urlopen(req):
            pass
    except urllib.error.HTTPError as e:
        sys.exit(f"error: GitLab returned HTTP {e.code}: {e.read().decode(errors='replace')}")
    except urllib.error.URLError as e:
        sys.exit(f"error: could not reach {base_url}: {e.reason}")

    print(f"Deleted personal access token {args.token_id}")


if __name__ == "__main__":
    main()
