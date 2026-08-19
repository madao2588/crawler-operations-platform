# Crawler System

Crawler System 是面向运营场景的采集平台。后端使用 FastAPI，前端使用 React。

说明：仓库根目录的 `npm start` 会转发到 `crawler_system`，最终启动行为与下表一致。

## 启动约定

| 命令 | 作用 | 端口 |
| --- | --- | --- |
| `npm start` | 启动 FastAPI + React | 后端 `8000` / 前端 `8093` |
| `npm stop` | 停止当前组合 | - |

## 当前功能

- 登录与会话恢复
- 任务创建、编辑、启停、立即执行
- 抓取、解析、清洗、去重、快照保存
- 公告中心、看板统计、日志摘录
- 模板管理、关键词规则管理
- CSV 导出

## 快速开始

1. 准备环境变量

```powershell
$env:CRAWLER_BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:CRAWLER_BOOTSTRAP_ADMIN_PASSWORD = "change-this-password"
```

2. 启动本地组合

```powershell
npm start
```

3. 如果本机 `8000` 或 `8093` 已被占用

```powershell
npm start -- -BackendPort 18000 -FrontendPort 18093
```

4. 停止当前组合

```powershell
npm stop
```

5. 运行本地校验

```powershell
.\scripts\dev-check.ps1
```

这条校验链会依次执行：

- 后端 `pytest -q`
- React 前端 `typecheck`
- React 前端 `test`
- React 前端 `build`

## 关键环境变量

- `CRAWLER_BOOTSTRAP_ADMIN_USERNAME`
- `CRAWLER_BOOTSTRAP_ADMIN_PASSWORD`
- `CRAWLER_CORS_ALLOWED_ORIGINS`
- `CRAWLER_CORS_ALLOWED_ORIGIN_REGEX`
- `CRAWLER_OUTBOUND_PROXY_URL`
- `CRAWLER_USE_SYSTEM_PROXY`
- `CRAWLER_OUTBOUND_NO_PROXY`
- `CRAWLER_AUTOMATIC_RETRY_MINUTES`
- `VITE_API_BASE_URL`
- `API_BASE_URL`

说明：

- React 默认通过同源代理访问 `/v1/*` 和 `/health`，本地联调通常不需要额外配置 `VITE_API_BASE_URL`。
- 如果要把 React 静态包部署到独立域名，而 API 在另一个域名上，请在构建时设置 `VITE_API_BASE_URL`。
- `API_BASE_URL` 可用于本地联合启动时显式指定后端地址。
- Windows 离线部署入口会自动读取当前系统代理；当代理监听在 `127.0.0.1` 时，会转换成容器可访问的 `host.docker.internal`。下载器会在全局代理和直连之间自动回退，任务级显式代理除外。
- `CRAWLER_OUTBOUND_NO_PROXY` 默认只包含本机地址。若公司有内网域名需要直连，可以追加；不要把需要 VPN/代理才能访问的目标网站加入该列表。
- 失败来源每 15 分钟检查一次，到达错误退避时间后自动重试，不需要逐项点击。代理和直连都失败时，仍需由 IT 修复服务器的 VPN、代理或外网白名单。

## 固定需求来源状态

- 需求 1：7 个政府站点自动采集，分别保留站点级状态、错误原因和重试记录。
- 需求 2：丁香会议、中国药学会、生物谷、CPHI 覆盖会议列表与详情；生物谷来源可能触发验证码，默认不做绕过。
- 需求 3：PubMed 通过 NCBI 官方接口自动采集；摩熵医药需要合法授权账号或授权导出。

## 本地开发说明

仓库内置统一的本地启动与校验脚本：

- [scripts/dev-up.ps1](scripts/dev-up.ps1)
- [scripts/dev-check.ps1](scripts/dev-check.ps1)

详情见：

- [docs/local-dev.md](docs/local-dev.md)

## 部署路径

公司内网推荐使用一体化生产包：Nginx 托管 React 并同源代理 FastAPI，只开放一个 Web 端口。构建包含当前数据、快照、随机首登密码和离线 Docker 镜像的可交付 ZIP：

```powershell
npm run release:intranet
```

产物位于 `artifacts/intranet-package/`。Docker 镜像在开发/打包机上构建并随 ZIP 交付；目标 Windows 电脑解压到最终位置后只需双击一次 `START-HERE.cmd`，启动器会自动启动 Docker、校验并部署、登记当前用户登录后自动启动，并打开网页。根目录只展示入口、说明和首登凭据，程序与运行数据集中在 `_system`。部署阶段禁止重新构建和联网拉取镜像。首次安装程序依赖无需联网，正式运行时采集外部网站仍需要受控的互联网出口。固定来源随服务自动恢复并按上海时间采集，日常不需逐项启用；升级时由 IT 运行 `_system/upgrade.ps1`，已有活动配置和运行数据不会被覆盖。

部署说明见：

- [docs/deployment.md](docs/deployment.md)
- [docs/intranet-deployment.md](docs/intranet-deployment.md)
- [web/README.md](web/README.md)

## 目录

```text
crawler_system/
|-- server/
|-- web/
|-- scripts/
|-- docs/
|-- docker-compose.yml
`-- README.md
```
