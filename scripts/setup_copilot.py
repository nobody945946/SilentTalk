from __future__ import annotations

import hashlib
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_DIR / ".runtime"
ASR_DIR = RUNTIME_DIR / "models" / "asr"
LLM_DIR = RUNTIME_DIR / "models" / "llm"

ASSETS = (
    (
        "ASR encoder INT8",
        "https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en/resolve/main/encoder.int8.onnx?download=true",
        ASR_DIR / "encoder.int8.onnx",
        "81a70226a8934e6ed92aa1d4fc486b428b5398e2f2619ed4897b7294cab90e9a",
        150_000_000,
    ),
    (
        "ASR decoder INT8",
        "https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en/resolve/main/decoder.int8.onnx?download=true",
        ASR_DIR / "decoder.int8.onnx",
        "f3cca9f77bb9d93c8fcbfb63ae617b6b1ee96818df3aa3b151c40658fe38594f",
        65_000_000,
    ),
    (
        "ASR tokens",
        "https://huggingface.co/csukuangfj/sherpa-onnx-streaming-paraformer-bilingual-zh-en/resolve/main/tokens.txt?download=true",
        ASR_DIR / "tokens.txt",
        None,
        50_000,
    ),
    (
        "Qwen3-0.6B Q4_K_M",
        "https://huggingface.co/QuantFactory/Qwen3-0.6B-GGUF/resolve/main/Qwen3-0.6B.Q4_K_M.gguf?download=true",
        LLM_DIR / "Qwen3-0.6B.Q4_K_M.gguf",
        "7af3fdf842f87b24672f8a7f1dd50404043f0bfb71093ff91c31d2b49df4631d",
        450_000_000,
    ),
)


def _copilot_enabled() -> bool:
    config_path = PROJECT_DIR / "config.toml"
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    section = raw.get("copilot", {})
    return bool(section.get("enabled", True)) if isinstance(section, dict) else True


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(4 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _is_ready(path: Path, expected_sha256: str | None, min_size: int) -> bool:
    if not path.is_file() or path.stat().st_size < min_size:
        return False
    if expected_sha256 is None:
        return True

    marker = path.with_name(path.name + ".sha256")
    if marker.is_file() and marker.read_text(encoding="ascii").strip() == expected_sha256:
        return True

    actual = _sha256(path)
    if actual != expected_sha256:
        print(f"Existing {path.name} failed SHA256; downloading a clean copy.")
        path.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)
        return False

    marker.write_text(expected_sha256 + "\n", encoding="ascii")
    return True


def _download(
    label: str,
    url: str,
    path: Path,
    expected_sha256: str | None,
    min_size: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if _is_ready(path, expected_sha256, min_size):
        print(f"[OK] {label}")
        return

    temp = path.with_name(path.name + ".part")
    temp.unlink(missing_ok=True)
    marker = path.with_name(path.name + ".sha256")
    marker.unlink(missing_ok=True)

    print(f"Downloading {label}...")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SilentTalk/1.0"},
    )
    digest = hashlib.sha256()
    received = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response, temp.open("wb") as out:
            total = int(response.headers.get("Content-Length", "0") or "0")
            last_percent = -1
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                digest.update(chunk)
                received += len(chunk)
                if total:
                    percent = int(received * 100 / total)
                    if percent >= last_percent + 5:
                        print(f"  {percent:3d}%")
                        last_percent = percent
    except (OSError, urllib.error.URLError) as exc:
        temp.unlink(missing_ok=True)
        raise RuntimeError(f"{label} download failed: {exc}") from exc

    if received < min_size:
        temp.unlink(missing_ok=True)
        raise RuntimeError(
            f"{label} download is unexpectedly small ({received} bytes)."
        )

    actual_sha256 = digest.hexdigest()
    if expected_sha256 is not None and actual_sha256 != expected_sha256:
        temp.unlink(missing_ok=True)
        raise RuntimeError(
            f"{label} SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    temp.replace(path)
    if expected_sha256 is not None:
        marker.write_text(expected_sha256 + "\n", encoding="ascii")
    print(f"[OK] {label}")


def main() -> int:
    if not _copilot_enabled():
        print("Copilot is disabled in config.toml; model deployment skipped.")
        return 0

    print("Checking SilentTalk Copilot models...")
    try:
        for asset in ASSETS:
            _download(*asset)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("SilentTalk Copilot models are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
