from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


# GitLab access levels (Project Access Tokens API)
ACCESS_LEVEL_GUEST = 10
ACCESS_LEVEL_REPORTER = 20
ACCESS_LEVEL_DEVELOPER = 30
ACCESS_LEVEL_MAINTAINER = 40
ACCESS_LEVEL_OWNER = 50

READ_ONLY_CLONE_SCOPES = ["read_repository"]
READ_ONLY_CLONE_ACCESS_LEVEL = ACCESS_LEVEL_REPORTER


@dataclass
class ProjectAccessToken:
    """A GitLab project access token, as returned by the API.

    `token` is only populated on create/rotate responses — GitLab returns the
    secret value exactly once and never again.
    """

    id: int
    name: str
    scopes: list[str]
    access_level: int
    expires_at: date | None
    active: bool
    revoked: bool
    created_at: datetime | None
    token: str | None = None

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "ProjectAccessToken":
        expires_at = data.get("expires_at")
        created_at = data.get("created_at")
        return cls(
            id=data["id"],
            name=data["name"],
            scopes=data.get("scopes", []),
            access_level=data.get("access_level", READ_ONLY_CLONE_ACCESS_LEVEL),
            expires_at=date.fromisoformat(expires_at) if expires_at else None,
            active=data.get("active", False),
            revoked=data.get("revoked", False),
            created_at=datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else None,
            token=data.get("token"),
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize without the secret token value (for logs/listings)."""
        return {
            "id": self.id,
            "name": self.name,
            "scopes": self.scopes,
            "access_level": self.access_level,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "active": self.active,
            "revoked": self.revoked,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def to_dict_with_secret(self) -> dict[str, Any]:
        """Serialize including the secret token value. Only call this for the
        single stdout result of a create/rotate — never for logs."""
        d = self.to_safe_dict()
        d["token"] = self.token
        return d
