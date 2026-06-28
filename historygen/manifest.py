"""Project manifest: the single JSON file that flows through every stage.

It holds the `Project` (topic, scenes, assets) plus a `stage_cache` recording the
input-hash each stage last ran with. A stage is skipped when its current input-hash
matches the cached one — so re-running `run` only repeats work whose inputs changed.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from historygen.config import assets_dir, project_dir
from historygen.schemas import Project


def slugify(text: str) -> str:
    text = text.lower().strip()
    # keep ascii letters/digits; collapse everything else to single hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:60] or "project"


def input_hash(*parts: Any) -> str:
    """Stable hash of a stage's inputs (used for skip-if-unchanged)."""
    blob = json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


class Manifest:
    def __init__(self, project: Project, stage_cache: dict[str, str] | None = None):
        self.project = project
        self.stage_cache: dict[str, str] = stage_cache or {}

    # --- paths -------------------------------------------------------------
    @property
    def slug(self) -> str:
        return self.project.slug

    @property
    def dir(self) -> Path:
        return project_dir(self.slug)

    @property
    def assets(self) -> Path:
        return assets_dir(self.slug)

    @property
    def path(self) -> Path:
        return self.dir / "manifest.json"

    # --- lifecycle ---------------------------------------------------------
    @classmethod
    def create(cls, topic: str) -> "Manifest":
        slug = slugify(topic)
        project = Project(slug=slug, topic=topic)
        m = cls(project)
        m.assets.mkdir(parents=True, exist_ok=True)
        m.save()
        return m

    @classmethod
    def load(cls, slug: str) -> "Manifest":
        path = project_dir(slug) / "manifest.json"
        if not path.exists():
            raise FileNotFoundError(f"No project '{slug}' at {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            project=Project.model_validate(data["project"]),
            stage_cache=data.get("stage_cache", {}),
        )

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "project": self.project.model_dump(),
            "stage_cache": self.stage_cache,
        }
        self.path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    # --- stage cache -------------------------------------------------------
    def is_fresh(self, stage: str, current_hash: str) -> bool:
        return self.stage_cache.get(stage) == current_hash

    def mark_done(self, stage: str, current_hash: str) -> None:
        self.stage_cache[stage] = current_hash
        self.save()

    def invalidate(self, stage: str) -> None:
        self.stage_cache.pop(stage, None)
