#!/usr/bin/env python3
"""
A4 — silent-failure lint for critical paths.

Flags exception handlers that SILENTLY swallow exceptions in the directories
where a swallowed error can corrupt real-money state or hide a failure:

    src/risk        — sizing, caps, validation
    src/execution   — order placement / close
    src/core        — trading scheduler, monitoring, order monitor

A handler is "silent" when its body is exactly `pass`, or its only statement is
`logger.debug(...)` / `log.debug(...)`, AND it does not re-raise. Those are the
patterns that hid the DELL-orphan order-write failure and the last_signal_at
telemetry gap — the error happened, nothing was logged at ERROR, nobody knew.

Benign handlers (genuinely safe to ignore — e.g. best-effort analytics) can be
marked with a trailing `# silent-ok` comment on the `except` line to suppress.

Usage:
    python scripts/check_silent_excepts.py            # report only (exit 0)
    python scripts/check_silent_excepts.py --ci       # exit 1 if any unmarked

Intended for CI on the critical dirs and for periodic manual audit.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

CRITICAL_DIRS = ["src/risk", "src/execution", "src/core"]


def _is_debug_call(node: ast.stmt) -> bool:
    """True if stmt is a bare logger.debug(...) / log.debug(...) call."""
    if not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call):
        return False
    func = node.value.func
    return isinstance(func, ast.Attribute) and func.attr == "debug"


def _body_reraises(body: list[ast.stmt]) -> bool:
    """True if any statement in the handler body re-raises."""
    for n in ast.walk(ast.Module(body=body, type_ignores=[])):
        if isinstance(n, ast.Raise):
            return True
    return False


def _is_silent(handler: ast.ExceptHandler) -> bool:
    # Only `pass`
    if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
        return True
    # Only logger.debug(...) and no re-raise
    if (
        len(handler.body) == 1
        and _is_debug_call(handler.body[0])
        and not _body_reraises(handler.body)
    ):
        return True
    return False


def scan_file(path: Path) -> list[tuple[int, str]]:
    src = path.read_text(encoding="utf-8", errors="replace")
    lines = src.splitlines()
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and _is_silent(node):
            lineno = node.lineno
            except_line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
            if "# silent-ok" in except_line:
                continue
            kind = "pass" if (len(node.body) == 1 and isinstance(node.body[0], ast.Pass)) else "logger.debug"
            hits.append((lineno, f"{except_line.strip()}  →  swallows via {kind}"))
    return hits


def main() -> int:
    ci = "--ci" in sys.argv
    repo = Path(__file__).resolve().parent.parent
    total = 0
    for d in CRITICAL_DIRS:
        for py in sorted((repo / d).rglob("*.py")):
            for lineno, desc in scan_file(py):
                total += 1
                rel = py.relative_to(repo)
                print(f"{rel}:{lineno}: {desc}")
    print(f"\n{total} silent exception handler(s) in critical paths "
          f"({', '.join(CRITICAL_DIRS)}). Mark reviewed-benign ones with '# silent-ok'.")
    if ci and total:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
