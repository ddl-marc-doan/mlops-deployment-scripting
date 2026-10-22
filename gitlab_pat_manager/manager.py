from __future__ import annotations

import logging
from datetime import date, timedelta

from .client import GitLabProjectTokenClient
from .config import RepoTokenSpec
from .models import ProjectAccessToken

logger = logging.getLogger(__name__)


def ensure_repo_token(
    client: GitLabProjectTokenClient, spec: RepoTokenSpec
) -> tuple[ProjectAccessToken, bool]:
    """Idempotently ensure `spec.project` has a live, non-expiring-soon token
    named `spec.name`.

    Returns (token, changed). `token.token` (the secret value) is only set
    when `changed` is True — a no-op run never has the secret to leak.
    """
    existing = client.find_active_token_by_name(spec.project, spec.name)
    new_expiry = date.today() + timedelta(days=spec.expires_in_days)

    if existing is None:
        logger.info(
            "No active token named %r on %s; creating one", spec.name, spec.project
        )
        token = client.create_token(
            spec.project,
            spec.name,
            expires_at=new_expiry,
            scopes=spec.scopes,
            access_level=spec.access_level,
        )
        return token, True

    rotate_threshold = date.today() + timedelta(days=spec.rotate_within_days)
    needs_rotation = existing.expires_at is not None and existing.expires_at <= rotate_threshold

    if not needs_rotation:
        logger.info(
            "Token %r on %s is still valid until %s; no action needed",
            spec.name,
            spec.project,
            existing.expires_at,
        )
        return existing, False

    logger.info(
        "Token %r on %s expires %s (within %d-day threshold); rotating",
        spec.name,
        spec.project,
        existing.expires_at,
        spec.rotate_within_days,
    )
    token = client.rotate_token(spec.project, existing.id, expires_at=new_expiry)
    return token, True
