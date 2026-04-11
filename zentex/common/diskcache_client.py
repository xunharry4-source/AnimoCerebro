import os
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

_disk_cache = None

def get_disk_cache():
    """Singleton-like access to the DiskCache instance."""
    global _disk_cache
    if _disk_cache is None:
        try:
            import diskcache
            # Default to an app_data/cache directory in the current project
            project_root = os.getcwd()
            base_dir = os.environ.get("ZENTEX_DATA_DIR", os.path.join(project_root, "app_data"))
            cache_dir = os.path.join(base_dir, "cache", "state_v2")
            os.makedirs(cache_dir, exist_ok=True)
            
            _disk_cache = diskcache.Cache(cache_dir)
            logger.info(f"Initialized DiskCache at {cache_dir}")
        except ImportError:
            logger.error("diskcache module not found. Please install it using 'pip install diskcache'.")
            raise
    return _disk_cache
