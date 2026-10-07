"""What turn_eval.py reports from a run's records: recall (spoke where it
should), false speak (spoke where it should not), per tag and engagement
mode, latency per model call, and the agent character's work gate."""

from __future__ import annotations

from typing import Any


def _rates(records: list[dict[str, Any]]) -> dict[str, Any]:
    speak = [r for r in records if r["expect"] == "speak"]
    silent = [r for r in records if r["expect"] == "silent"]
    either = [r for r in records if r["expect"] == "either"]

    def share(rows: list[dict[str, Any]]) -> float | None:
        return round(sum(r["spoke"] for r in rows) / len(rows), 4) if rows else None

    return {
        "n_speak": len(speak), "recall": share(speak),
        "n_silent": len(silent), "false_speak": share(silent),
        "n_either": len(either), "either_spoke": share(either),
    }


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 1)


def compute_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    tags = sorted({t for r in records for t in r["tags"]})
    calls = [r["latency_ms"] for r in records if r.get("gate") == "model"]
    spoken = [r["latency_ms"] for r in records if r.get("gate") == "model" and r["spoke"]]
    silent_calls = [r["latency_ms"] for r in records if r.get("gate") == "model" and not r["spoke"]]
    return {
        "overall": _rates(records),
        "by_engagement": {
            mode: _rates([r for r in records if r["engagement"] == mode])
            for mode in ("called", "active")
        },
        "by_tag": {tag: _rates([r for r in records if tag in r["tags"]]) for tag in tags},
        "latency_ms": {
            "model_calls": len(calls),
            "median": _percentile(calls, 0.5), "p90": _percentile(calls, 0.9),
            "spoke_median": _percentile(spoken, 0.5), "spoke_p90": _percentile(spoken, 0.9),
            "silent_median": _percentile(silent_calls, 0.5),
            "silent_p90": _percentile(silent_calls, 0.9),
        },
        "replies": sum(r["spoke"] for r in records),
        "decision_points": len(records),
        # Agent characters: the "is this the owner's work?" gate.
        "task_gate": {
            "owner_lines": len(asked := [r for r in records if "task_expected" in r]),
            "work_found": _share([r["task_said"] for r in asked if r["task_expected"]]),
            "talk_taken_as_work": _share([r["task_said"] for r in asked if not r["task_expected"]]),
        } if any("task_expected" in r for r in records) else None,
        "gates": {g: sum(r.get("gate") == g for r in records) for g in ("short", "rule", "model")},
    }


def _share(flags: list[bool]) -> float | None:
    return round(sum(flags) / len(flags), 3) if flags else None


def _pct(value: float | None) -> str:
    return "  -  " if value is None else f"{value * 100:5.1f}%"


def print_metrics(metrics: dict[str, Any], judge: dict[str, Any] | None = None) -> None:
    o = metrics["overall"]
    print(f"\ndecision points {metrics['decision_points']}  replies {metrics['replies']}  "
          f"gates {metrics['gates']}")
    print(f"recall {_pct(o['recall'])} (n={o['n_speak']})   false speak {_pct(o['false_speak'])} "
          f"(n={o['n_silent']})   either spoke {_pct(o['either_spoke'])} (n={o['n_either']})")
    print(f"{'':<18}{'recall':>8}{'n':>5}{'false':>9}{'n':>5}{'either':>9}{'n':>5}")
    rows = [(f"[{m}]", r) for m, r in metrics["by_engagement"].items()]
    rows += sorted(metrics["by_tag"].items())
    for name, r in rows:
        print(f"{name:<18}{_pct(r['recall']):>8}{r['n_speak']:>5}{_pct(r['false_speak']):>9}"
              f"{r['n_silent']:>5}{_pct(r['either_spoke']):>9}{r['n_either']:>5}")
    lat = metrics["latency_ms"]
    print(f"latency per model call: median {lat['median']} ms  p90 {lat['p90']} ms  "
          f"(calls {lat['model_calls']}; spoke median {lat['spoke_median']} / "
          f"silent median {lat['silent_median']})")
    if judge:
        print("judge: " + "  ".join(
            f"{k} {v:.2f}" if isinstance(v, float) else f"{k} {v}" for k, v in judge.items()
        ))
