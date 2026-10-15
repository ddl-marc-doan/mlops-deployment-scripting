#!/usr/bin/env python3
"""Authenticate to the Domino API with a service-account bearer token.

Reads the deployment URL from --url or DOMINO_URL (required) and the token
from --token or DOMINO_API_TOKEN (required). Domino has no login or
token-exchange endpoint: the token is sent as `Authorization: Bearer <token>`
on every request, so "logging in" means building an authenticated session.

Run directly to verify the credentials against GET /api/users/v1/self.

Other scripts import this file by its hyphenated name with importlib; see
load_auth() in governance-project-status.py.
"""
import argparse
import os
import sys

import requests

URL_ENV = "DOMINO_URL"
TOKEN_ENV = "DOMINO_API_TOKEN"
EXIT_ERROR = 2


def fail(message):
    """Print an error to stderr and exit with the shared error code."""
    print(f"error: {message}", file=sys.stderr)
    sys.exit(EXIT_ERROR)


def get_domino_url(url=None):
    url = url or os.environ.get(URL_ENV)
    if not url:
        fail(f"Domino URL required: pass --url or set {URL_ENV}")
    return url.rstrip("/")


def get_token(token=None):
    token = token or os.environ.get(TOKEN_ENV)
    if not token:
        fail(f"Domino API token required: set {TOKEN_ENV} (or pass --token to domino-auth.py)")
    return token


def get_session(url=None, token=None):
    """Return (session, base_url) with the bearer header set."""
    base_url = get_domino_url(url)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {get_token(token)}"
    session.headers["Accept"] = "application/json"
    return session, base_url


def api_request(session, method, url, **kwargs):
    """Make a request and exit with a clear message on any failure."""
    try:
        resp = session.request(method, url, timeout=60, **kwargs)
    except requests.RequestException as e:
        fail(f"could not reach {url}: {e}")
    if not resp.ok:
        fail(f"{method} {url} returned HTTP {resp.status_code}: {resp.text[:500]}")
    return resp


def add_auth_args(parser):
    """Add the --url/--token flags shared by every script."""
    parser.add_argument("--url", help=f"Domino URL (default: ${URL_ENV})")
    parser.add_argument("--token", help=f"service-account token (default: ${TOKEN_ENV})")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    add_auth_args(parser)
    args = parser.parse_args()

    session, base_url = get_session(args.url, args.token)
    user = api_request(session, "GET", f"{base_url}/api/users/v1/self").json().get("user", {})
    print(f"OK: authenticated to {base_url} as {user.get('userName', '<unknown>')}")


if __name__ == "__main__":
    main()
