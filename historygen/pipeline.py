"""Stage registry and the ordered, resumable runner.

Each stage is a callable `run(manifest) -> None` that mutates the manifest in place
and saves it. The runner executes stages in order; a stage skips itself internally
when its inputs are unchanged (see manifest.is_fresh). `metadata` is folded into the
script/assemble flow as the final step.
"""

from __future__ import annotations

from collections.abc import Callable

from historygen.manifest import Manifest
from historygen.stages import (
    assemble,
    captions,
    music,
    narration,
    script,
    visuals,
)

# Ordered list of (name, callable). Order matters: later stages consume earlier output.
STAGES: list[tuple[str, Callable[[Manifest], None]]] = [
    ("script", script.run),
    ("narration", narration.run),
    ("visuals", visuals.run),
    ("captions", captions.run),
    ("music", music.run),
    ("assemble", assemble.run),
]

STAGE_NAMES = [name for name, _ in STAGES]


def run_all(manifest: Manifest, only: str | None = None, force: bool = False) -> None:
    for name, fn in STAGES:
        if only and name != only:
            continue
        if force:
            manifest.invalidate(name)
        print(f"\n=== stage: {name} ===")
        fn(manifest)
    print("\nDone. Manifest:", manifest.path)
