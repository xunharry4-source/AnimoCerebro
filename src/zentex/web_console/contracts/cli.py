from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class CliToolItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    command_name: str
    description: str
    mapped_domain: str
    plugin_id: str
    feature_code: str
    execution_domain: Optional[str] = None
    read_only: bool = True
    side_effect_free: bool = True
    mutates_state: bool = False
    requires_cloud_audit: bool = False
    status: str
    help_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None


class CliToolRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tool_name: str = Field(min_length=1)
    command_executable: str = Field(min_length=1)
    command_args: list[str] = Field(default_factory=list)
    description: str = Field(min_length=1)
    read_only_flag: bool = True
    help_doc_url: Optional[str] = None
    project_path: Optional[str] = None
    project_name: Optional[str] = None
    project_description: Optional[str] = None
    execution_domain: str = "cli"
    env: dict[str, str] = Field(default_factory=dict)


class CliToolTestCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: list[str] = Field(default_factory=list)
    stdin_input: Optional[str] = None
    working_directory: Optional[str] = None
    timeout_seconds: float = Field(default=15.0, gt=0.0, le=120.0)


class CliToolTestCallResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str
    status: str
    trace_id: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command_line: list[str] = Field(default_factory=list)
    working_directory: Optional[str] = None
