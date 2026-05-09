from __future__ import annotations

from pathlib import Path
from typing import Any

from zentex.launcher.config import load_yaml_config


DEFAULT_Q8_EVALUATION_PROFILE_PATH = Path("config") / "q8_evaluation_profile.yml"


class Q8EvaluationLensMappingError(RuntimeError):
    def __init__(self, failures: list[dict[str, Any]]) -> None:
        self.failures = failures
        super().__init__("Q8 evaluation lens mapping failed")


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def load_q8_evaluation_lens_mapping_config(
    config_path: Path | str = DEFAULT_Q8_EVALUATION_PROFILE_PATH,
) -> dict[str, Any]:
    payload = load_yaml_config(config_path)
    mapping = _as_dict(payload.get("meta_value_lens_mapping"))
    if not mapping:
        raise Q8EvaluationLensMappingError([{"reason": "meta_value_lens_mapping_missing"}])

    failures: list[dict[str, Any]] = []
    normalized_mapping: dict[str, dict[str, Any]] = {}
    for lens_id, raw_lens in mapping.items():
        lens_key = str(lens_id).strip()
        lens = _as_dict(raw_lens)
        axes = _string_list(lens.get("source_axes"))
        name = str(lens.get("name") or lens_key).strip()
        if not lens_key:
            failures.append({"reason": "lens_id_missing"})
        if not axes:
            failures.append({"reason": "lens_source_axes_missing", "lens_id": lens_key})
        normalized_mapping[lens_key] = {
            "name": name,
            "source_axes": axes,
        }

    if failures:
        raise Q8EvaluationLensMappingError(failures)

    return {
        "version": str(payload.get("version") or "").strip() or "unknown",
        "meta_value_lens_mapping": normalized_mapping,
    }


def map_evaluation_weights_to_meta_value_lenses(
    evaluation_weights: dict[str, Any],
    *,
    config_path: Path | str = DEFAULT_Q8_EVALUATION_PROFILE_PATH,
) -> dict[str, Any]:
    if not isinstance(evaluation_weights, dict) or not evaluation_weights:
        raise Q8EvaluationLensMappingError([{"reason": "evaluation_weights_missing"}])

    failures: list[dict[str, Any]] = []
    source_weights: dict[str, float] = {}
    for axis, value in evaluation_weights.items():
        axis_key = str(axis).strip()
        if not axis_key:
            failures.append({"reason": "evaluation_axis_missing"})
            continue
        try:
            source_weights[axis_key] = float(value)
        except (TypeError, ValueError):
            failures.append({"reason": "evaluation_weight_invalid", "axis": axis_key, "value": value})

    if failures:
        raise Q8EvaluationLensMappingError(failures)

    config = load_q8_evaluation_lens_mapping_config(config_path)
    mapping = _as_dict(config.get("meta_value_lens_mapping"))
    lens_weights: dict[str, float] = {}
    lens_names: dict[str, str] = {}
    lens_axes: dict[str, list[str]] = {}
    lens_axis_weights: dict[str, dict[str, float]] = {}
    consumed_axes: set[str] = set()

    for lens_id, lens in mapping.items():
        axes = _string_list(_as_dict(lens).get("source_axes"))
        axis_weights = {axis: source_weights.get(axis, 0.0) for axis in axes}
        lens_axis_weights[lens_id] = axis_weights
        lens_weights[lens_id] = round(sum(axis_weights.values()), 6)
        lens_names[lens_id] = str(_as_dict(lens).get("name") or lens_id)
        lens_axes[lens_id] = axes
        consumed_axes.update(axes)

    max_weight = max(lens_weights.values(), default=0.0)
    dominant_lenses = sorted(
        lens_id for lens_id, weight in lens_weights.items() if max_weight > 0 and weight == max_weight
    )
    unmapped_source_weights = {
        axis: weight for axis, weight in source_weights.items() if axis not in consumed_axes
    }

    return {
        "mapping_version": str(config.get("version") or "unknown"),
        "lens_weights": lens_weights,
        "lens_names": lens_names,
        "lens_axes": lens_axes,
        "lens_axis_weights": lens_axis_weights,
        "dominant_lenses": dominant_lenses,
        "unmapped_source_weights": unmapped_source_weights,
    }


def enrich_evaluation_profile_with_meta_value_lenses(
    evaluation_profile: dict[str, Any],
    *,
    config_path: Path | str = DEFAULT_Q8_EVALUATION_PROFILE_PATH,
) -> dict[str, Any]:
    profile = dict(evaluation_profile)
    mapping = map_evaluation_weights_to_meta_value_lenses(
        _as_dict(profile.get("evaluation_weights")),
        config_path=config_path,
    )
    profile["meta_value_lens_mapping_version"] = mapping["mapping_version"]
    profile["meta_value_lens_weights"] = mapping["lens_weights"]
    profile["meta_value_lens_names"] = mapping["lens_names"]
    profile["meta_value_lens_axes"] = mapping["lens_axes"]
    profile["meta_value_lens_axis_weights"] = mapping["lens_axis_weights"]
    profile["dominant_meta_value_lenses"] = mapping["dominant_lenses"]
    profile["unmapped_evaluation_axes"] = mapping["unmapped_source_weights"]
    return profile
