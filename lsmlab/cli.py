"""Command-line reproduction for the paired LSM simulation."""

from __future__ import annotations

import argparse
import sys

from .experiment import ExperimentConfig, run_experiment


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lsm-compaction-lab")
    parser.add_argument("--operations", type=_positive, default=10_000)
    parser.add_argument("--key-count", type=_positive, default=2_000)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--read-ratio", type=float, default=0.25)
    parser.add_argument("--phases", type=_positive, default=4)
    parser.add_argument("--memtable-bytes", type=_positive, default=32 * 1024)
    parser.add_argument("--background-bytes-per-tick", type=_positive, default=16 * 1024)
    parser.add_argument("--json", action="store_true")
    return parser


def _text(report) -> str:
    lines = [
        "policy    write_amp read_amp space_amp stalls backlog",
    ]
    for result in report.results:
        lines.append(
            f"{result.policy:9} {result.write_amplification:9.3f} "
            f"{result.read_amplification:8.3f} {result.peak_space_amplification:9.3f} "
            f"{result.stall_ticks:6d} {result.peak_backlog_bytes:7d}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run_experiment(
            ExperimentConfig(
                operations=args.operations,
                key_count=args.key_count,
                seed=args.seed,
                read_ratio=args.read_ratio,
                phases=args.phases,
                memtable_bytes=args.memtable_bytes,
                background_bytes_per_tick=args.background_bytes_per_tick,
            )
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(report.to_json() if args.json else _text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
