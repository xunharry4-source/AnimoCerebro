#!/usr/bin/env python3
"""
反思系统数据迁移脚本
从 JSON 文件迁移到 SQLite 数据库

用法:
  python src/zentex/reflection/migrate_to_sqlite.py
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def migrate_reflections():
    """迁移反思数据从 JSON 到 SQLite"""
    
    try:
        # 添加 src 到路径
        src_path = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(src_path))
        
        from zentex.reflection.reflection_dao import get_reflection_dao
        from zentex.reflection.models import ReflectionRecord
        
        # 1. 加载 JSON 文件
        json_dir = Path.home() / '.zentex' / 'reflection'
        reflections_file = json_dir / 'reflections.json'
        
        if not reflections_file.exists():
            logger.warning(f"No reflections.json file found at {reflections_file}")
            logger.info("Migration skipped - no data to migrate")
            return True
        
        logger.info(f"📥 Loading reflections from {reflections_file}")
        with open(reflections_file, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        logger.info(f"✅ Loaded {len(json_data)} reflections from JSON")
        
        # 2. 初始化 DAO
        logger.info("🔧 Initializing ReflectionDAO...")
        dao = get_reflection_dao()
        
        # 3. 迁移数据
        migrated_count = 0
        error_count = 0
        
        for reflection_id, reflection_data in json_data.items():
            try:
                # 确保数据是字典
                if not isinstance(reflection_data, dict):
                    logger.warning(f"⚠️ Skipping {reflection_id}: invalid data type {type(reflection_data)}")
                    error_count += 1
                    continue
                
                # 添加 reflection_id 字段
                reflection_data['reflection_id'] = reflection_id
                
                # 创建 ReflectionRecord对象
                reflection = ReflectionRecord(**reflection_data)
                
                # 保存到数据库
                dao.save_reflection(reflection)
                migrated_count += 1
                
                if migrated_count % 10 == 0:
                    logger.debug(f"  Progress: {migrated_count}/{len(json_data)}")
                
            except Exception as e:
                logger.error(f"❌ Failed to migrate {reflection_id}: {str(e)[:100]}")
                error_count += 1
                continue
        
        # 4. 记录迁移结果
        logger.info("="*60)
        logger.info("📊 MIGRATION RESULTS")
        logger.info("="*60)
        logger.info(f"✅ Successfully migrated: {migrated_count}")
        logger.info(f"❌ Failed: {error_count}")
        logger.info(f"📈 Total: {migrated_count + error_count}")
        
        if error_count == 0:
            logger.info("✅ Migration completed successfully!")
            
            # 5. 备份原始 JSON
            backup_dir = json_dir / f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            backup_dir.mkdir(exist_ok=True)
            
            import shutil
            backup_file = backup_dir / 'reflections.json'
            shutil.copy2(reflections_file, backup_file)
            logger.info(f"💾 Original JSON backed up to {backup_file}")
            
            # 6. 验证迁移
            logger.info("\n🔍 Verifying migration...")
            loaded = dao.load_all_reflections()
            logger.info(f"✅ Database verification: {len(loaded)} reflections in SQLite")
            
            if len(loaded) >= migrated_count:
                logger.info("✅ Verification passed!")
                return True
            else:
                logger.error("❌ Verification failed - database count mismatch")
                return False
        else:
            logger.warning(f"⚠️ Migration completed with {error_count} errors")
            return False
            
    except Exception as e:
        logger.error(f"❌ Migration failed: {str(e)}", exc_info=True)
        return False


if __name__ == "__main__":
    success = migrate_reflections()
    sys.exit(0 if success else 1)
