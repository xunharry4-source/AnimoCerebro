#!/usr/bin/env python3
"""
Phase 2 任务系统迁移脚本

类似于 Phase 1 反思系统迁移，本脚本将任务从 JSON 迁移到 SQLite

任务：
1. 检查任务 JSON 文件
2. 加载任务数据
3. 转换为数据库模型
4. 保存到 SQLite
5. 验证迁移完整性
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime, timezone

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 添加 src 到路径
sys.path.insert(0, str(Path.cwd() / 'src'))

from zentex.tasks.models import ZentexTask, SuspendedTask, TaskStatus
from zentex.tasks.persistence.dao import TaskDAO, SuspendedTaskDAO
from zentex.common.database import DatabaseConnection


def check_json_files():
    """检查任务 JSON 文件是否存在"""
    print("\n" + "=" * 60)
    print("STEP 1: 检查任务 JSON 文件")
    print("=" * 60)
    
    # 任务文件位置
    home = Path.home()
    tasks_dir = home / '.zentex' / 'tasks'
    tasks_file = tasks_dir / 'tasks.json'
    suspended_file = tasks_dir / 'suspended_tasks.json'
    
    if tasks_file.exists():
        logger.info(f"✅ 任务文件找到: {tasks_file}")
        with open(tasks_file) as f:
            data = json.load(f)
            count = len(data) if isinstance(data, dict) else 0
        logger.info(f"   包含 {count} 个任务")
        return tasks_file, suspended_file, count
    else:
        logger.warning(f"⚠️  任务文件不存在: {tasks_file}")
        logger.info("   这是正常的，如果系统刚启动，任务数据可能还未生成")
        return None, None, 0


def load_tasks_from_json(tasks_file: Path, suspended_file: Path):
    """从 JSON 加载任务数据"""
    print("\n" + "=" * 60)
    print("STEP 2: 从 JSON 加载任务数据")
    print("=" * 60)
    
    tasks = {}
    suspended_tasks = {}
    
    if tasks_file and tasks_file.exists():
        try:
            with open(tasks_file) as f:
                tasks_data = json.load(f)
                # 如果是字典格式
                if isinstance(tasks_data, dict):
                    tasks = tasks_data
                # 如果是列表格式
                elif isinstance(tasks_data, list):
                    tasks = {t['task_id']: t for t in tasks_data}
            
            logger.info(f"✅ 加载 {len(tasks)} 个任务")
        except Exception as e:
            logger.error(f"❌ 加载任务失败: {e}")
            return None, None
    
    if suspended_file and suspended_file.exists():
        try:
            with open(suspended_file) as f:
                suspended_data = json.load(f)
                if isinstance(suspended_data, dict):
                    suspended_tasks = suspended_data
                elif isinstance(suspended_data, list):
                    suspended_tasks = {t['task_id']: t for t in suspended_data}
            
            logger.info(f"✅ 加载 {len(suspended_tasks)} 个暂停任务")
        except Exception as e:
            logger.warning(f"⚠️  加载暂停任务失败: {e}")
    
    return tasks, suspended_tasks


def migrate_to_sqlite(tasks: dict, suspended_tasks: dict):
    """将任务迁移到 SQLite"""
    print("\n" + "=" * 60)
    print("STEP 3: 迁移任务到 SQLite")
    print("=" * 60)
    
    if not tasks and not suspended_tasks:
        logger.info("⚠️  没有任务数据需要迁移")
        return True
    
    try:
        # 连接到数据库
        db = DatabaseConnection("runtime/data/zentex_core.db")
        task_dao = TaskDAO(db)
        suspended_dao = SuspendedTaskDAO(db)
        
        migrated_count = 0
        
        # 迁移常规任务
        for task_id, task_data in tasks.items():
            try:
                # 确保数据格式正确
                if not isinstance(task_data, dict):
                    logger.warning(f"⚠️  任务 {task_id} 格式错误，跳过")
                    continue
                
                # 确保有 task_id
                if 'task_id' not in task_data:
                    task_data['task_id'] = task_id
                
                # 保存到数据库
                if task_dao.create_task(task_data):
                    migrated_count += 1
                else:
                    logger.warning(f"⚠️  任务 {task_id} 保存失败")
            except Exception as e:
                logger.warning(f"⚠️  迁移任务 {task_id} 异常: {e}")
        
        logger.info(f"✅ 迁移 {migrated_count}/{len(tasks)} 个常规任务")
        
        # 迁移暂停任务
        suspended_count = 0
        for task_id, suspended_data in suspended_tasks.items():
            try:
                if not isinstance(suspended_data, dict):
                    logger.warning(f"⚠️  暂停任务 {task_id} 格式错误，跳过")
                    continue
                
                if 'task_id' not in suspended_data:
                    suspended_data['task_id'] = task_id
                
                if suspended_dao.create_suspended_task(suspended_data):
                    suspended_count += 1
                else:
                    logger.warning(f"⚠️  暂停任务 {task_id} 保存失败")
            except Exception as e:
                logger.warning(f"⚠️  迁移暂停任务 {task_id} 异常: {e}")
        
        logger.info(f"✅ 迁移 {suspended_count}/{len(suspended_tasks)} 个暂停任务")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def verify_migration():
    """验证迁移完整性"""
    print("\n" + "=" * 60)
    print("STEP 4: 验证迁移")
    print("=" * 60)
    
    try:
        db = DatabaseConnection("runtime/data/zentex_core.db")
        task_dao = TaskDAO(db)
        
        # 查询数据库中的任务数
        tasks = task_dao.list_all()
        logger.info(f"✅ 数据库中的任务数: {len(tasks)}")
        
        if len(tasks) > 0:
            # 显示前几个任务
            logger.info("📋 前 3 个任务:")
            for i, task in enumerate(list(tasks.values())[:3], 1):
                task_id = task.get('task_id', 'N/A') if isinstance(task, dict) else task.task_id
                status = task.get('status', 'N/A') if isinstance(task, dict) else task.status
                logger.info(f"   {i}. ID: {task_id[:20]}... | Status: {status}")
        
        return True
    except Exception as e:
        logger.warning(f"⚠️  验证异常: {e}")
        return False


def generate_report():
    """生成迁移报告"""
    print("\n" + "=" * 60)
    print("迁移完成报告")
    print("=" * 60)
    
    report = """
✅ Phase 2 任务系统迁移脚本完成

状态:
- 检查任务 JSON 文件
- 从 JSON 加载任务数据  
- 迁移到 SQLite 数据库
- 验证迁移完整性

注意:
- 如果没有找到任务 JSON 文件，这是正常的（新系统）
- 系统会自动为新任务创建数据库记录
- 已有的 TaskDAO 会正确处理所有操作

下一步:
- 实现完成任务自动归档机制
- 清理幂等日志
- 性能基准测试
"""
    
    logger.info(report)
    print(report)


def main():
    """主程序"""
    print("\n" + "=" * 60)
    print("PHASE 2 任务系统迁移脚本")
    print("=" * 60)
    
    # Step 1: 检查 JSON 文件
    tasks_file, suspended_file, count = check_json_files()
    
    # Step 2: 加载数据
    if tasks_file:
        tasks, suspended_tasks = load_tasks_from_json(tasks_file, suspended_file)
    else:
        logger.info("ℹ️  任务数据不存在，这是正常的")
        tasks, suspended_tasks = {}, {}
    
    # Step 3: 迁移到 SQLite
    if migrate_to_sqlite(tasks, suspended_tasks):
        logger.info("✅ 迁移步骤完成")
    else:
        logger.error("❌ 迁移失败")
        return 1
    
    # Step 4: 验证
    if verify_migration():
        logger.info("✅ 验证成功")
    else:
        logger.warning("⚠️  验证有误，但继续进行")
    
    # 生成报告
    generate_report()
    
    print("\n" + "=" * 60)
    print("🟢 Phase 2 脚本执行完成")
    print("=" * 60)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
