# model_provider_tools

- Name: Provider Tools Model Adapter
- Description: Exposes configured LLM providers to Zentex and delegates real calls to the unified LLM gateway.

## 功能

这个插件的作用是把 `config/provider_tools.yml` 中已经配置好的 provider 暴露给 Zentex 运行时。

它的核心职责是：
- 读取 provider 配置，例如 `provider_name`、`api_base`、`api_key_env`、`default_model`
- 让系统知道当前有哪些 LLM provider 可以被统一入口使用
- 为以后通过插件扩展更多 provider 留出位置，例如千问、DeepSeek、其他 OpenAI-compatible 网关

它不是一套独立的 LLM 请求实现。

## 正确使用方式

正确方式：
- 业务代码统一通过 `zentex.llm.gateway.LLMGateway`
- 或通过 `zentex.llm.service.LLMService`
- `provider_key` 的默认值来自 `config/provider_tools.yml` 的 `default_provider`

这意味着：
- plugin 负责“提供 provider 能力”
- gateway/service 负责“真正访问 LLM”

## 错误使用方式

以下用法是错误的：
- 把这个 plugin 当成独立于 `LLMGateway` 之外的第二套请求入口
- 在业务代码里直接把 plugin 当作主调用面来设计新的 LLM 流程
- 在 plugin 内部硬编码 provider 配置，绕过 `config/provider_tools.yml`
- 把它理解成“替代统一网关的请求方式”

## 配置来源

本插件的默认 provider 选择和 provider 细节都来自：

- [config/provider_tools.yml](/Users/harry/Documents/git/AnimoCerebro-V2/config/provider_tools.yml)

其中：
- `default_provider` 决定未显式传 `provider_key` 时默认用哪个 provider
- `providers.<name>` 定义每个 provider 的 `api_base`、`api_key_env`、`default_model`

## 设计边界

如果未来要通过插件支持更多大模型，例如千问，正确做法是：
- 在 provider tools 配置和适配层里新增该 provider
- 让 `LLMGateway` 能够选择并调用它
- 保持业务层调用入口不变

也就是说，扩展的是“provider 能力”，不是“增加新的调用路径”。

## Required Files

- `startup.py`
- `plugin.json`
- `register.py`
- `README.md`
