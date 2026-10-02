from __future__ import annotations

import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts import setup_copilot
from silenttalk import agent_lease
from silenttalk.settings_store import SettingsStore


def test_setup_uses_settings_page_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "config.toml").write_text(
        '[copilot]\nstt_engine = "paraformer"\n', encoding="utf-8"
    )
    SettingsStore(tmp_path / "settings.json").save(
        {"copilot": {"stt_engine": "sensevoice"}}
    )
    monkeypatch.setattr(setup_copilot, "PROJECT_DIR", tmp_path)

    assert setup_copilot._copilot_section()["stt_engine"] == "sensevoice"


def test_runtime_check_verifies_lease_and_restores_service(monkeypatch):
    calls = []
    statuses = iter([None, {"mode": "base"}])
    monkeypatch.setattr(agent_lease, "service_status", lambda: next(statuses))
    monkeypatch.setattr(agent_lease, "ensure_service", lambda: {"mode": "base"})

    def post(path, payload, **kwargs):
        calls.append(path)
        if path == "/shutdown":
            return {"mode": "stopped"}
        return {"mode": "character", "owner_pid": payload["owner_pid"]}

    monkeypatch.setattr(agent_lease, "post_json", post)
    monkeypatch.setattr(
        agent_lease,
        "release_character",
        lambda owner: calls.append("release") or {"mode": "base"},
    )
    setup_copilot.check_runtime({})
    assert calls == ["/character", "release", "/shutdown"]


def test_runtime_check_does_not_steal_existing_lease(monkeypatch):
    monkeypatch.setattr(agent_lease, "service_status", lambda: {"mode": "character"})
    with pytest.raises(RuntimeError, match="already leased"):
        setup_copilot.check_runtime({})


def test_failed_runtime_check_releases_its_lease(monkeypatch):
    calls = []
    monkeypatch.setattr(agent_lease, "service_status", lambda: {"mode": "base"})
    monkeypatch.setattr(agent_lease, "ensure_service", lambda: {"mode": "base"})
    monkeypatch.setattr(
        agent_lease, "post_json", lambda *args, **kwargs: {"mode": "wrong"}
    )
    monkeypatch.setattr(
        agent_lease, "release_character", lambda owner: calls.append(owner)
    )
    with pytest.raises(RuntimeError, match="lease validation"):
        setup_copilot.check_runtime({})
    assert calls == [setup_copilot.os.getpid()]


def test_checksum_marker_does_not_hide_corrupted_speech_asset(tmp_path):
    import hashlib

    expected = hashlib.sha256(b"correct").hexdigest()
    asset = tmp_path / "model.onnx"
    asset.write_bytes(b"damaged")
    asset.with_suffix(".onnx.sha256").write_text(expected, encoding="ascii")
    assert not setup_copilot._is_ready(asset, expected, 1)
    assert asset.read_bytes() == b"damaged"


@pytest.mark.skipif(os.name != "nt", reason="Windows bootstrap")
@pytest.mark.parametrize("existing_version", [None, "2.0.0", "2.0.1"])
def test_bundled_edge_source_never_requires_github_login(tmp_path, existing_version):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    bootstrap = scripts / "bootstrap.ps1"
    bootstrap.write_bytes(
        (Path(__file__).parents[1] / "scripts/bootstrap.ps1").read_bytes()
    )
    cache = tmp_path / "cache"
    cache.mkdir()
    archive = cache / "edge-source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("scripts/bootstrap.ps1", "# installer fixture\n")
        bundle.writestr("pyproject.toml", 'version = "2.0.1"\n')
    (scripts / "edge-agent-distribution.json").write_text(
        json.dumps(
            {
                "repository": "invalid/never-used",
                "release": "fixture",
                "minimum_version": "2.0.1",
                "asset": archive.name,
                "sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        ),
        encoding="utf-8",
    )
    destination = tmp_path / "agent"
    if existing_version:
        (destination / "scripts").mkdir(parents=True)
        (destination / "scripts/bootstrap.ps1").write_text("# existing fixture")
        (destination / "pyproject.toml").write_text(f'version = "{existing_version}"\n')
        (destination / "user-asset").write_bytes(b"preserved fixture")
    expected = (
        destination.with_name("agent-fixture")
        if existing_version == "2.0.0"
        else destination
    )
    script = f"""
. '{bootstrap}' -Library
function Get-Command {{ throw 'GitHub command lookup must not occur for bundled sources' }}
$installer = Get-EdgeAgentInstaller '{destination}' '{cache}'
if (-not (Test-Path -LiteralPath $installer)) {{ throw 'Installer not extracted' }}
if ($installer -ne '{expected / "scripts/bootstrap.ps1"}'.Replace('/', '\')) {{ throw 'Wrong installation selected' }}
"""
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    if existing_version:
        assert (destination / "user-asset").read_bytes() == b"preserved fixture"


@pytest.mark.skipif(os.name != "nt", reason="Windows bootstrap")
def test_ready_deployment_skips_installer_and_check_forces_it(tmp_path):
    bootstrap = Path(__file__).parents[1] / "scripts/bootstrap.ps1"
    script = f"""
. '{bootstrap}' -Library
function Test-DeploymentReady {{ return $true }}
$global:forceInstall = $false
function Get-EdgeAgentInstaller {{
    if ($global:forceInstall) {{ throw 'INSTALL_REQUIRED' }}
    return '{tmp_path.parent / "agent/scripts/bootstrap.ps1"}'
}}
Install-SilentTalk '{tmp_path}' '{tmp_path.parent / "agent"}' $false
$global:forceInstall = $true
try {{ Install-SilentTalk '{tmp_path}' '{tmp_path.parent / "agent"}' $true; throw 'Check skipped' }}
catch {{ if ($_.Exception.Message -ne 'INSTALL_REQUIRED') {{ throw }} }}
exit 0
"""
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")


@pytest.mark.skipif(os.name != "nt", reason="Windows bootstrap")
def test_deployment_receipt_must_match_current_components(tmp_path):
    bootstrap = Path(__file__).parents[1] / "scripts/bootstrap.ps1"
    (tmp_path / ".runtime").mkdir()
    (tmp_path / ".runtime/deployment-complete").write_text("current", encoding="utf-8")
    script = f"""
. '{bootstrap}' -Library
$global:fixtureState = 'current'
function Get-DeploymentState {{ return $global:fixtureState }}
if (-not (Test-DeploymentReady '{tmp_path}' 'agent')) {{ throw 'Valid receipt rejected' }}
$global:fixtureState = 'changed'
if (Test-DeploymentReady '{tmp_path}' 'agent') {{ throw 'Stale receipt accepted' }}
$global:fixtureState = $null
if (Test-DeploymentReady '{tmp_path}' 'agent') {{ throw 'Missing component accepted' }}
"""
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
