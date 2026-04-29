# 外部插件目录 / External plugins directory

## 中文

本目录（仓库根目录下的 `plugins/`）用于存放**外部插件**：在工程上**完全独立、专用**，**不依赖** `src/` 下的应用代码（包括但不限于 `src/zentex`）。  
可将第三方包、独立进程、脚本或资源放在此处；与 Zentex 主工程的集成应通过约定接口、配置或进程间通信完成，而不是在代码上 import `src`。

## English

This directory (`plugins/` at the repository root) holds **external plugins**: they are **fully standalone and dedicated**, and **must not depend** on code under `src/` (including but not limited to `src/zentex`).  
You may place third-party packages, separate processes, scripts, or assets here. Integration with the main Zentex project should use agreed APIs, configuration, or IPC—not Python imports from `src`.
