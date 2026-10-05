"""Publish a Windows release that players download without a GitHub account.

Run on the dev box once the laptop's report shows the current commits of
both repositories pass on Windows. It packs EdgeAgent's source (EdgeAgent's
own scripts/package_source.py), puts a new archive on a private EdgeAgent
release for installs from the repository, records it in
scripts/edge-agent-distribution.json (committed and pushed), builds the
player ZIP from that commit (package_windows.py), publishes it on the public
download page and downloads it back anonymously to check it.

    python scripts/release_windows.py --edge-agent ../EdgeAgent --notes notes.md            # dry run
    python scripts/release_windows.py --edge-agent ../EdgeAgent --notes notes.md --publish

`notes.md` says what was verified on Windows (from the laptop's report); the
script adds the commits and the SHA256. A dry run builds both archives into
--out and changes nothing else.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from scripts import package_windows

PUBLIC = "nobody945946/SilentTalk-download"
MANIFEST = PROJECT / "scripts" / "edge-agent-distribution.json"


def _run(*command: str, cwd: Path = PROJECT) -> str:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True, check=True, timeout=600).stdout.strip()


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def next_edge_release(manifest: dict[str, str], version: str, sha256: str) -> dict[str, str] | None:
    """The manifest for a new EdgeAgent archive, or None when the archive is
    the one already released. A changed archive needs a newer version, so an
    installed older EdgeAgent is replaced."""
    if sha256 == manifest["sha256"]:
        return None
    if _version(version) <= _version(manifest["minimum_version"]):
        raise SystemExit(
            f"EdgeAgent changed since {manifest['release']} but its version is still {version}: "
            "raise the version in EdgeAgent's pyproject.toml first")
    number = int(re.fullmatch(r"edge-agent-windows-source-v(\d+)\.zip", manifest["asset"]).group(1)) + 1
    return {**manifest, "minimum_version": version, "release": f"bootstrap-v{number}",
            "asset": f"edge-agent-windows-source-v{number}.zip", "sha256": sha256}


def _clean_and_pushed(repo: Path) -> str:
    if _run("git", "status", "--porcelain", cwd=repo):
        raise SystemExit(f"{repo} has uncommitted changes")
    head = _run("git", "rev-parse", "HEAD", cwd=repo)
    _run("git", "fetch", "-q", "origin", cwd=repo)
    if _run("git", "rev-parse", "@{u}", cwd=repo) != head:
        raise SystemExit(f"{repo} is not the same as its pushed branch")
    return head


def _tag() -> str:
    base = time.strftime("windows-%Y.%m.%d")
    existing = set(_run("gh", "release", "list", "--repo", PUBLIC, "--limit", "100",
                        "--json", "tagName", "-q", ".[].tagName").splitlines())
    tag, n = base, 1
    while tag in existing:
        n += 1
        tag = f"{base}.{n}"
    return tag


def _check_download(tag: str, name: str, sha256: str) -> None:
    url = f"https://github.com/{PUBLIC}/releases/download/{tag}/{name}"
    for _ in range(30):  # a new asset takes a moment to be served
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                if hashlib.sha256(response.read()).hexdigest() == sha256:
                    return
        except OSError:
            pass
        time.sleep(5)
    raise SystemExit(f"the public download does not match: {url}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--edge-agent", type=Path, required=True, help="the EdgeAgent repository")
    parser.add_argument("--notes", type=Path, required=True, help="what was verified on Windows")
    parser.add_argument("--out", type=Path, default=PROJECT / ".runtime" / "release")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    edge = args.edge_agent.resolve()
    notes = args.notes.read_text(encoding="utf-8").strip()
    if args.publish:
        silent_head, edge_head = _clean_and_pushed(PROJECT), _clean_and_pushed(edge)
    else:
        silent_head, edge_head = _run("git", "rev-parse", "HEAD"), _run("git", "rev-parse", "HEAD", cwd=edge)
    args.out.mkdir(parents=True, exist_ok=True)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    version = re.search(r'(?m)^version\s*=\s*"([\d.]+)"', (edge / "pyproject.toml").read_text(encoding="utf-8")).group(1)
    with tempfile.TemporaryDirectory() as tmp:
        packed = json.loads(_run(sys.executable, "scripts/package_source.py", "--output", f"{tmp}/edge.zip", cwd=edge))
        new = next_edge_release(manifest, version, packed["sha256"])
        current = new or manifest
        edge_zip = args.out / current["asset"]
        edge_zip.write_bytes(Path(f"{tmp}/edge.zip").read_bytes())

    if args.publish and new is not None:
        _run("gh", "release", "create", new["release"], str(edge_zip), "--repo", new["repository"],
             "--target", edge_head, "--title", f"EdgeAgent {version} Windows source",
             "--notes", f"EdgeAgent `{edge_head}`, bundled by SilentTalk's Windows download.")
        MANIFEST.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")
        _run("git", "add", str(MANIFEST))
        _run("git", "commit", "-q", "-m", f"Windows release: EdgeAgent {version} ({new['release']})")
        _run("git", "push", "-q", "origin", "HEAD")
        silent_head = _run("git", "rev-parse", "HEAD")

    tag = _tag() if args.publish else time.strftime("windows-%Y.%m.%d")
    player = args.out / f"silenttalk-{tag}.zip"
    built = package_windows.build(edge_zip, player, manifest=None if args.publish else current)
    body = (f"下載 `{player.name}`，解壓後雙擊 `啟動 SilentTalk.cmd`。第一次啟動需要網路，約下載 7–8 GB；"
            "EdgeAgent 已包在 ZIP 裡，不需要 GitHub 帳號。ZIP 裡沒有任何 LoRA、個人設定、帳號資料、角色狀態、模型權重或對話紀錄。\n\n"
            f"{notes}\n\nSilentTalk `{silent_head}`；EdgeAgent `{edge_head}`（{version}）。\n\n"
            f"SHA256：`{built['sha256']}`")
    (args.out / f"{tag}-notes.md").write_text(body + "\n", encoding="utf-8")
    if args.publish:
        _run("gh", "release", "create", tag, str(player), "--repo", PUBLIC,
             "--title", f"SilentTalk Windows {tag.removeprefix('windows-').replace('.', '-', 2)}（含 EdgeAgent）",
             "--notes-file", str(args.out / f"{tag}-notes.md"))
        _check_download(tag, player.name, built["sha256"])
    print(json.dumps({"published": args.publish, "tag": tag, "player_zip": str(player), "player_sha256": built["sha256"],
                      "edge_release": (new or manifest)["release"], "edge_new": new is not None,
                      "silenttalk": silent_head, "edgeagent": edge_head}, ensure_ascii=False))


if __name__ == "__main__":
    main()
