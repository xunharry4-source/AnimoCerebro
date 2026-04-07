from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import AliasChoices, Field, model_validator
from pydantic.fields import FieldInfo

from zentex.core.plugin_base import FunctionalPluginSpec, LogicalCognitivePluginSpec


@dataclass(frozen=True)
class BrainRuntimeState:
    runtime_id: str
    started_at: datetime
    active_session_ids: List[str]
    default_workspace: Optional[str]
    identity_kernel_ref: Optional[str]
    tool_registry_version: Optional[str]
    transcript_store_status: str
    memory_store_status: str
    read_only_mode: bool
    degraded_mode: bool
    manual_confirmation_required: bool
    last_runtime_snapshot_at: datetime


class CognitiveToolSpec(FunctionalPluginSpec):
    """
    Unified contract for cognitive-only plugins.

    Cognitive tools are internal thinking aids. They may inspect, compare,
    decompose, and rank. They may never execute external actions.

    ── supports_multiple_plugins 字段使用规范 ────────────────────────────────
    正确字段名：supports_multiple_plugins（旧名 supports_multi_active 已废弃）

    ⚠️  子类禁止直接重新声明该字段（如 supports_multiple_plugins: bool = True）。
       Pydantic v2 的字段继承规则：子类重新声明会覆盖父类的 Field(...)，
       包括 validation_alias=AliasChoices(...)。一旦 alias 被清除，
       用关键字参数 supports_multi_active=... 构造任何子类实例都会触发
       "Extra inputs are not permitted" 校验错误，且该错误只在运行期
       实际构造实例时才暴露，编码阶段不报任何警告。

    ✅  如需在子类固定 True，只在 factory 函数里传 supports_multiple_plugins=True。
    ✅  如需在子类修改默认值，使用：
           supports_multiple_plugins: bool = Field(
               default=True,
               validation_alias=AliasChoices(
                   "supports_multiple_plugins", "supports_multi_active"
               ),
           )
    ─────────────────────────────────────────────────────────────────────────
    """

    tool_type: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    required_context: list[str]
    trigger_conditions: list[str]
    behavior_key: str = Field(min_length=1)
    supports_multiple_plugins: bool = Field(
        default=False,
        validation_alias=AliasChoices("supports_multiple_plugins", "supports_multi_active"),
    )
    is_default_version: bool = False
    is_official_release: bool = True
    do_not_use_when: list[str]
    read_only: bool = True
    side_effect_free: bool = True

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # 检测子类是否用裸值重新声明了 supports_multiple_plugins。
        #
        # 背景（2026-04 事故）：子类写 `supports_multiple_plugins: bool = True`
        # 会让 Pydantic v2 用裸 bool 值覆盖父类的 Field(..., validation_alias=
        # AliasChoices(...))。alias 丢失后，任何用 supports_multi_active= 关键字
        # 构造该子类实例的 factory 函数都会在运行期得到
        # "Extra inputs are not permitted" 错误，且只在实际实例化时才暴露。
        #
        # 检测时机：Pydantic ModelMetaclass 处理完字段后才调用 __init_subclass__，
        # 此时 cls.__dict__['supports_multiple_plugins'] 是原始的 bool/FieldInfo，
        # 而不是已合并的 model_fields（后者在此时刻仍反映父类的 alias）。
        val = cls.__dict__.get("supports_multiple_plugins")
        if val is not None:
            alias_ok = isinstance(val, FieldInfo) and val.validation_alias is not None
            if not alias_ok:
                raise TypeError(
                    f"{cls.__name__} 不可在子类中用裸值重新声明 `supports_multiple_plugins`。\n"
                    "这会覆盖父类 Field 的 validation_alias，导致用 supports_multi_active= "
                    "构造该子类时在运行期触发 'Extra inputs are not permitted' 错误。\n"
                    "修复方案：\n"
                    "  1. 删除子类中的 `supports_multiple_plugins: bool = True`，"
                    "在 factory 函数里改为传 supports_multiple_plugins=True。\n"
                    "  2. 若确需子类固定默认值，使用完整的 Field：\n"
                    "     supports_multiple_plugins: bool = Field(\n"
                    "         default=True,\n"
                    "         validation_alias=AliasChoices(\n"
                    '             "supports_multiple_plugins", "supports_multi_active"\n'
                    "         ),\n"
                    "     )"
                )

    @classmethod
    def plugin_kind(cls) -> str:
        return "cognitive_tool"

    @model_validator(mode="after")
    def validate_cognitive_boundaries(self) -> "CognitiveToolSpec":
        if self.read_only is not True or self.side_effect_free is not True:
            raise ValueError(
                "Cognitive tools must be strictly read_only=True and side_effect_free=True"
            )
        if not self.trigger_conditions:
            raise ValueError("Cognitive tools must declare trigger_conditions")
        if not self.do_not_use_when:
            raise ValueError("Cognitive tools must declare do_not_use_when")
        return self


class LogicalCognitiveToolSpec(LogicalCognitivePluginSpec):
    """
    Orchestrator contract for top-layer reasoning plugins such as Q1-Q9.

    These plugins may consult functional plugins through the registry, but they
    remain read-only reasoning components and do not perform side effects.
    """

    tool_type: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    required_context: List[str]
    trigger_conditions: List[str]
    behavior_key: str = Field(min_length=1)
    supports_multiple_plugins: bool = Field(
        default=False,
        validation_alias=AliasChoices("supports_multiple_plugins", "supports_multi_active"),
    )
    is_default_version: bool = False
    is_official_release: bool = True
    do_not_use_when: List[str]
    read_only: bool = True
    side_effect_free: bool = True

    @classmethod
    def plugin_kind(cls) -> str:
        return "cognitive_tool"

    @model_validator(mode="after")
    def validate_logical_cognitive_boundaries(self) -> "LogicalCognitiveToolSpec":
        if self.read_only is not True or self.side_effect_free is not True:
            raise ValueError(
                "Logical cognitive plugins must be strictly read_only=True and side_effect_free=True"
            )
        if not self.trigger_conditions:
            raise ValueError("Logical cognitive plugins must declare trigger_conditions")
        if not self.do_not_use_when:
            raise ValueError("Logical cognitive plugins must declare do_not_use_when")
        return self
