"""Stamp an Agent adapter's measured sampling on its GGUF file.

EdgeAgent reads `edgeagent.sampling.off.temp` and
`edgeagent.sampling.thinking.temp` from the Agent adapter it loads
(edge_agent/models.py SAMPLING) and samples that adapter's requests at them;
an adapter without them samples at the base model's 0.2. The values are the
temperatures that did best in the bench for each mode: two adapters trained
on the same rows did best at opposite temperatures (2026-10-10), so each
adapter carries its own.

    PYTHONPATH=.runtime/tools/llama.cpp-b11179/gguf-py .runtime/train-venv/bin/python \\
        scripts/dev/stamp_adapter_sampling.py .runtime/models/llm/machine-spirit-fw3.q8_0.gguf --off 0.2 --thinking 1.0
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import gguf
from gguf.scripts.gguf_new_metadata import MetadataDetails, copy_with_new_metadata

KEY = "edgeagent.sampling.{mode}.temp"


def stamp(adapter: Path, off: float, thinking: float) -> None:
    reader = gguf.GGUFReader(adapter, "r")
    if reader.get_field("adapter.type") is None:
        raise SystemExit(f"{adapter} is not an adapter")
    architecture = reader.get_field(gguf.Keys.General.ARCHITECTURE).contents()
    work = adapter.with_name(adapter.name + ".stamping")
    writer = gguf.GGUFWriter(work, arch=architecture, endianess=reader.endianess)
    copy_with_new_metadata(reader, writer, {
        KEY.format(mode=mode): MetadataDetails(gguf.GGUFValueType.FLOAT32, value)
        for mode, value in (("off", off), ("thinking", thinking))}, [])
    del reader  # the memory map, before the file is replaced
    os.replace(work, adapter)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("adapter", type=Path)
    parser.add_argument("--off", type=float, required=True, help="temperature with thinking off")
    parser.add_argument("--thinking", type=float, required=True, help="temperature with thinking on")
    args = parser.parse_args()
    stamp(args.adapter, args.off, args.thinking)
    print(f"{args.adapter}: off {args.off}, thinking {args.thinking}")


if __name__ == "__main__":
    main()
