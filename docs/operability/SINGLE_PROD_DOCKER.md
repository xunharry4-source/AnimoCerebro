# Single-Prod Docker 环境

本目录提供 `single-prod` 的独立 Docker 脚手架，会一起启动：

- `single-prod` Web/API
- 本地 `cloud-audit` 服务

但不会拉起 `PostgreSQL`、`Redis`、`Prometheus`、`OTel Collector` 或 worker。

相关文件：

- `docker/single-prod/compose.yml`
- `docker/Dockerfile.single-prod`
- `docker/single-prod/animocerebro_vision.single-prod.yaml`
- `scripts/single-prod-docker.sh`

## 快速启动

```bash
cp docker/single-prod/.env.example docker/single-prod/.env
./scripts/single-prod-docker.sh build
./scripts/single-prod-docker.sh up
```

说明：

- `scripts/single-prod-docker.sh` 优先读取 `docker/single-prod/.env`，不存在时回退到 `docker/single-prod/.env.example`
- `up` 默认只启动，不重新构建镜像，适合测试阶段反复验证
- `build` 只构建镜像，不启动容器
- `rebuild` 才会执行 `up --build`，适合依赖或 Dockerfile 变化后强制重建
- 容器启动时会自动准备 `.animocerebro/docker-single-prod/{workspace,state,backups}`
- 如果宿主卷里还没有配置文件，会自动把镜像内的 `animocerebro_vision.single-prod.yaml` 复制到宿主目录
- `audit` 服务和 `single-prod` 服务都会先执行 `animocerebro audit init-local`，把本地云审计配置和凭据写进运行时配置，再由 `audit` 容器真正启动 `animocerebro audit start-local`

默认入口：

- Web/API: `http://127.0.0.1:18898`
- 宿主数据目录：`.animocerebro/docker-single-prod`

## 管理命令

```bash
./scripts/single-prod-docker.sh build
./scripts/single-prod-docker.sh ps
./scripts/single-prod-docker.sh logs
./scripts/single-prod-docker.sh rebuild
./scripts/single-prod-docker.sh down
```

## 与 cluster-core Docker 的区别

`single-prod Docker`：

- 会起 `single-prod + audit` 两个容器
- 只用本地 SQLite/WAL 和本地后台任务执行器
- 宿主数据目录固定为 `.animocerebro/docker-single-prod`
- 适合单机长期运行或先做低复杂度部署

`cluster-core Docker`：

- 会起 `api / worker / migrate / postgres / redis / prometheus / otel-collector`
- 依赖外部状态、缓存、队列与观测组件
- 宿主数据目录固定为 `.animocerebro/docker-cluster-core`
- 适合多实例承载和 cluster-core 联调

如果你的目标只是“把当前版本装进 Docker 单机跑”，优先用 `single-prod-docker.sh`；只有确实需要队列、worker、数据库和观测组件时，再用 `cluster-core-docker.sh`。
