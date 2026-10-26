"""Export a reviewed architecture snapshot without private data or Git history."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_ID = "kei-v1.1-public"
SOURCE_BASELINE = "86c57fdc2cd7fd30f8e0063841664b6457c745da"
FILE_ALLOWLIST = (
    ".env.example",
    ".gitignore",
    "README.md",
    "CONTRIBUTING.md",
    "THIRD_PARTY_NOTICES.md",
    "requirements.txt",
    "requirements-offline.txt",
    "app.py",
    "main.py",
    "config.py",
    "roles/profiles/tendou_kei.yaml",
    "roles/stickers/packs/README.md",
    "docs/ARCHITECTURE_DECISIONS.md",
    "docs/FAILURE_CASES.md",
    "docs/ROLEPLAY_DEVELOPMENT_MANUAL.md",
    "releases/kei-v1.1-public/README.md",
)
CODE_DIRS = (
    "context", "core", "knowledge", "llm", "memory", "prompts",
    "roleplay", "roles", "session", "summary", "web",
)
EXTRA_CODE = ("tools/export_public_kei.py", "tests/test_public_snapshot.py")
EXCLUDED = (
    ".git history", ".env and secrets", "private scene cards and unreviewed profiles",
    "real chats, memory, indexes, logs", "model weights", "official images and dialogue",
    "Momotalk and Base-56 frontend/source",
)


def public_files() -> list[Path]:
    """Return only reviewed public paths, independent of Git tracking state."""
    paths = [Path(value) for value in (*FILE_ALLOWLIST, *EXTRA_CODE)]
    for directory in CODE_DIRS:
        paths.extend((ROOT / directory).rglob("*.py"))
    relative = sorted({path.relative_to(ROOT) if path.is_absolute() else path for path in paths})
    for path in relative:
        source = ROOT / path
        if not source.is_file() or source.is_symlink() or any(part.startswith("._") for part in path.parts):
            raise ValueError(f"missing or unsafe allowlisted file: {path}")
    return relative


def export(output: Path) -> dict:
    """Copy the allowlist to a new directory and write independent checksums."""
    target = output.expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"output already exists: {target}")
    if target == ROOT or ROOT in target.parents:
        raise ValueError("output must be outside the source worktree")
    files = public_files()
    target.mkdir(parents=True)
    checksums: list[str] = []
    for relative in files:
        source = ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        checksums.append(f"{digest}  {relative.as_posix()}")
    manifest = {
        "snapshot_id": SNAPSHOT_ID,
        "release_name": "Kei v1.1",
        "source_baseline": SOURCE_BASELINE,
        "source_note": "Independent curated copy of working-tree code; no verified kei-v1.1 tag",
        "files": [str(path) for path in files],
        "excluded": list(EXCLUDED),
        "integrity_note": "checksums.sha256 covers payload files only, not itself or PUBLIC_MANIFEST.json",
        "test_note": "Offline tests must be run separately against the exported tree; no inherited pass count is claimed.",
    }
    (target / "PUBLIC_MANIFEST.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target / "checksums.sha256").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new directory outside this repository")
    args = parser.parse_args()
    manifest = export(args.output)
    print(f"Exported {len(manifest['files'])} payload files to {args.output}")


if __name__ == "__main__":
    main()
