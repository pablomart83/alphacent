#!/usr/bin/env python3
"""
Sprint 4.2 — Cull Low-Activation Templates

Reads config/.proposal_tracker.json and reports templates that have been
proposed enough times but have a low activation rate. Optionally writes
the culled names to config/.disabled_templates.json.

Usage:
    # Dry-run (report only, no changes):
    python3 scripts/utilities/cull_low_activation_templates.py

    # Apply: write culled templates to .disabled_templates.json
    python3 scripts/utilities/cull_low_activation_templates.py --apply

    # Custom thresholds:
    python3 scripts/utilities/cull_low_activation_templates.py --min-proposed 20 --max-activation-rate 0.10 --apply

The existing _is_template_disabled() check in strategy_proposer.py reads
.disabled_templates.json and skips those templates automatically.
"""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Cull low-activation templates")
    parser.add_argument("--min-proposed", type=int, default=20,
                        help="Minimum proposals before a template is eligible for culling (default: 20)")
    parser.add_argument("--max-activation-rate", type=float, default=0.10,
                        help="Maximum activation rate (approved/proposed) to be culled (default: 0.10 = 10%%)")
    parser.add_argument("--apply", action="store_true",
                        help="Write culled templates to .disabled_templates.json (default: dry-run)")
    args = parser.parse_args()

    tracker_path = Path("config/.proposal_tracker.json")
    disabled_path = Path("config/.disabled_templates.json")

    if not tracker_path.exists():
        print(f"ERROR: {tracker_path} not found. Run the autonomous cycle first to populate it.")
        return

    with open(tracker_path) as f:
        tracker: dict = json.load(f)

    # Load existing disabled set
    existing_disabled: set = set()
    if disabled_path.exists():
        try:
            with open(disabled_path) as f:
                existing_disabled = set(json.load(f))
        except Exception:
            pass

    # Evaluate each template
    to_cull: list[str] = []
    report_rows: list[tuple] = []

    for template_name, counts in tracker.items():
        proposed = counts.get("proposed", 0)
        approved = counts.get("approved", 0)

        if proposed < args.min_proposed:
            continue  # Not enough data

        activation_rate = approved / proposed if proposed > 0 else 0.0

        if activation_rate < args.max_activation_rate:
            to_cull.append(template_name)
            report_rows.append((template_name, proposed, approved, activation_rate))

    # Sort by activation rate ascending (worst first)
    report_rows.sort(key=lambda r: r[3])

    print(f"\n{'='*70}")
    print(f"Low-Activation Template Report")
    print(f"Thresholds: min_proposed={args.min_proposed}, max_activation_rate={args.max_activation_rate:.0%}")
    print(f"{'='*70}")
    print(f"{'Template':<50} {'Proposed':>8} {'Approved':>8} {'Rate':>8}")
    print(f"{'-'*70}")
    for name, proposed, approved, rate in report_rows:
        already = " [already disabled]" if name in existing_disabled else ""
        print(f"{name:<50} {proposed:>8} {approved:>8} {rate:>7.1%}{already}")

    new_to_cull = [n for n in to_cull if n not in existing_disabled]
    print(f"\nTotal eligible for culling: {len(to_cull)}")
    print(f"Already disabled: {len(to_cull) - len(new_to_cull)}")
    print(f"New to disable: {len(new_to_cull)}")

    if not args.apply:
        print("\nDry-run mode — no changes made. Use --apply to write to .disabled_templates.json")
        return

    if not new_to_cull:
        print("\nNothing new to disable.")
        return

    updated_disabled = sorted(existing_disabled | set(to_cull))
    with open(disabled_path, "w") as f:
        json.dump(updated_disabled, f, indent=2)

    print(f"\nWrote {len(updated_disabled)} disabled templates to {disabled_path}")
    print("Restart the backend for changes to take effect.")


if __name__ == "__main__":
    main()
