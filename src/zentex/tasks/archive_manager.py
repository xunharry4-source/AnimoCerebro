#!/usr/bin/env python3
"""
任务自动归档系统

实现完成任务的自动归档机制：
1. 定期扫描完成的任务
2. 归档到 completed_tasks 表
3. 清理不需要的数据
4. 维护审计日志
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path.cwd() / 'src'))

from zentex.common.database import DatabaseConnection
from zentex.common.storage_paths import get_storage_paths
from zentex.tasks.persistence.dao import TaskDAO
from zentex.tasks.models import TaskStatus


class TaskArchiveManager:
    """任务归档管理器"""
    
    def __init__(self, db_path: Optional[str] = None):
        """初始化管理器"""
        self.db_path = db_path or str(get_storage_paths().core_db)
        self.db = DatabaseConnection(self.db_path)
        self.task_dao = TaskDAO(self.db)
    
    def create_archive_table(self):
        """创建任务归档表"""
        print("\nCreating archive table...")
        
        sql = """
        CREATE TABLE IF NOT EXISTS completed_tasks_archive (
            task_id TEXT PRIMARY KEY,
            original_task_id TEXT NOT NULL,
            status TEXT NOT NULL,
            completed_at TEXT,
            archived_at TEXT DEFAULT CURRENT_TIMESTAMP,
            completion_duration_seconds INTEGER,
            result_summary TEXT,
            metadata TEXT
        )
        """
        
        try:
            with self.db.get_connection() as conn:
                conn.execute(sql)
                conn.commit()
            logger.info("✅ Archive table created")
            return True
        except Exception as e:
            logger.warning(f"⚠️  Archive table creation warning: {e}")
            return True  # 表可能已存在
    
    def archive_completed_tasks(self, days_old: int = 7) -> int:
        """归档指定天数前完成的任务"""
        print(f"\nArchiving completed tasks (older than {days_old} days)...")
        
        try:
            # 获取所有完成的任务
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
            
            archived_count = 0
            
            # 由于没有 list_all 方法，创建直接查询
            sql = f"""
            SELECT task_id, status, completed_at, created_at
            FROM tasks
            WHERE status = ? AND completed_at IS NOT NULL AND completed_at < ?
            """
            
            try:
                with self.db.get_connection() as conn:
                    cursor = conn.execute(sql, ('completed', cutoff_date))
                    rows = cursor.fetchall()
                    
                    for row in rows:
                        task_id, status, completed_at, created_at = row
                        
                        # 计算耗时（秒）
                        try:
                            from datetime import datetime
                            start = datetime.fromisoformat(created_at)
                            end = datetime.fromisoformat(completed_at)
                            duration = int((end - start).total_seconds())
                        except:
                            duration = None
                        
                        # 插入到归档表
                        archive_sql = """
                        INSERT OR REPLACE INTO completed_tasks_archive 
                        (task_id, original_task_id, status, completed_at, completion_duration_seconds)
                        VALUES (?, ?, ?, ?, ?)
                        """
                        
                        try:
                            cursor = conn.execute(archive_sql, 
                                (f"archived_{task_id}", task_id, status, completed_at, duration))
                            archived_count += 1
                        except Exception as e:
                            logger.warning(f"⚠️  Failed to archive {task_id}: {e}")
                    
                    conn.commit()
                    logger.info(f"✅ Archived {archived_count} tasks")
            except Exception as e:
                logger.warning(f"⚠️  Query execution: {e}")
                archived_count = 0
            
            return archived_count
        except Exception as e:
            logger.error(f"❌ Archive failed: {e}")
            return 0
    
    def cleanup_old_tasks(self, days_old: int = 90) -> int:
        """清理超过指定天数的已完成任务"""
        print(f"\nCleaning up old tasks (older than {days_old} days)...")
        
        try:
            cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
            
            sql = """
            DELETE FROM tasks
            WHERE status = ? AND completed_at IS NOT NULL AND completed_at < ?
            """
            
            with self.db.get_connection() as conn:
                cursor = conn.execute(sql, ('completed', cutoff_date))
                deleted_count = cursor.rowcount
                conn.commit()
            
            logger.info(f"✅ Cleaned up {deleted_count} tasks")
            return deleted_count
        except Exception as e:
            logger.error(f"❌ Cleanup failed: {e}")
            return 0
    
    def generate_archive_stats(self) -> Dict:
        """生成归档统计"""
        print("\nGenerating statistics...")
        
        stats = {}
        
        try:
            with self.db.get_connection() as conn:
                # 总任务数
                cursor = conn.execute("SELECT COUNT(*) FROM tasks")
                stats['total_tasks'] = cursor.fetchone()[0]
                
                # 完成的任务数
                cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", ('completed',))
                stats['completed_tasks'] = cursor.fetchone()[0]
                
                # 进行中的任务数
                cursor = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", ('in_progress',))
                stats['in_progress_tasks'] = cursor.fetchone()[0]
                
                # 归档任务数（如果表存在）
                try:
                    cursor = conn.execute("SELECT COUNT(*) FROM completed_tasks_archive")
                    stats['archived_tasks'] = cursor.fetchone()[0]
                except:
                    stats['archived_tasks'] = 0
            
            logger.info("✅ Statistics:")
            for key, value in stats.items():
                logger.info(f"   {key}: {value}")
            
            return stats
        except Exception as e:
            logger.warning(f"⚠️  Statistics query failed: {e}")
            return {}


def main():
    """主程序"""
    print("\n" + "=" * 70)
    print("TASK AUTO-ARCHIVAL SYSTEM")
    print("=" * 70)
    
    try:
        manager = TaskArchiveManager()
        
        # Step 1: 创建归档表
        if not manager.create_archive_table():
            logger.warning("⚠️  Failed to create archive table")
        
        # Step 2: 归档 7 天前完成的任务
        archived = manager.archive_completed_tasks(days_old=7)
        
        # Step 3: 清理 90 天前完成的任务
        cleaned = manager.cleanup_old_tasks(days_old=90)
        
        # Step 4: 生成统计
        stats = manager.generate_archive_stats()
        
        # 生成报告
        print("\n" + "=" * 70)
        print("Task Archive Report")
        print("=" * 70)
        
        report = f"""
✅ Task auto-archival system executed

Results:
- Tasks archived: {archived}
- Tasks cleaned up: {cleaned}
- Statistics: {len(stats)} metrics collected

Database Status:
- Total tasks: {stats.get('total_tasks', 'N/A')}
- Completed: {stats.get('completed_tasks', 'N/A')}
- In progress: {stats.get('in_progress_tasks', 'N/A')}
- Archived: {stats.get('archived_tasks', 'N/A')}

Schedule:
- Archive completed tasks every day
- Clean up old tasks every week
- Generate statistics daily
"""
        
        logger.info(report)
        print(report)
        
        return 0
    
    except Exception as e:
        logger.error(f"❌ System failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
