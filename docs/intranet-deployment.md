# 公司内网部署、升级与回滚

## 推荐交付方式

在开发机的 `crawler_system` 目录执行：

```powershell
npm run release:intranet
```

命令会在 `artifacts/intranet-package/` 生成一个可直接转交的 ZIP 和对应 `.zip.sha256`。包内包含生产镜像、React 与 FastAPI 源码、当前 SQLite 数据的在线一致性副本、快照、随机首登密码、版本清单和逐文件校验清单。随机密码只写入被忽略的本地发布产物，不进入 Git。

镜像只在这台开发/打包机上构建一次；构建时会下载基础镜像和系统依赖，因此打包机需要能访问 Docker Hub、Debian 和 Python/npm 软件源。目标内网服务器不再构建，也不会去镜像仓库拉取：`_system/deploy.ps1` 只校验并加载 ZIP 内的 `_system/images/production-images.tar`。如果该文件或其中的精确版本标签缺失，部署会直接报错，不会偷偷改为联网下载。

目标 Windows 电脑安装 Docker Desktop（Linux 容器模式）后，把 ZIP 解压到最终存放位置并直接双击：

```text
START-HERE.cmd
```

启动器会自动启动 Docker Desktop、等待 Linux 引擎、校验交付包、加载离线镜像、启动服务、登记当前 Windows 用户登录后的自动启动，并打开浏览器。包根目录只展示入口、首登凭据和说明，其余程序文件集中在 `_system`。首次部署会从 `_system/.env.production.initial` 生成活动配置，并从 `_system/seed` 初始化 `_system/runtime`；再次启动会跳过已经存在的同版本镜像。再次部署或升级不会覆盖活动配置和运行数据，只会同步新版镜像版本号。服务只暴露 `8093`，后端 `8000` 仅在容器内部使用。

首次安装只需双击一次 `START-HERE.cmd`；之后登录 Windows 时会在后台自动启动。使用纯英文入口名是为了兼容部分 Windows 服务器的中文代码页。不要在首次启动后移动部署文件夹，也不要在目标服务器上执行 `docker compose build` 或自行执行 `docker compose up`；`_system` 中的部署、状态、备份、停止和升级脚本只保留给 IT 运维使用。

容器使用 `restart: unless-stopped`。API 启动时会恢复固定来源、加载上海时区的采集计划，并补跑超过 24 小时未成功的启用来源；运行期间还会每 15 分钟检查失败来源，到达错误退避时间后自动重试。日常不需要逐个启用或运行任务；管理员页面只保留“立即刷新全部”作为临时手动刷新。

Windows 部署入口会自动读取宿主机系统代理，并把 `127.0.0.1` 代理地址转换为容器可访问的 `host.docker.internal`。采集器在全局代理失败时会自动尝试直连。若两条路径都失败，页面会保留具体错误，此时需要 IT 修复服务器 VPN、代理或目标域名外网白名单，而不是反复点击任务。

## 首次部署

服务器至少准备 4 核 CPU、8 GB 内存和 20 GB 可用磁盘，并允许访问需求中的目标采集网站。部署完成后用包内 `FIRST-LOGIN.txt` 登录并立即修改密码，然后安全删除该文件。浏览器访问 `http://服务器IP:8093/`；防火墙只需对公司内网放行配置的 Web 端口。数据库、快照和备份分别保存在 `_system/runtime/data`、`_system/runtime/storage`、`_system/runtime/backups`。

```powershell
.\_system\status.ps1
.\_system\backup.ps1
.\_system\stop.ps1
```

分别用于查看状态、创建一致性备份和安全停机。

## 健康检查与日志

```powershell
Invoke-RestMethod http://服务器IP:8093/health
docker compose --env-file .\_system\.env.production -f .\_system\compose.production.yml logs --tail 200 api
docker compose --env-file .\_system\.env.production -f .\_system\compose.production.yml logs --tail 100 web
```

健康接口应返回 `status=ok`、数据库可用、调度器运行。若采集异常，应先看系统页面的失败分类和下次重试时间，再检查 API 日志；不要用不断重启代替定位原因。

## 升级

1. 保存旧版本 ZIP 和 `.sha256`，用于需要时回滚。
2. 解压新版 ZIP，把新版目录内的文件覆盖到现有部署目录。新版不含活动的 `_system/.env.production` 和 `_system/runtime`，所以不会覆盖生产配置与数据。旧版平铺目录会在首次启动时自动复制到 `_system`，原文件不会立即删除。
3. 在现有部署目录执行：

```powershell
.\_system\verify.ps1
.\_system\upgrade.ps1
.\_system\status.ps1
```

`_system/upgrade.ps1` 会先创建 SQLite 一致性备份，再加载新版离线镜像并等待健康检查。数据库迁移在 API 启动时幂等执行。升级后仍需实际验证登录、公告筛选、个人关注、管理员修改和立即刷新全部。

API 会在启动时以及每天上海时间 03:30 自动备份并清理过期运行文件；升级仍应额外保留一份离线备份，不能只依赖容器内的自动保留周期。

## 回滚与恢复

程序回滚时，把保留的上一版发布包重新覆盖到部署目录并执行 `_system/upgrade.ps1`；活动配置和数据仍会保留。若必须恢复数据库：

1. 执行 `.\_system\stop.ps1`。
2. 复制 `_system/runtime/data/data.db` 留存当前故障现场。
3. 从 `_system/runtime/backups` 选择经完整性检查的 `.db`，复制为 `_system/runtime/data/data.db`。
4. 执行 `.\_system\deploy.ps1` 和 `.\_system\status.ps1`，再验证登录和关键业务流程。

不要在 API 容器运行时直接覆盖 SQLite 文件。公司域名、TLS 证书、服务器账号、防火墙和出口代理属于部署环境；如需 HTTPS，应由公司反向代理或网关终止 TLS，再转发到本系统 Web 端口。
