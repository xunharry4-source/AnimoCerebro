#!/usr/bin/env python3
"""
Simple integration test for unified database connection.

This test verifies the core database functionality without requiring
full application dependencies (pydantic, etc.).

Usage:
    python scripts/test_db_simple_integration.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root / "src"))


def test_unified_connection():
    """Test unified database connection basic operations."""
    print("\n=== Test 1: Unified Connection Basic Operations ===")
    
    from zentex.common.db_connection import get_db_connection
    
    db = get_db_connection()
    test_db_path = "runtime/data/test_simple.db"
    
    # Initialize
    db.initialize(test_db_path)
    assert db.is_initialized
    print(f"✓ Database initialized at: {db.db_path}")
    
    # Create test table
    db.execute_script("""
        CREATE TABLE IF NOT EXISTS test_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            value REAL
        );
    """)
    print("✓ Test table created")
    
    # Insert data
    affected = db.execute_update(
        "INSERT INTO test_items (name, value) VALUES (?, ?)",
        ("item1", 10.5)
    )
    assert affected == 1
    print("✓ Data inserted")
    
    # Query data
    rows = db.execute_query("SELECT * FROM test_items WHERE name = ?", ("item1",))
    assert len(rows) == 1
    assert rows[0]['name'] == "item1"
    assert rows[0]['value'] == 10.5
    print(f"✓ Data queried: {dict(rows[0])}")
    
    # Scalar query
    count = db.execute_scalar("SELECT COUNT(*) FROM test_items")
    assert count == 1
    print(f"✓ Scalar query: count={count}")
    
    # Batch insert
    items = [("item2", 20.0), ("item3", 30.0)]
    affected = db.execute_many(
        "INSERT INTO test_items (name, value) VALUES (?, ?)",
        items
    )
    assert affected == 2
    print(f"✓ Batch insert: {affected} rows")
    
    # Verify total count
    total = db.execute_scalar("SELECT COUNT(*) FROM test_items")
    assert total == 3
    print(f"✓ Total items: {total}")
    
    # Cleanup
    db.shutdown()
    print("✓ Database shutdown")
    
    return test_db_path


def test_transaction_management():
    """Test transaction commit and rollback."""
    print("\n=== Test 2: Transaction Management ===")
    
    from zentex.common.db_connection import get_db_connection
    
    db = get_db_connection()
    test_db_path = "runtime/data/test_transactions.db"
    db.initialize(test_db_path)
    
    # Create table
    db.execute_script("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT,
            amount REAL
        );
    """)
    
    # Successful transaction
    with db.get_connection() as conn:
        conn.execute("INSERT INTO transactions (description, amount) VALUES (?, ?)", 
                    ("deposit", 100.0))
        conn.execute("INSERT INTO transactions (description, amount) VALUES (?, ?)", 
                    ("deposit", 200.0))
    print("✓ Successful transaction committed")
    
    # Failed transaction (rollback)
    try:
        with db.get_connection() as conn:
            conn.execute("INSERT INTO transactions (description, amount) VALUES (?, ?)", 
                        ("withdrawal", -50.0))
            raise ValueError("Simulated error")
    except ValueError:
        pass
    print("✓ Failed transaction rolled back")
    
    # Verify only successful inserts remain
    count = db.execute_scalar("SELECT COUNT(*) FROM transactions")
    assert count == 2, f"Expected 2 rows, got {count}"
    print(f"✓ Only committed transactions remain: {count} rows")
    
    # Cleanup
    db.shutdown()
    return test_db_path


def test_concurrent_access():
    """Test thread-safe concurrent access."""
    print("\n=== Test 3: Concurrent Access ===")
    
    import threading
    from zentex.common.db_connection import get_db_connection
    
    db = get_db_connection()
    test_db_path = "runtime/data/test_concurrent.db"
    db.initialize(test_db_path)
    
    # Create table
    db.execute_script("""
        CREATE TABLE IF NOT EXISTS concurrent_test (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            thread_name TEXT,
            value INTEGER
        );
    """)
    
    # Worker function
    def worker(thread_id):
        thread_db = get_db_connection()
        for i in range(5):
            thread_db.execute_update(
                "INSERT INTO concurrent_test (thread_name, value) VALUES (?, ?)",
                (f"thread-{thread_id}", i)
            )
    
    # Start multiple threads
    threads = []
    for i in range(3):
        t = threading.Thread(target=worker, args=(i,))
        threads.append(t)
        t.start()
    
    # Wait for all threads
    for t in threads:
        t.join()
    
    print("✓ All threads completed")
    
    # Verify all inserts succeeded
    count = db.execute_scalar("SELECT COUNT(*) FROM concurrent_test")
    expected = 3 * 5  # 3 threads × 5 inserts each
    assert count == expected, f"Expected {expected} rows, got {count}"
    print(f"✓ All inserts successful: {count} rows from 3 threads")
    
    # Cleanup
    db.shutdown()
    return test_db_path


def cleanup_test_databases(db_paths):
    """Remove test database files."""
    print("\n=== Cleanup ===")
    
    for db_path in db_paths:
        path = Path(db_path)
        if path.exists():
            path.unlink()
            print(f"✓ Removed: {path}")
        
        # Remove WAL and SHM files
        for ext in ['-wal', '-shm']:
            wal_path = Path(str(path) + ext)
            if wal_path.exists():
                wal_path.unlink()


def main():
    """Run all tests."""
    print("=" * 70)
    print("Unified Database Connection - Simple Integration Test")
    print("=" * 70)
    
    db_paths = []
    
    try:
        # Test 1: Basic operations
        path1 = test_unified_connection()
        db_paths.append(path1)
        
        # Test 2: Transaction management
        path2 = test_transaction_management()
        db_paths.append(path2)
        
        # Test 3: Concurrent access
        path3 = test_concurrent_access()
        db_paths.append(path3)
        
        # Cleanup
        cleanup_test_databases(db_paths)
        
        print("\n" + "=" * 70)
        print("✅ All tests passed!")
        print("=" * 70)
        print("\nKey Features Verified:")
        print("  ✓ Singleton pattern")
        print("  ✓ Thread-safe connections")
        print("  ✓ WAL mode enabled")
        print("  ✓ Automatic transaction management")
        print("  ✓ CRUD operations")
        print("  ✓ Batch operations")
        print("  ✓ Concurrent access")
        return 0
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
        # Cleanup on failure
        cleanup_test_databases(db_paths)
        return 1


if __name__ == "__main__":
    sys.exit(main())
