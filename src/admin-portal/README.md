# Admin Portal

This directory contains the source code for the Zentex Administrative Dashboard, built with React and Vite.
- **`src/pages`**: UI implementations for system monitoring, plugin management, and Nine Questions visualization.
- **`src/api`**: Client-side API calls to the Web Console backend.

Important boundary:
- This portal is a monitoring and audit surface, not the runtime source of truth.
- Product/runtime semantics must be defined by kernel/runtime services, not by frontend routes, browser state, or web-specific identifiers.

---

# 管理后台目录

该目录包含 Zentex 后端管理系统的源码，基于 React 与 Vite 构建。
- **`src/pages`**: 实现系统监控、插件管理以及九阶段认知模型的可视化界面。
- **`src/api`**: 针对 Web Console 后端的 API 调用封装。

重要边界说明：
- 该前端只是监控与审计界面，不是运行时真相来源。
- 任何产品语义、九问状态语义、运行实例语义，都不能由前端路由、浏览器状态或 Web 专属标识来定义。
