from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from scripts import package_windows


@pytest.fixture
def distribution(tmp_path, monkeypatch):
    def sources(extra=None):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("scripts/bootstrap.ps1", "# fixture")
            if extra:
                archive.writestr(extra, "private fixture")
        return data.getvalue()

    edge = tmp_path / "edge.zip"
    edge.write_bytes(sources())
    manifest = {
        "asset": "edge.zip",
        "sha256": hashlib.sha256(edge.read_bytes()).hexdigest(),
    }
    files = {name: b"source fixture" for name in package_windows.APPLICATION_FILES}
    files["scripts/edge-agent-distribution.json"] = json.dumps(manifest).encode()
    files["silenttalk/__init__.py"] = b""
    for name in [
        ".env",
        "settings.json",
        "models/private.gguf",
        "tests/test_example.py",
    ]:
        files[name] = b"excluded fixture"

    def git(project, *arguments):
        if arguments[0] == "rev-parse":
            return b"a" * 40
        if arguments[0] == "ls-tree":
            return "\n".join(files).encode()
        return files[arguments[1].split(":", 1)[1]]

    monkeypatch.setattr(package_windows, "_git", git)
    return edge, tmp_path / "player.zip", manifest, files, sources


def test_player_package_only_contains_application_and_verified_dependency(distribution):
    edge, output, _, _, _ = distribution
    result = package_windows.build(edge, output)
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
        assert "SilentTalk/啟動 SilentTalk.cmd" in names
        assert (
            archive.read("SilentTalk/.runtime/downloads/edge.zip") == edge.read_bytes()
        )
        assert "SilentTalk/silenttalk/__init__.py" in names
        assert not any("fixture" in name or "private" in name for name in names)
        assert "SilentTalk/.env" not in names
        assert "SilentTalk/settings.json" not in names
        assert "SilentTalk/tests/test_example.py" not in names
    assert result["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "entry", ["models/private.gguf", "../escaped.py", "settings.json"]
)
def test_unsafe_or_personal_dependency_never_replaces_player_package(
    distribution, entry
):
    edge, output, manifest, files, sources = distribution
    edge.write_bytes(sources(entry))
    manifest["sha256"] = hashlib.sha256(edge.read_bytes()).hexdigest()
    files["scripts/edge-agent-distribution.json"] = json.dumps(manifest).encode()
    output.write_bytes(b"previous verified package")
    with pytest.raises(ValueError, match="safe sources"):
        package_windows.build(edge, output)
    assert output.read_bytes() == b"previous verified package"


def test_unverified_dependency_is_rejected_before_package_creation(distribution):
    edge, output, _, _, _ = distribution
    edge.write_bytes(b"corrupt archive")
    with pytest.raises(ValueError, match="SHA256"):
        package_windows.build(edge, output)
    assert not output.exists()
