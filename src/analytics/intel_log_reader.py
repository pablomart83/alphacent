"""Log rotation-aware reader for the Intel analyst.

Handles the EC2 log rotation scheme:
  alphacent.log        (current)
  alphacent.log.1      (previous)
  alphacent.log.2      ...
  alphacent.log.N      (oldest, up to .100)

Each file is max 10MB. Newer content is in lower-numbered files.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

LOG_DIR = "/home/ubuntu/alphacent/logs"

# Log files the analyst cares about (base names without rotation suffix)
_KNOWN_LOGS = [
    "alphacent.log",
    "errors.log",
    "strategy.log",
    "cycles/cycle_history.log",
]


class IntelLogReader:
    """Read log files within a lookback window, handling rotation transparently."""

    def __init__(self, log_dir: str = LOG_DIR):
        self.log_dir = log_dir

    # ── Public API ────────────────────────────────────────────────────────────

    def read_lines(
        self,
        log_name: str,
        lookback_days: int,
        pattern: Optional[str] = None,
    ) -> List[str]:
        """Return lines from log_name + all rotated versions within the lookback window.

        Lines are returned in chronological order (oldest first).
        Pattern: optional substring filter applied per line.
        """
        cutoff = datetime.now() - timedelta(days=lookback_days)
        files = self._get_rotated_files(log_name, cutoff)

        lines: List[str] = []
        for path in reversed(files):  # oldest first
            try:
                with open(path, "r", errors="replace") as fh:
                    for line in fh:
                        line = line.rstrip()
                        if pattern and pattern not in line:
                            continue
                        ts = self._parse_timestamp(line)
                        if ts and ts < cutoff:
                            continue
                        lines.append(line)
            except (IOError, PermissionError) as exc:
                logger.debug(f"IntelLogReader: cannot read {path}: {exc}")
                continue

        return lines

    def grep_logs(
        self,
        pattern: str,
        lookback_days: int,
        log_names: Optional[List[str]] = None,
    ) -> List[Dict]:
        """Search across log files for pattern within the lookback window.

        Returns list of {file, line_number, timestamp, text} sorted by timestamp.
        """
        if log_names is None:
            log_names = _KNOWN_LOGS

        results: List[Dict] = []
        for log_name in log_names:
            cutoff = datetime.now() - timedelta(days=lookback_days)
            files = self._get_rotated_files(log_name, cutoff)
            for path in reversed(files):
                try:
                    with open(path, "r", errors="replace") as fh:
                        for lineno, line in enumerate(fh, 1):
                            if pattern not in line:
                                continue
                            line = line.rstrip()
                            ts = self._parse_timestamp(line)
                            if ts and ts < cutoff:
                                continue
                            results.append(
                                {
                                    "file": os.path.basename(path),
                                    "line_number": lineno,
                                    "timestamp": ts.isoformat() if ts else None,
                                    "text": line,
                                }
                            )
                except (IOError, PermissionError) as exc:
                    logger.debug(f"IntelLogReader.grep_logs: cannot read {path}: {exc}")
                    continue

        results.sort(key=lambda r: r["timestamp"] or "")
        return results

    def count_pattern(
        self,
        pattern: str,
        lookback_days: int,
        log_names: Optional[List[str]] = None,
    ) -> int:
        """Count occurrences of pattern across logs within the lookback window."""
        return len(self.grep_logs(pattern, lookback_days, log_names))

    def tail_lines(self, log_name: str, n: int = 50) -> List[str]:
        """Return the last N lines of the current (non-rotated) log file."""
        path = os.path.join(self.log_dir, log_name)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", errors="replace") as fh:
                all_lines = fh.readlines()
            return [l.rstrip() for l in all_lines[-n:]]
        except (IOError, PermissionError):
            return []

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _parse_timestamp(self, line: str) -> Optional[datetime]:
        """Extract timestamp from log line.

        Expected format: '2026-05-15 18:38:48 - src.module - LEVEL - message'
        Falls back gracefully if the line doesn't start with a timestamp.
        """
        if len(line) < 19:
            return None
        try:
            return datetime.strptime(line[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None

    def _get_rotated_files(self, base_name: str, cutoff: datetime) -> List[str]:
        """Return [base_name, base_name.1, base_name.2, ...] that exist and are relevant.

        Stops at the first gap in the rotation sequence. Files are returned
        newest-first (base_name first, then .1, .2, ...).
        """
        base_path = os.path.join(self.log_dir, base_name)
        files: List[str] = []

        # Always include the current file if it exists
        if os.path.exists(base_path):
            files.append(base_path)

        # Walk rotated copies
        for i in range(1, 101):
            rotated = f"{base_path}.{i}"
            if not os.path.exists(rotated):
                break  # rotation sequence is sequential — stop at first gap
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(rotated))
                # Include if mtime is within lookback (proxy for content recency)
                # Always include .1 as it may contain the tail of the current window
                if i == 1 or mtime >= cutoff:
                    files.append(rotated)
                else:
                    break  # files get older as number increases
            except OSError:
                break

        return files  # newest first; caller reverses for chronological order
