from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .models import READ_ONLY_CLONE_ACCESS_LEVEL, READ_ONLY_CLONE_SCOPES


@dataclass
class RepoTokenSpec:
    """Desired-state spec for one repo's read-only clone token."""

    project: str
    name: str
    scopes: list[str] = field(default_factory=lambda: list(READ_ONLY_CLONE_SCOPES))
    access_level: int = READ_ONLY_CLONE_ACCESS_LEVEL
    expires_in_days: int = 30
    rotate_within_days: int = 7

    @classmethod
    def from_dict(cls, data: dict) -> "RepoTokenSpec":
        return cls(
            project=str(data["project"]),
            name=data.get("name", "domino-clone-ro"),
            scopes=list(data.get("scopes", READ_ONLY_CLONE_SCOPES)),
            access_level=int(data.get("access_level", READ_ONLY_CLONE_ACCESS_LEVEL)),
            expires_in_days=int(data.get("expires_in_days", 30)),
            rotate_within_days=int(data.get("rotate_within_days", 7)),
        )


def load_repo_specs(path: str | Path) -> list[RepoTokenSpec]:
    """Load a batch config file (YAML or JSON) listing repos to manage.

    Expected shape:

        repos:
          - project: group/subgroup/repo-a
            name: domino-clone-ro
            expires_in_days: 30
            rotate_within_days: 7
          - project: 12345
            name: domino-clone-ro
    """
    p = Path(path)
    text = p.read_text()
    if p.suffix.lower() == ".json":
        raw = json.loads(text)
    else:
        raw = yaml.safe_load(text)

    entries = raw.get("repos", []) if isinstance(raw, dict) else raw
    if not entries:
        return []
    return [RepoTokenSpec.from_dict(entry) for entry in entries]
