from __future__ import annotations

from zentex.llm.providers.config import get_maintenance_llm_config


def test_learning_maintenance_provider_config_real() -> None:
    """功能：验证 maintenance provider 配置读取真实文件。"""
    cfg = get_maintenance_llm_config()
    assert isinstance(cfg, dict)
    assert cfg.get("provider_key") == "ollama"

