# Single-Prod 单机部署

这套路径专门给单机生产化使用，不依赖 `PostgreSQL`、`Redis`、`Prometheus`、`OTel Collector`。

## 适用范围

适合这些场景：

- 单台机器长期运行
- 私有小规模部署
- 先把 AnimoCerebro 主脑跑稳
- 暂时不做真正的多实例集群承载

## 组成

`single-prod` 默认只使用：

- `FastAPI + Uvicorn`
- `SQLite/WAL`
- 本地后台任务执行器
- 本地 workspace index
- SQLite 反思与运行时记忆

不默认启用：

- `PostgreSQL`
- `Redis`
- `Dramatiq` 外部 broker
- `Prometheus`
- `OpenTelemetry Collector`
- `cluster-core` 那套多容器依赖栈

## 快速启动

```bash
./scripts/single-prod.sh
```

如果当前环境还没有把 `animocerebro` 安装成全局命令，脚本会自动退回到：

```bash
python3 -m zentex.cli web start ...
```

默认会自动准备：

- 配置目录：`.animocerebro/single-prod`
- 工作目录：`.animocerebro/single-prod/workspace`
- 状态目录：`.animocerebro/single-prod/state`

默认入口：

- Web/API: `http://127.0.0.1:8899`
- 普通模式: `http://127.0.0.1:8899/console/basic`
- 专业模式: `http://127.0.0.1:8899/console/pro`

如果你要把单机版直接装进 Docker，而不是跑本机脚本，改用：

```bash
./scripts/single-prod-docker.sh build
./scripts/single-prod-docker.sh up
```

对应说明文档见：

- `docs/operability/SINGLE_PROD_DOCKER.md`

## 单机运维入口

备份：

```bash
./scripts/single-prod-backup.sh
```

- 默认导出到 `.animocerebro/single-prod/backups`
- 首次运行会自动生成 `.animocerebro/single-prod/backup.key`
- 备份底层直接复用现有 `package export`，不单独发明第二套格式

恢复：

```bash
./scripts/single-prod-restore.sh
```

- 不带参数时默认恢复最新一个 `.zpkg`
- 也可以显式传入某个备份包路径

日志：

```bash
./scripts/single-prod-logs.sh list
./scripts/single-prod-logs.sh tail
./scripts/single-prod-logs.sh path
```

- 日志轮转已经由运行时 `RotatingFileHandler` 自动处理
- 当前固定策略是单文件约 `1MB`，保留 `3` 个轮转文件
- `single-prod-logs.sh` 只负责查看，不重复造一套轮转机制

健康验证：

```bash
./scripts/single-prod-verify.sh
```

- 该脚本会直接加载 `single-prod` 配置并做一次本地健康检查
- 重点确认 `deployment_profile`、本地后台任务执行器、SQLite/WAL 状态和 workspace index 可用

严格压测：

```bash
./scripts/single-prod-pressure.sh
```

- 该脚本会真正启动 `single-prod` Web/API，并按固定门槛执行 `SP-BASELINE / SP-SUSTAINED / SP-LARGE-WORKSPACE / SP-EDGE / SP-RECOVERY`
- 输出固定生成 `json + markdown` 报告，结论分为 `PASS / WARN / FAIL`
- 严格压测的权威说明和最近一次实测结果统一维护在 [13-单实例与集群压测说明.md](../../测试文档/13-单实例与集群压测说明.md)

## 自定义端口

```bash
ANIMOCEREBRO_HOST=0.0.0.0 ANIMOCEREBRO_PORT=9000 ./scripts/single-prod.sh
```

## 样例配置

样例模板在：

- `deploy/single-prod/animocerebro_vision.single-prod.yaml`

这个模板固定为：

- `deployment_profile: single-prod`
- `reflection_backend: sqlite`
- `runtime_memory_backend: sqlite`
- `state_database_url: ""`
- `cache_url: ""`
- `queue_backend_url: ""`

也就是说，单机默认只走本地 SQLite，不引入外部基础设施。

## 与 cluster-core 的区别

`single-prod`：

- 目标是“单机可长期稳定运行”
- 优先降低复杂度
- 不要求外部服务
- 现在已经有独立的 `single-prod-docker.sh` 和 `docker/single-prod/compose.yml`

`cluster-core`：

- 目标是“多实例承载同一个逻辑脑”
- 需要外部状态和缓存服务
- 需要更完整的观测与编排
- 继续使用 `cluster-core-docker.sh` 和 `docker/cluster-core/compose.yml`

如果你的目标只是单机稳定跑，优先用 `single-prod`，不要直接上 `cluster-core`。 
