"""CLI for managing per-repo GitLab Project Access Tokens used for
read-only cloning (e.g. into a Domino Data Lab project via a service
account).

Authenticates to the GitLab API with a "root" token: an existing
project or group access token (scope: `api`) with Maintainer/Owner
rights on the target project(s). That root token is read only from the
environment or a file and is never logged or echoed.

All informational/progress output goes to stderr. The only thing ever
written to stdout is the JSON result of the command, including the
secret token value on `create`/`rotate`/`ensure`/`sync` when a new
token was actually minted. Treat stdout as sensitive: callers should
capture it directly into a secrets store rather than a log file.

Examples:

    export GITLAB_ROOT_TOKEN=glpat-...   # masked+protected CI variable

    gitlab-pat-manager create --project group/repo --name domino-clone-ro \\
        --expires-in-days 30

    gitlab-pat-manager list --project group/repo

    gitlab-pat-manager ensure --project group/repo --name domino-clone-ro \\
        --expires-in-days 30 --rotate-within-days 7

    gitlab-pat-manager sync --config repos.yaml

    gitlab-pat-manager revoke --project group/repo --name domino-clone-ro
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta

from .client import GitLabProjectTokenClient
from .config import RepoTokenSpec, load_repo_specs
from .exceptions import GitLabAPIError, TokenNotFoundError
from .manager import ensure_repo_token
from .models import READ_ONLY_CLONE_ACCESS_LEVEL, READ_ONLY_CLONE_SCOPES

logger = logging.getLogger("gitlab_pat_manager")


def _emit(obj) -> None:
    print(json.dumps(obj, indent=2, sort_keys=True))


def _build_client(args: argparse.Namespace) -> GitLabProjectTokenClient:
    gitlab_url = args.gitlab_url or os.environ.get("GITLAB_URL", "https://gitlab.com")
    root_token = args.root_token or os.environ.get("GITLAB_ROOT_TOKEN")
    if not root_token:
        logger.error(
            "No root token provided. Set GITLAB_ROOT_TOKEN or pass --root-token."
        )
        sys.exit(2)
    return GitLabProjectTokenClient(gitlab_url=gitlab_url, root_token=root_token, timeout=args.timeout)


def _cmd_create(args: argparse.Namespace) -> int:
    client = _build_client(args)
    expires_at = date.today() + timedelta(days=args.expires_in_days)
    token = client.create_token(
        project=args.project,
        name=args.name,
        expires_at=expires_at,
        scopes=args.scopes,
        access_level=args.access_level,
    )
    _emit(token.to_dict_with_secret())
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    client = _build_client(args)
    tokens = client.list_tokens(args.project)
    _emit([t.to_safe_dict() for t in tokens])
    return 0


def _resolve_token_id(client: GitLabProjectTokenClient, args: argparse.Namespace) -> int:
    if args.token_id is not None:
        return args.token_id
    token = client.find_active_token_by_name(args.project, args.name)
    if token is None:
        raise TokenNotFoundError(
            f"No active token named {args.name!r} found on project {args.project!r}"
        )
    return token.id


def _cmd_rotate(args: argparse.Namespace) -> int:
    client = _build_client(args)
    token_id = _resolve_token_id(client, args)
    expires_at = date.today() + timedelta(days=args.expires_in_days) if args.expires_in_days else None
    token = client.rotate_token(args.project, token_id, expires_at=expires_at)
    _emit(token.to_dict_with_secret())
    return 0


def _cmd_revoke(args: argparse.Namespace) -> int:
    client = _build_client(args)
    token_id = _resolve_token_id(client, args)
    client.revoke_token(args.project, token_id)
    _emit({"project": args.project, "token_id": token_id, "revoked": True})
    return 0


def _cmd_ensure(args: argparse.Namespace) -> int:
    client = _build_client(args)
    spec = RepoTokenSpec(
        project=args.project,
        name=args.name,
        scopes=args.scopes,
        access_level=args.access_level,
        expires_in_days=args.expires_in_days,
        rotate_within_days=args.rotate_within_days,
    )
    token, changed = ensure_repo_token(client, spec)
    result = token.to_dict_with_secret() if changed else token.to_safe_dict()
    result["changed"] = changed
    _emit(result)
    return 0


def _cmd_sync(args: argparse.Namespace) -> int:
    client = _build_client(args)
    specs = load_repo_specs(args.config)
    if not specs:
        logger.warning("No repos found in config file %s", args.config)

    results = []
    exit_code = 0
    for spec in specs:
        try:
            token, changed = ensure_repo_token(client, spec)
        except GitLabAPIError as exc:
            logger.error("Failed to sync project %s: %s", spec.project, exc)
            results.append({"project": spec.project, "error": str(exc)})
            exit_code = 1
            continue
        result = token.to_dict_with_secret() if changed else token.to_safe_dict()
        result["changed"] = changed
        results.append(result)

    _emit(results)
    return exit_code


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gitlab-pat-manager",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--gitlab-url",
        help="GitLab base URL (default: $GITLAB_URL or https://gitlab.com)",
    )
    parser.add_argument(
        "--root-token",
        help=(
            "Root token with api scope on the target project(s). "
            "Prefer $GITLAB_ROOT_TOKEN over this flag to keep it out of shell history/process list."
        ),
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging on stderr")

    sub = parser.add_subparsers(dest="command", required=True)

    def add_project_arg(p):
        p.add_argument("--project", required=True, help="Numeric project ID or 'group/subgroup/repo' path")

    def add_scope_args(p):
        p.add_argument(
            "--scopes",
            nargs="+",
            default=list(READ_ONLY_CLONE_SCOPES),
            help=f"Token scopes (default: {READ_ONLY_CLONE_SCOPES})",
        )
        p.add_argument(
            "--access-level",
            type=int,
            default=READ_ONLY_CLONE_ACCESS_LEVEL,
            help="GitLab access level: 10=Guest 20=Reporter 30=Developer 40=Maintainer 50=Owner (default: 20/Reporter)",
        )

    p_create = sub.add_parser("create", help="Create a new project access token")
    add_project_arg(p_create)
    p_create.add_argument("--name", required=True, help="Token name")
    p_create.add_argument("--expires-in-days", type=int, default=30)
    add_scope_args(p_create)
    p_create.set_defaults(func=_cmd_create)

    p_list = sub.add_parser("list", help="List project access tokens (never shows secret values)")
    add_project_arg(p_list)
    p_list.set_defaults(func=_cmd_list)

    p_rotate = sub.add_parser("rotate", help="Rotate an existing project access token")
    add_project_arg(p_rotate)
    group = p_rotate.add_mutually_exclusive_group(required=True)
    group.add_argument("--token-id", type=int, help="Token ID to rotate")
    group.add_argument("--name", help="Token name to look up and rotate")
    p_rotate.add_argument("--expires-in-days", type=int, default=30)
    p_rotate.set_defaults(func=_cmd_rotate)

    p_revoke = sub.add_parser("revoke", help="Revoke a project access token")
    add_project_arg(p_revoke)
    group = p_revoke.add_mutually_exclusive_group(required=True)
    group.add_argument("--token-id", type=int, help="Token ID to revoke")
    group.add_argument("--name", help="Token name to look up and revoke")
    p_revoke.set_defaults(func=_cmd_revoke)

    p_ensure = sub.add_parser(
        "ensure",
        help="Idempotently ensure a named token exists and isn't about to expire (create or rotate as needed)",
    )
    add_project_arg(p_ensure)
    p_ensure.add_argument("--name", required=True, help="Token name")
    p_ensure.add_argument("--expires-in-days", type=int, default=30)
    p_ensure.add_argument(
        "--rotate-within-days",
        type=int,
        default=7,
        help="Rotate if the existing token expires within this many days",
    )
    add_scope_args(p_ensure)
    p_ensure.set_defaults(func=_cmd_ensure)

    p_sync = sub.add_parser(
        "sync", help="Run 'ensure' for every repo listed in a batch config file"
    )
    p_sync.add_argument("--config", required=True, help="Path to a YAML/JSON repo list")
    p_sync.set_defaults(func=_cmd_sync)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    try:
        return args.func(args)
    except TokenNotFoundError as exc:
        logger.error(str(exc))
        return 3
    except GitLabAPIError as exc:
        logger.error(str(exc))
        if args.verbose and exc.response_body:
            logger.debug("Response body: %s", exc.response_body)
        return 1


if __name__ == "__main__":
    sys.exit(main())
