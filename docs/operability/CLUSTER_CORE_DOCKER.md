# Cluster-Core Docker 环境

本目录提供 `cluster-core` 的外部依赖 Docker 脚手架，用于一次性起出：

- `PostgreSQL`
- `Redis`
- `OpenTelemetry Collector`
- `Prometheus`
- `Local Cloud Audit`
- `AnimoCerebro API`
- `AnimoCerebro Worker`

相关文件：

- `docker/cluster-core/compose.yml`
- `docker/Dockerfile.cluster-core`
- `docker/cluster-core/animocerebro_vision.cluster-core.yaml`
- `docker/cluster-core/animocerebro_vision.cluster-ha.yaml`
- `docker/cluster-core/prometheus.yml`
- `docker/cluster-core/otel-collector.yml`
- `scripts/cluster-core-docker.sh`
- `scripts/cluster-core-smoke.sh`
- `scripts/cluster-core-preflight.sh`
- `scripts/cluster-core-fault-drill.sh`

## 快速启动

```bash
cp docker/cluster-core/.env.example docker/cluster-core/.env
scripts/cluster-core-docker.sh build
scripts/cluster-core-docker.sh up
```

说明：

- `scripts/cluster-core-docker.sh` 现在优先读取 `docker/cluster-core/.env`，不存在时才回退到 `docker/cluster-core/.env.example`
- `up` 默认只启动，不重新构建镜像，适合测试阶段复用已存在镜像层
- `build` 只构建镜像，不启动容器
- `rebuild` 才会执行强制重建并启动，适合依赖变化后刷新镜像缓存
- Docker 场景默认把 `ZENTEX_OPENCLAW_BRIDGE_ALLOW_NON_LOOPBACK=true` 写进示例环境文件，避免“同机但跨 Docker 网桥”被误判成非法远程来源
- 如果你明确只允许纯 loopback 访问，可以在 `docker/cluster-core/.env` 里把该值改回 `false`

默认入口：

- Web/API: `http://127.0.0.1:8899`
- Prometheus: `http://127.0.0.1:19090`
- PostgreSQL: `127.0.0.1:5432`
- Redis: `127.0.0.1:6379`

默认角色分工：

- `audit`：先做 `audit init-local` 写入运行时配置，再提供本地 cloud-audit 服务
- `api`：`gateway`，只负责 HTTP/API、排队和读取快照，不直接执行脑循环
- `worker`：`leader + worker`，负责消费 Redis 队列并执行 `brain_tick/replan` 等后台任务

## OpenClaw Bridge 注意事项

如果 OpenClaw 宿主不在同一个网络命名空间内，即使它和 Docker 里的 API 在同一台机器上，AnimoCerebro 看到的源地址也可能是 `172.x` 之类的容器网段，而不是 `127.0.0.1`。

这时如果 `ZENTEX_OPENCLAW_BRIDGE_ALLOW_NON_LOOPBACK=false`，bridge 会返回：

- `OpenClaw 大脑桥当前只允许本机 loopback 访问。`

因此 Docker 或 split-process 场景应至少满足：

```bash
ZENTEX_OPENCLAW_BRIDGE_TOKEN=<长随机 token>
ZENTEX_OPENCLAW_BRIDGE_ALLOW_NON_LOOPBACK=true
```

放开非 loopback 后，bridge token 就是主要防线，建议同时配合：

- 只绑定内网或本机开发网段
- 反向代理 / TLS
- IP 白名单或 VPN

## 真实 Smoke Test

建议先跑预检：

```bash
scripts/cluster-core-preflight.sh
```

启动并验证整套真实栈：

```bash
scripts/cluster-core-smoke.sh
```

如果只想复用已经跑着的栈：

```bash
scripts/cluster-core-smoke.sh --skip-up
```

如果你想在 smoke 结束后保留容器：

```bash
scripts/cluster-core-smoke.sh --keep-up
```

该脚本会实际检查：

- `migrate -> api -> worker` 启动链路
- `GET /api/web/system/health`
- `GET /api/web/system/cluster/state`
- 重复 `POST /api/web/system/brain-runs` 的幂等复用
- worker 真实消费并完成任务
- `GET /api/web/overview` 与 `GET /api/web/goals/tree`
- PostgreSQL 中 `alembic_version` 与 `workspace_index_entries.modified_ns=bigint`

说明：

- `/api/web/system/cluster/state`、`/api/web/system/coordination`、`/api/web/system/brain-runs` 默认现在只返回轻量 summary。
- 如果需要深度诊断 payload，统一使用 `?detail=full`。
- smoke 脚本在需要完整断言的场景下已经固定改用 `detail=full`，避免把调试 payload 重新放回默认热路径。

## 故障演练

在 smoke 通过后，可以直接执行一轮基础故障演练：

```bash
scripts/cluster-core-fault-drill.sh --skip-up
```

该脚本当前会覆盖：

- 模拟器注入：`leader_loss`、`cache_storm`、`queue_backlog`、`database_slow`
- 模拟器 rollback
- `worker` 容器重启
- `redis` pause / unpause

## 严格压测

在 smoke 通过后，可以直接执行一轮严格压测：

```bash
./scripts/cluster-core-pressure.sh
```

如果你要复用已经跑着的栈：

```bash
./scripts/cluster-core-pressure.sh --skip-up
```

如果你要单独生成 `cluster-ha` 的严格压测阻塞报告：

```bash
./scripts/cluster-ha-pressure.sh
```

该脚本会固定执行：

- `CC-BASELINE / CC-ELEVATED / CC-SUSTAINED / CC-MIXED / CC-STALE-SNAPSHOT`
- `CC-FAULT-AFTER-LOAD`：负载过程中插入 `fault-drill`
- `CC-RECOVERY`：故障回滚后的恢复压测
- `CC-DEAD-LETTER`：队列级 dead-letter 不阻塞主链的 harness

输出固定生成 `json + markdown` 报告，结论分为 `PASS / WARN / FAIL`。  
`cluster-ha` 现在也有统一入口，但如果当前仍缺正式 rollout/rollback 自动化，会在报告里明确标成 `FAIL/未完成`，不会伪装成“已覆盖”。

最近一次修复后复测表明：

- 默认热路径 payload 已显著缩小，`CC-BASELINE` 从 `FAIL` 收到 `WARN`
- 但 `CC-ELEVATED` 及之后的场景仍普遍受制于协调读取、心跳更新和 brain-runs 写路径延迟
- 当前 cluster-core 的剩余问题已经从“返回体过大”转成“高并发下状态链本身过慢”

严格压测的权威说明和最近一次实测结果统一维护在 [13-单实例与集群压测说明.md](../../测试文档/13-单实例与集群压测说明.md)。

真实 `cluster-ha` 的更深接管演练仍然建议在独立环境里补完整矩阵，但这套脚本已经把“smoke 之后最小可重复 drill”固定下来了。

如果要切到更保守的高可用档位，可以把配置切到：

- `docker/cluster-core/animocerebro_vision.cluster-ha.yaml`

## 当前边界

这套 Docker 脚手架现在已经包含 API、worker、PostgreSQL、Redis、Prometheus、OTel Collector 的固定编排，并且 cluster 核心代码已经接上：

- Redis-backed queue
- Redis/PostgreSQL 协调器
- 节点注册/心跳/draining
- cluster state 接口
- Alembic baseline
- Locust 压测脚手架

当前仍然保留的后续增强，不再是“有没有集群骨架”，而是更深的工程化验收：

- 完整故障演练矩阵
- 更细的租户/密级/运营权限隔离
- 更完整的 cluster-ha 联调和 rollout 自动化

关于后台 runtime：

- 代码已经暴露 `Dramatiq actor` 目标态的 runtime 信息与 actor 集合
- 当前环境若未安装 `dramatiq`，worker 会明确回退到现有 Redis queue worker 路径
- 一旦运行环境补齐 `dramatiq` 依赖，cluster worker 会优先切到目标 runtime

也就是说，当前 Docker 栈已经从“联调底座”推进到“可运行 cluster-core 栈”，不需要再临时补 PostgreSQL / Redis / OTel / Prometheus / worker 环境。 
