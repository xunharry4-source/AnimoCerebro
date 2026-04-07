from __future__ import annotations

from pathlib import Path

import pytest

from zentex.core.config import ConfigLoadError, load_required_mapping_section, load_yaml_config


def test_load_yaml_config_reads_mapping(tmp_path: Path) -> None:
    config_file = tmp_path / "sample.yml"
    config_file.write_text("root:\n  enabled: true\n", encoding="utf-8")

    payload = load_yaml_config(config_file)

    assert payload == {"root": {"enabled": True}}


def test_load_yaml_config_raises_for_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yml"

    with pytest.raises(ConfigLoadError) as exc_info:
        load_yaml_config(missing)

    assert "Configuration file not found" in str(exc_info.value)


def test_load_required_mapping_section_raises_for_missing_section(tmp_path: Path) -> None:
    config_file = tmp_path / "sample.yml"
    config_file.write_text("root:\n  enabled: true\n", encoding="utf-8")

    with pytest.raises(ConfigLoadError) as exc_info:
        load_required_mapping_section(config_file, "providers")

    assert "providers" in str(exc_info.value)
