"""Build the Windows player distribution from committed application sources."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from silenttalk.config import BUNDLED_ADAPTERS

APPLICATION_FILES = {
    "app.py",
    "config.toml",
    "requirements.txt",
    "README.md",
    "ARCHITECTURE.md",
    "LICENSE",
    "啟動 SilentTalk.cmd",
    "scripts/bootstrap.ps1",
    "scripts/setup_copilot.py",
    "scripts/restart_silenttalk.ps1",
    "scripts/edge-agent-distribution.json",
}
PRIVATE_NAMES = {".env", "settings.json", "personas.json", "character_state.json"}
# The one model file EdgeAgent's source may carry: the adapter it ships for the
# default E4B (edge_agent/adapters/, its deploy checks the SHA256), which the
# lease names too. Any other weights stay out.
SHIPPED_ADAPTERS = {f"edge_agent/adapters/{name}" for name, _ in BUNDLED_ADAPTERS.values()}


def _git(project: Path, *arguments: str) -> bytes:
    return subprocess.run(
        ["git", "-c", "core.quotepath=false", *arguments],
        cwd=project,
        capture_output=True,
        check=True,
        timeout=30,
    ).stdout


def build(
    edge_source: Path,
    output: Path,
    *,
    project: Path = PROJECT,
    revision: str = "HEAD",
    manifest: dict[str, str] | None = None,
) -> dict[str, str | int]:
    """`manifest`: the EdgeAgent manifest to package instead of the
    committed one (a release's dry run, before the new one is committed)."""
    commit = (
        _git(project, "rev-parse", "--verify", f"{revision}^{{commit}}")
        .decode()
        .strip()
    )
    manifest_path = "scripts/edge-agent-distribution.json"
    override = manifest is not None
    if manifest is None:
        manifest = json.loads(_git(project, "show", f"{commit}:{manifest_path}"))
    source = edge_source.read_bytes()
    if hashlib.sha256(source).hexdigest() != manifest["sha256"]:
        raise ValueError("EdgeAgent source SHA256 mismatch")
    asset = manifest["asset"]
    if PurePosixPath(asset).name != asset or "\\" in asset:
        raise ValueError("Unsafe EdgeAgent asset name")
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        if "scripts/bootstrap.ps1" not in archive.namelist():
            raise ValueError("EdgeAgent installer missing")
        for entry in archive.infolist():
            path = PurePosixPath(entry.filename)
            if (
                path.is_absolute()
                or ".." in path.parts
                or "\\" in entry.filename
                or ":" in entry.filename
                or path.name in PRIVATE_NAMES
                or (path.suffix.lower() in {".gguf", ".safetensors", ".onnx", ".wav"}
                    and entry.filename not in SHIPPED_ADAPTERS)
                or ".runtime" in path.parts
                or (entry.external_attr >> 16) & 0o170000 == 0o120000
            ):
                raise ValueError(
                    "EdgeAgent distribution must contain safe sources only"
                )
        bad = archive.testzip()
        if bad:
            raise ValueError(f"Corrupt EdgeAgent archive entry: {bad}")
    tracked = (
        _git(project, "ls-tree", "-r", "--name-only", commit).decode().splitlines()
    )
    paths = sorted(
        name
        for name in tracked
        if name in APPLICATION_FILES
        or (name.startswith("silenttalk/") and name.endswith(".py"))
        # Data the code reads (the homophone table for calling the character).
        or name.startswith("silenttalk/copilot/data/")
    )
    if not APPLICATION_FILES.issubset(paths):
        raise ValueError("Application deployment sources are incomplete")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".part")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in paths:
            content = (
                (json.dumps(manifest, indent=2) + "\n").encode()
                if override and name == manifest_path
                else _git(project, "show", f"{commit}:{name}")
            )
            archive.writestr("SilentTalk/" + name, content)
        archive.writestr("SilentTalk/.runtime/downloads/" + asset, source)
    temporary.replace(output)
    return {
        "commit": commit,
        "files": len(paths) + 1,
        "bytes": output.stat().st_size,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edge-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", default="HEAD")
    args = parser.parse_args()
    print(json.dumps(build(args.edge_source, args.output, revision=args.revision)))


if __name__ == "__main__":
    main()
