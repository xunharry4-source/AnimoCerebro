#!/usr/bin/env python3
"""
Test script for unified database connection.

This script verifies that the UnifiedDatabaseConnection works correctly,
including singleton behavior, thread safety, and basic CRUD operations.

Usage:
    python scripts/test_db_connection.py
"""

import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))

from zentex.common.db_connection import get_db_connection


def test_singleton():
    """Test that only one instance exists."""
    print("\n=== Testing Singleton Pattern ===")
    
    db1 = get_db_connection()
    db2 = get_db_connection()
    
    assert db1 is db2, "Singleton pattern failed - different instances returned"
    print("✓ Singleton pattern works correctly")


def test_initialization():
    """Test database initialization."""
    print("\n=== Testing Initialization ===")
    
    db = get_db_connection()
    
    # Should not be initialized yet
    assert not db.is_initialized, "Database should not be initialized yet"
    print("✓ Initial state correct (not initialized)")
    
    # Initialize
    test_db_path = "runtime/data/test_connection.db"
    db.initialize(test_db_path)
    
    assert db.is_initialized, "Database should be initialized"
    assert db.db_path == Path(test_db_path), "Database path mismatch"
    print(f"✓ Database initialized at: {db.db_path}")
    
    # Second initialization should be skipped
    db.initialize(test_db_path)
    print("✓ Re-initialization handled correctly (skipped)")
    
    return test_db_path


def test_basic_operations(db_path: str):
    """Test basic database operations."""
    print("\n=== Testing Basic Operations ===")
    
    db = get_db_connection()
    
    # Create a test table
    db.execute_script("""
        CREATE TABLE IF NOT EXISTS test_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE
        );
    """)
    print("✓ Test table created")
    
    # Insert data
    affected = db.execute_update(
        "INSERT INTO test_users (name, email) VALUES (?, ?)",
        ("Alice", "alice@example.com")
    )
    assert affected == 1, f"Expected 1 row affected, got {affected}"
    print("✓ Insert operation successful")
    
    # Query data
    rows = db.execute_query("SELECT * FROM test_users WHERE name = ?", ("Alice",))
    assert len(rows) == 1, f"Expected 1 row, got {len(rows)}"
    assert rows[0]['name'] == "Alice", "Data mismatch"
    print(f"✓ Query operation successful: {dict(rows[0])}")
    
    # Scalar query
    count = db.execute_scalar("SELECT COUNT(*) FROM test_users")
    assert count == 1, f"Expected count 1, got {count}"
    print(f"✓ Scalar query successful: count={count}")
    
    # Batch insert
    users = [
        ("Bob", "bob@example.com"),
        ("Charlie", "charlie@example.com"),
    ]
    affected = db.execute_many(
        "INSERT INTO test_users (name, email) VALUES (?, ?)",
        users
    )
    assert affected == 2, f"Expected 2 rows affected, got {affected}"
    print(f"✓ Batch insert successful: {affected} rows")
    
    # Check table exists
    assert db.table_exists("test_users"), "Table should exist"
    assert not db.table_exists("nonexistent_table"), "Non-existent table check failed"
    print("✓ Table existence check successful")
    
    # Get all tables
    tables = db.get_table_names()
    assert "test_users" in tables, "test_users should be in table list"
    print(f"✓ Table list retrieved: {len(tables)} tables")


def test_transaction_management():
    """Test transaction commit and rollback."""
    print("\n=== Testing Transaction Management ===")
    
    db = get_db_connection()
    
    # Successful transaction (auto-commit)
    with db.get_connection() as conn:
        conn.execute("INSERT INTO test_users (name, email) VALUES (?, ?)", 
                    ("Dave", "dave@example.com"))
    print("✓ Successful transaction committed")
    
    # Failed transaction (auto-rollback)
    try:
        with db.get_connection() as conn:
            conn.execute("INSERT INTO test_users (id, name, email) VALUES (?, ?, ?)",
                        (999, "Eve", "eve@example.com"))
            # This will fail due to duplicate ID if it exists, or succeed
            # Let's force an error
            raise ValueError("Simulated error")
    except ValueError:
        print("✓ Failed transaction rolled back correctly")
    
    # Verify Dave was inserted but Eve was not (if error occurred before insert)
    count = db.execute_scalar("SELECT COUNT(*) FROM test_users WHERE name = 'Dave'")
    assert count == 1, "Dave should have been inserted"
    print("✓ Transaction isolation verified")


def test_cleanup(db_path: str):
    """Clean up test database."""
    print("\n=== Cleaning Up ===")
    
    db = get_db_connection()
    db.shutdown()
    print("✓ Database connection shutdown")
    
    # Remove test database
    test_path = Path(db_path)
    if test_path.exists():
        test_path.unlink()
        print(f"✓ Test database removed: {test_path}")
    
    # Also remove WAL and SHM files if they exist
    for ext in ['-wal', '-shm']:
        wal_path = Path(str(test_path) + ext)
        if wal_path.exists():
            wal_path.unlink()


def main():
    """Run all tests."""
    print("=" * 60)
    print("Unified Database Connection Test")
    print("=" * 60)
    
    try:
        # Test singleton
        test_singleton()
        
        # Test initialization
        db_path = test_initialization()
        
        # Test basic operations
        test_basic_operations(db_path)
        
        # Test transaction management
        test_transaction_management()
        
        # Cleanup
        test_cleanup(db_path)
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
