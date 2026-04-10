#!/usr/bin/env python3
"""
Cleanup old log files to save disk space.

Usage:
    python scripts/utilities/cleanup_old_logs.py [--days 7] [--dry-run]
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path


def cleanup_old_logs(days: int = 7, dry_run: bool = False) -> dict:
    """
    Delete log files older than specified days.
    
    Args:
        days: Delete logs older than this many days
        dry_run: If True, only show what would be deleted
        
    Returns:
        Dict with cleanup statistics
    """
    cutoff = datetime.now() - timedelta(days=days)
    log_dir = Path("logs")
    
    if not log_dir.exists():
        print(f"Log directory not found: {log_dir}")
        return {"deleted": 0, "size_freed": 0}
    
    deleted_count = 0
    size_freed = 0
    
    print(f"{'DRY RUN: ' if dry_run else ''}Cleaning up logs older than {days} days (before {cutoff.strftime('%Y-%m-%d %H:%M:%S')})")
    print("-" * 80)
    
    # Clean timestamped logs
    for log_file in log_dir.glob("alphacent_*.log"):
        file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
        
        if file_mtime < cutoff:
            size = log_file.stat().st_size
            size_freed += size
            deleted_count += 1
            
            size_str = f"{size / 1024:.1f}KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f}MB"
            print(f"{'Would delete' if dry_run else 'Deleting'}: {log_file.name} ({size_str})")
            
            if not dry_run:
                log_file.unlink()
    
    # Clean empty logs
    print("\nCleaning empty log files...")
    for log_file in log_dir.rglob("*.log"):
        if log_file.stat().st_size == 0:
            deleted_count += 1
            print(f"{'Would delete' if dry_run else 'Deleting'}: {log_file.relative_to(log_dir)} (empty)")
            
            if not dry_run:
                log_file.unlink()
    
    # Clean tiny logs (< 1KB, likely just startup messages)
    print("\nCleaning tiny log files (< 1KB)...")
    for log_file in log_dir.glob("alphacent_*.log"):
        size = log_file.stat().st_size
        if 0 < size < 1024:
            size_freed += size
            deleted_count += 1
            print(f"{'Would delete' if dry_run else 'Deleting'}: {log_file.name} ({size}B)")
            
            if not dry_run:
                log_file.unlink()
    
    print("-" * 80)
    size_freed_mb = size_freed / (1024 * 1024)
    print(f"{'Would delete' if dry_run else 'Deleted'} {deleted_count} files, freeing {size_freed_mb:.2f}MB")
    
    return {
        "deleted": deleted_count,
        "size_freed": size_freed,
        "size_freed_mb": size_freed_mb
    }


def main():
    parser = argparse.ArgumentParser(description="Cleanup old log files")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Delete logs older than this many days (default: 7)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    
    args = parser.parse_args()
    
    stats = cleanup_old_logs(days=args.days, dry_run=args.dry_run)
    
    if args.dry_run:
        print("\nThis was a dry run. Use without --dry-run to actually delete files.")
    else:
        print("\nCleanup complete!")


if __name__ == "__main__":
    main()
