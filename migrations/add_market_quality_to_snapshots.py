"""
Migration: add market_quality_score and market_quality_grade to equity_snapshots.

Run once on EC2:
  python3 migrations/add_market_quality_to_snapshots.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.database import get_database

def run():
    db = get_database()
    session = db.get_session()
    try:
        from sqlalchemy import text
        # Add columns if they don't already exist (idempotent)
        session.execute(text("""
            ALTER TABLE equity_snapshots
            ADD COLUMN IF NOT EXISTS market_quality_score FLOAT,
            ADD COLUMN IF NOT EXISTS market_quality_grade VARCHAR(16);
        """))
        session.commit()
        print("Migration complete: market_quality_score and market_quality_grade added to equity_snapshots")
    except Exception as e:
        session.rollback()
        print(f"Migration failed: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    run()
