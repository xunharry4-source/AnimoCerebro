#!/usr/bin/env python3
"""
Migration script to add new fields to mcp_servers table.
Adds: name, description, version, tags_json, owner, created_at
"""

import sqlite3
import sys
from pathlib import Path

def migrate_db(db_path: str | Path):
    """Add missing columns to mcp_servers table."""
    db_path = Path(db_path)
    
    if not db_path.exists():
        print(f"Database file not found: {db_path}")
        return False
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check current schema
        cursor.execute("PRAGMA table_info(mcp_servers)")
        columns = [row[1] for row in cursor.fetchall()]
        
        print(f"Current columns: {columns}")
        
        # Add missing columns
        migrations = []
        
        if "name" not in columns:
            migrations.append("ALTER TABLE mcp_servers ADD COLUMN name TEXT")
        
        if "description" not in columns:
            migrations.append("ALTER TABLE mcp_servers ADD COLUMN description TEXT")
        
        if "version" not in columns:
            migrations.append("ALTER TABLE mcp_servers ADD COLUMN version TEXT")
        
        if "tags_json" not in columns:
            migrations.append("ALTER TABLE mcp_servers ADD COLUMN tags_json TEXT")
        
        if "owner" not in columns:
            migrations.append("ALTER TABLE mcp_servers ADD COLUMN owner TEXT")
        
        if "created_at" not in columns:
            migrations.append("ALTER TABLE mcp_servers ADD COLUMN created_at TEXT")
        
        if not migrations:
            print("✓ Database is already up to date. No migrations needed.")
            return True
        
        print(f"\nApplying {len(migrations)} migration(s)...")
        
        for sql in migrations:
            print(f"  Executing: {sql}")
            cursor.execute(sql)
        
        conn.commit()
        
        # Verify
        cursor.execute("PRAGMA table_info(mcp_servers)")
        new_columns = [row[1] for row in cursor.fetchall()]
        print(f"\n✓ Migration complete!")
        print(f"New columns: {new_columns}")
        
        return True
        
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    # Default database path
    default_db = Path(__file__).parent.parent.parent.parent / "runtime" / "data" / "zentex_assets.sqlite"
    
    db_path = sys.argv[1] if len(sys.argv) > 1 else str(default_db)
    
    print(f"MCP Database Migration Tool")
    print(f"=" * 50)
    print(f"Database: {db_path}\n")
    
    success = migrate_db(db_path)
    sys.exit(0 if success else 1)
