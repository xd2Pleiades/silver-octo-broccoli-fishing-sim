#!/usr/bin/env python3
"""Run the regression suite in bounded unittest shards for release hardening.

Usage:
  python tools/run_regression_shards_v13_2_13.py --scope focused
  python tools/run_regression_shards_v13_2_13.py --scope full --timeout 45

Each shard is a fresh process, so a slow/legacy module does not prevent later
shards from executing. The runner reports timeouts as inconclusive failures.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_DIR = ROOT / "fishing_sim" / "tests"
FOCUSED_LEGACY = {
    "test_v13_1_26_hud_health_tow",
    "test_v13_1_29_anchor_tow_controls",
    "test_v13_1_30_tow_persistence",
    "test_v13_1_31_tow_assistance",
    "test_v13_1_32_tow_escort",
    "test_v13_1_33_tow_placeholder_ship",
    "test_v13_1_34_merge_contracts",
    "test_v13v1_02_navigation_chart",
    "test_v13v1_15_marine_collisions",
}


def discover_modules(scope: str) -> list[str]:
    files = sorted(p.stem for p in TEST_DIR.glob("test_*.py"))
    if scope == "focused":
        files = [name for name in files if name.startswith("test_v13_2_") or name in FOCUSED_LEGACY]
    return ["fishing_sim.tests." + name for name in files]


def shard(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("focused", "full"), default="focused")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds per shard")
    parser.add_argument("--max-total-seconds", type=float, default=180.0,
                        help="whole-run time budget; 0 disables it")
    parser.add_argument("--log", type=Path, help="write progress and summary incrementally to this path")
    args = parser.parse_args()
    if args.batch_size < 1 or args.timeout <= 0 or args.max_total_seconds < 0:
        parser.error("batch-size and timeout must be positive; max-total-seconds must be >= 0")

    target = None
    if args.log:
        target = args.log if args.log.is_absolute() else ROOT / args.log
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")

    def emit(line: str = "") -> None:
        print(line, flush=True)
        if target:
            with target.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
                handle.flush()

    modules = discover_modules(args.scope)
    shards = shard(modules, args.batch_size)
    emit("Fishing Simulator v13.2.13 regression shard run")
    emit(f"Scope: {args.scope}")
    emit(f"Modules: {len(modules)}; shards: {len(shards)}; per-shard timeout: {args.timeout:.1f}s; "
         f"whole-run budget: {args.max_total_seconds:.1f}s (0=unlimited)")
    emit("")
    total_tests = total_pass = total_skip = failed_shards = timed_out = completed_shards = 0
    started_all = time.perf_counter()
    env = os.environ.copy()
    env.setdefault("PYTHONHASHSEED", "0")
    for idx, group in enumerate(shards, 1):
        elapsed_all = time.perf_counter() - started_all
        if args.max_total_seconds and elapsed_all >= args.max_total_seconds:
            emit(f"BUDGET STOP: {args.max_total_seconds:.1f}s whole-run limit reached; remaining shards not run.")
            failed_shards += len(shards) - idx + 1
            break
        label = f"shard {idx}/{len(shards)} ({len(group)} modules)"
        command = [sys.executable, "-m", "unittest", *group]
        start = time.perf_counter()
        try:
            result = subprocess.run(command, cwd=ROOT, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    timeout=args.timeout, check=False)
            elapsed = time.perf_counter() - start
            out = result.stdout or ""
            matches = re.findall(r"Ran (\d+) tests? in", out)
            n = int(matches[-1]) if matches else 0
            skip_match = re.search(r"skipped=(\d+)", out)
            skips = int(skip_match.group(1)) if skip_match else sum(
                int(v) for v in re.findall(r"\((\d+) skipped\)", out))
            total_tests += n
            total_skip += skips
            completed_shards += 1
            if result.returncode == 0:
                total_pass += n - skips
                emit(f"PASS {label}: {n} tests, {skips} skipped, {elapsed:.2f}s")
            else:
                failed_shards += 1
                emit(f"FAIL {label}: exit {result.returncode}, {n} tests parsed, {elapsed:.2f}s")
                emit("  output tail:")
                for line in out.splitlines()[-24:]:
                    emit("    " + line)
            emit("  modules: " + ", ".join(group))
        except subprocess.TimeoutExpired as exc:
            timed_out += 1
            failed_shards += 1
            elapsed = time.perf_counter() - start
            output = exc.stdout or ""
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            emit(f"TIMEOUT {label}: exceeded {args.timeout:.1f}s after {elapsed:.2f}s")
            emit("  modules: " + ", ".join(group))
            for line in str(output).splitlines()[-12:]:
                emit("  " + line)
        emit("")

    total_elapsed = time.perf_counter() - started_all
    emit(f"SUMMARY: {total_tests} tests parsed; {total_pass} passed; {total_skip} skipped;")
    emit(f"         {failed_shards} failing/timed-out/unrun shards ({timed_out} timeouts); "
         f"{completed_shards}/{len(shards)} shards completed in {total_elapsed:.2f}s.")
    return 1 if failed_shards else 0


if __name__ == "__main__":
    raise SystemExit(main())
