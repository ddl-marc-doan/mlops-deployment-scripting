from __future__ import annotations

import logging
import urllib.parse
from datetime import date
from typing import Any

import requests

from .exceptions import GitLabAPIError, TokenNotFoundError
from .models import READ_ONLY_CLONE_ACCESS_LEVEL, READ_ONLY_CLONE_SCOPES, ProjectAccessToken

logger = logging.getLogger(__name__)

# Never log the root token or any created/rotated secret token value.
_REDACTED = "<redacted>"


def _quote_project(project: str | int) -> str:
    """URL-encode a numeric project ID or 'group/subgroup/repo' path for use
    in a GitLab API path segment."""
    return urllib.parse.quote(str(project), safe="")


class GitLabProjectTokenClient:
    """Thin wrapper around the GitLab Project Access Tokens API.

    Reference: https://docs.gitlab.com/ee/api/project_access_tokens.html

    Authenticates with a "root" token (a project/group access token with the
    `api` scope, or an admin PAT) supplied by the caller. That token itself is
    never logged or included in any response payload built by this client.
    """

    def __init__(
        self,
        gitlab_url: str,
        root_token: str,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ):
        self.base_url = gitlab_url.rstrip("/")
        self._timeout = timeout
        self._session = session or requests.Session()
        self._session.headers.update({"PRIVATE-TOKEN": root_token})

    def _url(self, path: str) -> str:
        return f"{self.base_url}/api/v4{path}"

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = self._url(path)
        try:
            resp = self._session.request(method, url, timeout=self._timeout, **kwargs)
        except requests.RequestException as exc:
            raise GitLabAPIError(f"Request to {method} {path} failed: {exc}") from exc

        if resp.status_code >= 400:
            # Response bodies for this API do not echo the root token, so it's
            # safe to include for debugging, but we keep it off by default.
            raise GitLabAPIError(
                f"GitLab API error on {method} {path}: HTTP {resp.status_code}",
                status_code=resp.status_code,
                response_body=resp.text,
            )
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def list_tokens(self, project: str | int) -> list[ProjectAccessToken]:
        data = self._request("GET", f"/projects/{_quote_project(project)}/access_tokens")
        return [ProjectAccessToken.from_api(item) for item in data]

    def get_token(self, project: str | int, token_id: int) -> ProjectAccessToken:
        data = self._request(
            "GET", f"/projects/{_quote_project(project)}/access_tokens/{token_id}"
        )
        return ProjectAccessToken.from_api(data)

    def find_active_token_by_name(
        self, project: str | int, name: str
    ) -> ProjectAccessToken | None:
        for token in self.list_tokens(project):
            if token.name == name and token.active and not token.revoked:
                return token
        return None

    def create_token(
        self,
        project: str | int,
        name: str,
        expires_at: date,
        scopes: list[str] | None = None,
        access_level: int = READ_ONLY_CLONE_ACCESS_LEVEL,
    ) -> ProjectAccessToken:
        payload = {
            "name": name,
            "scopes": scopes or READ_ONLY_CLONE_SCOPES,
            "access_level": access_level,
            "expires_at": expires_at.isoformat(),
        }
        logger.info("Creating project access token %r on project %s", name, project)
        data = self._request(
            "POST", f"/projects/{_quote_project(project)}/access_tokens", json=payload
        )
        return ProjectAccessToken.from_api(data)

    def rotate_token(
        self,
        project: str | int,
        token_id: int,
        expires_at: date | None = None,
    ) -> ProjectAccessToken:
        """Revokes the given token and returns a brand-new one with the same
        name/scopes/access level. The new token value is only ever returned
        once, in this response."""
        payload: dict[str, Any] = {}
        if expires_at is not None:
            payload["expires_at"] = expires_at.isoformat()
        logger.info("Rotating project access token id=%s on project %s", token_id, project)
        data = self._request(
            "POST",
            f"/projects/{_quote_project(project)}/access_tokens/{token_id}/rotate",
            json=payload,
        )
        return ProjectAccessToken.from_api(data)

    def revoke_token(self, project: str | int, token_id: int) -> None:
        logger.info("Revoking project access token id=%s on project %s", token_id, project)
        self._request(
            "DELETE", f"/projects/{_quote_project(project)}/access_tokens/{token_id}"
        )

    def revoke_token_by_name(self, project: str | int, name: str) -> ProjectAccessToken:
        token = self.find_active_token_by_name(project, name)
        if token is None:
            raise TokenNotFoundError(
                f"No active token named {name!r} found on project {project!r}"
            )
        self.revoke_token(project, token.id)
        return token
