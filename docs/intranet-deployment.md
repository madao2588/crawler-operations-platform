# 公司内网部署、升级与回滚

## 推荐交付方式

在开发机的 `crawler_system` 目录执行：

```powershell
npm run release:intranet
```

命令会在 `artifacts/intranet-package/` 生成一个可直接转交的 ZIP 和对应 `.zip.sha256`。包内包含生产镜像、React 与 FastAPI 源码、当前 SQLite 数据的在线一致性副本、快照、随机首登密码、版本清单和逐文件校验清单。随机密码只写入被忽略的本地发布产物，不进入 Git。

目标 Windows 电脑安装并启动 Docker Desktop（Linux 容器模式）后，解压 ZIP，在目录中执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\verify.ps1
.\deploy.ps1
```

首次部署会从 `.env.production.initial` 生成活动的 `.env.production`，并从 `seed` 初始化 `runtime`；再次部署或升级不会覆盖这两个活动目录，只会在环境文件中同步新版镜像版本号。服务只暴露 `8093`，后端 `8000` 仅在容器内部使用。

## 首次部署

服务器至少准备 4 核 CPU、8 GB 内存和 20 GB 可用磁盘，并允许访问需求中的目标采集网站。部署完成后用包内 `FIRST-LOGIN.txt` 登录并立即修改密码，然后安全删除该文件。浏览器访问 `http://服务器IP:8093/`；防火墙只需对公司内网放行配置的 Web 端口。数据库、快照和备份分别保存在 `runtime/data`、`runtime/storage`、`runtime/backups`。

```powershell
.\status.ps1
.\backup.ps1
.\stop.ps1
```

分别用于查看状态、创建一致性备份和安全停机。

## 健康检查与日志

```powershell
Invoke-RestMethod http://服务器IP:8093/health
docker compose --env-file .env.production -f compose.production.yml logs --tail 200 api
docker compose --env-file .env.production -f compose.production.yml logs --tail 100 web
```

健康接口应返回 `status=ok`、数据库可用、调度器运行。若采集异常，应先看系统页面的失败分类和下次重试时间，再检查 API 日志；不要用不断重启代替定位原因。

## 升级

1. 保存旧版本 ZIP 和 `.sha256`，用于需要时回滚。
2. 解压新版 ZIP，把新版目录内的文件覆盖到现有部署目录。新版不含活动的 `.env.production` 和 `runtime`，所以不会覆盖生产配置与数据。
3. 在现有部署目录执行：

```powershell
.\verify.ps1
.\upgrade.ps1
.\status.ps1
```

`upgrade.ps1` 会先创建 SQLite 一致性备份，再加载新版离线镜像并等待健康检查。数据库迁移在 API 启动时幂等执行。升级后仍需实际验证登录、公告筛选、个人关注、管理员修改和一键更新。

API 会在启动时以及每天上海时间 03:30 自动备份并清理过期运行文件；升级仍应额外保留一份离线备份，不能只依赖容器内的自动保留周期。

## 回滚与恢复

程序回滚时，把保留的上一版发布包重新覆盖到部署目录并执行 `upgrade.ps1`；活动配置和数据仍会保留。若必须恢复数据库：

1. 执行 `.\stop.ps1`。
2. 复制 `runtime/data/data.db` 留存当前故障现场。
3. 从 `runtime/backups` 选择经完整性检查的 `.db`，复制为 `runtime/data/data.db`。
4. 执行 `.\deploy.ps1` 和 `.\status.ps1`，再验证登录和关键业务流程。

不要在 API 容器运行时直接覆盖 SQLite 文件。公司域名、TLS 证书、服务器账号、防火墙和出口代理属于部署环境；如需 HTTPS，应由公司反向代理或网关终止 TLS，再转发到本系统 Web 端口。
