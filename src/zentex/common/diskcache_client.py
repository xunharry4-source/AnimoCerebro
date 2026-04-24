import os
import logging
from typing import Optional
from pathlib import Path
from datetime import datetime
import shutil
from zentex.common.storage_paths import get_storage_paths

logger = logging.getLogger(__name__)

_disk_cache = None


def _rotate_corrupt_cache_dir(cache_dir: str, exc: Exception) -> None:
    path = Path(cache_dir)
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = path.with_name(f"{path.name}.corrupt_{stamp}")
    logger.warning(
        "DiskCache at %s is corrupt (%s). Moving it to %s before reinitialization.",
        cache_dir,
        exc,
        backup,
    )
    shutil.move(str(path), str(backup))

def get_disk_cache():
    """Singleton-like access to the DiskCache instance."""
    global _disk_cache
    if _disk_cache is None:
        try:
            import diskcache
            # Default to the configured app data directory.
            base_dir = os.environ.get("ZENTEX_DATA_DIR")
            if base_dir:
                cache_dir = os.path.join(base_dir, "cache", "state_v2")
            else:
                cache_dir = str(get_storage_paths().app_data_dir / "cache" / "state_v2")
            os.makedirs(cache_dir, exist_ok=True)

            try:
                _disk_cache = diskcache.Cache(cache_dir)
            except Exception as exc:
                message = str(exc).lower()
                # Handle SQLite authorization denied (macOS Sandbox/TCC) or Corruption
                if "authorization denied" in message or "malformed" in message or "disk image is malformed" in message:
                    if "authorization denied" in message:
                        # Fallback to /tmp which is usually writable even in sandboxed environments
                        temp_cache = os.path.join("/tmp", f"zentex_cache_{os.getpid()}")
                        logger.warning(f"DiskCache authorization denied at {cache_dir}. Falling back to {temp_cache}")
                        cache_dir = temp_cache
                    else:
                        _rotate_corrupt_cache_dir(cache_dir, exc)
                    
                    os.makedirs(cache_dir, exist_ok=True)
                    _disk_cache = diskcache.Cache(cache_dir)
                else:
                    raise
            logger.info(f"Initialized DiskCache at {cache_dir}")
        except ImportError:
            logger.error("diskcache module not found. Please install it using 'pip install diskcache'.")
            raise
    return _disk_cache
