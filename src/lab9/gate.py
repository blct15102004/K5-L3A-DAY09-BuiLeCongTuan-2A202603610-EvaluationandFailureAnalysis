"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []

    # 1. NaN or inf in metrics
    for k, v in (pr.get("metrics") or {}).items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            if math.isnan(v) or math.isinf(v):
                problems.append(f"metric {k} is {v}")

    # 2. Row count vs manifest items x seeds, and duplicates
    rows = pr.get("rows") or []
    manifest = pr.get("manifest") or {}
    expected_len = int(manifest.get("items", 0)) * len(manifest.get("seeds") or [])
    if len(rows) != expected_len:
        problems.append(f"row count {len(rows)} != manifest {expected_len}")

    pr_keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    pr_key_set = set(pr_keys)
    if len(pr_key_set) != len(rows):
        problems.append("duplicate (item_id, seed) rows in PR")

    # 3. (item_id, seed) set matches baseline
    base_rows = base.get("rows") or []
    base_key_set = {(r.get("item_id"), r.get("seed")) for r in base_rows}
    if pr_key_set != base_key_set:
        problems.append("(item_id, seed) set differs from baseline")

    # 4. evaluator_failures non-empty or None value for a graded spec metric
    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures non-empty ({len(pr['evaluator_failures'])})")
    graded_ids = [m["id"] for m in (spec.get("metrics") or []) if m["id"] in GRADERS]
    for r in rows:
        for mid in graded_ids:
            if r.get(mid) is None:
                problems.append(f"missing/None value for {mid} on {r.get('item_id')}@{r.get('seed')}")
                break

    # 5. Slice tags in PR rows match baseline
    base_slices = {(r.get("item_id"), r.get("seed")): sorted(r.get("slices") or []) for r in base_rows}
    for r in rows:
        key = (r.get("item_id"), r.get("seed"))
        if key in base_slices and sorted(r.get("slices") or []) != base_slices[key]:
            problems.append(f"slice tags differ from baseline on {r.get('item_id')}@{r.get('seed')}")
            break

    # 6. Ratchet check when base_spec is given for the same eval-set version
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        spec_metrics = {m["id"]: m for m in (spec.get("metrics") or [])}
        for bm in (base_spec.get("metrics") or []):
            mid = bm["id"]
            if mid not in spec_metrics:
                problems.append(f"ratchet: metric {mid} removed")
                continue
            sm = spec_metrics[mid]
            if bm.get("blocking") and not sm.get("blocking"):
                problems.append(f"ratchet: metric {mid} became non-blocking")
            bth = bm.get("threshold") or {}
            sth = sm.get("threshold") or {}
            if "max" in bth and ("max" not in sth or sth["max"] > bth["max"]):
                problems.append(f"ratchet: {mid} max threshold loosened")
            if "min" in bth and ("min" not in sth or sth["min"] < bth["min"]):
                problems.append(f"ratchet: {mid} min threshold loosened")
            if "max_increase" in bth and ("max_increase" not in sth or sth["max_increase"] > bth["max_increase"]):
                problems.append(f"ratchet: {mid} max_increase loosened")
            if bth.get("no_significant_drop") and not sth.get("no_significant_drop"):
                problems.append(f"ratchet: {mid} dropped no_significant_drop")

        spec_slices = {(s["name"], s["metric"]): s for s in (spec.get("slices") or [])}
        for bs in (base_spec.get("slices") or []):
            skey = (bs["name"], bs["metric"])
            if skey not in spec_slices:
                problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} removed")
                continue
            ss = spec_slices[skey]
            if bs.get("blocking") and not ss.get("blocking"):
                problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} became non-blocking")
            if "min" in bs and ("min" not in ss or ss["min"] < bs["min"]):
                problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} min loosened")
            if bs.get("no_significant_drop") and not ss.get("no_significant_drop"):
                problems.append(f"ratchet: slice {bs['name']}/{bs['metric']} dropped no_significant_drop")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice."""
    blocked: list[str] = []
    lines: list[str] = []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, mid = sl["name"], sl["metric"]
        a = per_item(pr, mid, slice_name=name)
        b = per_item(base, mid, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "min" in sl and val < sl["min"]:
            verdict = "fail"
        if sl.get("no_significant_drop") and val is not None:
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys],
                    [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        sid = f"slice:{name}/{mid}"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        lines.append(f"  {sid:<22} {val!s:<8} min={str(sl.get('min', '-')):<36} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
