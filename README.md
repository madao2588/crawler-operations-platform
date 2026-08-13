# Crawler System

Crawler System 是面向运营场景的采集平台。后端使用 FastAPI，默认前端使用 React。Flutter 仅保留为显式回退入口，不再作为 `npm start` 的默认模式。

说明：仓库根目录的 `npm start` 会转发到 `crawler_system`，最终启动行为与下表一致。

## 启动约定

| 命令 | 作用 | 端口 |
| --- | --- | --- |
| `npm start` | 启动 FastAPI + React | 后端 `8000` / 前端 `8093` |
| `npm run start:react` | 显式启动 React 组合 | 后端 `8000` / 前端 `8093` |
| `npm run start:flutter` | 启动 FastAPI + Flutter 回退组合 | 后端 `8000` / 前端 `8093` |
| `npm stop` | 停止当前组合 | - |
| `npm run stop:flutter` | 停止 Flutter 回退组合 | - |

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
- Flutter `analyze`
- Flutter `test`

## 前端模式切换

- 默认模式：`npm start`
- 显式 React：`npm run start:react`
- 显式 Flutter 回退：`npm run start:flutter`
- 停止当前组合：`npm stop`
- 停止 Flutter 回退：`npm run stop:flutter`

## 关键环境变量

- `CRAWLER_BOOTSTRAP_ADMIN_USERNAME`
- `CRAWLER_BOOTSTRAP_ADMIN_PASSWORD`
- `CRAWLER_CORS_ALLOWED_ORIGINS`
- `CRAWLER_CORS_ALLOWED_ORIGIN_REGEX`
- `CRAWLER_OUTBOUND_PROXY_URL`
- `CRAWLER_USE_SYSTEM_PROXY`
- `CRAWLER_OUTBOUND_NO_PROXY`
- `VITE_API_BASE_URL`
- `API_BASE_URL`
- `CRAWLER_FLUTTER_ROOT`

说明：

- React 默认通过同源代理访问 `/v1/*` 和 `/health`，本地联调通常不需要额外配置 `VITE_API_BASE_URL`。
- 如果要把 React 静态包部署到独立域名，而 API 在另一个域名上，请在构建时设置 `VITE_API_BASE_URL`。
- `API_BASE_URL` 仅供 Flutter 回退构建脚本使用。
- Windows 默认代理、TUN 或 Fake-IP 场景下，爬虫和 Playwright 可能会继承系统代理；需要显式直连时，请同步设置 `CRAWLER_OUTBOUND_PROXY_URL`、`CRAWLER_USE_SYSTEM_PROXY` 和 `CRAWLER_OUTBOUND_NO_PROXY`。
- 需求 1 的 7 个政府来源已纳入默认直连列表。若使用 Clash/Vortex 一类 TUN 代理，运行模式必须是 `rule`，并确保这些域名命中 `DIRECT`；`global` 模式会忽略域名直连规则，导致站点看似全部不可用。

## 固定需求来源状态

- 需求 1：7 个政府站点自动采集；2 个公众号不纳入自动采集验收，由使用人员自行查询，现有文章链接登记仅作为可选辅助入口。
- 需求 2：丁香会议、中国药学会、生物谷、CPHI 覆盖会议列表与详情；生物谷来源可能触发验证码，默认不做绕过。
- 需求 3：PubMed 通过 NCBI 官方接口自动采集；摩熵医药需要合法授权账号或授权导出；公众号竞品线索由使用人员自行查询，可选使用人工链接登记。

## 本地开发说明

系统 Flutter SDK 在这台机器上是只读安装，不能直接稳定执行 `flutter`。仓库内置了 wrapper：

- [scripts/flutterw.ps1](scripts/flutterw.ps1)
- [scripts/dev-up.ps1](scripts/dev-up.ps1)
- [scripts/dev-check.ps1](scripts/dev-check.ps1)

详情见：

- [docs/local-dev.md](docs/local-dev.md)

## 部署路径

公司内网推荐使用一体化生产包：Nginx 托管 React 并同源代理 FastAPI，只开放一个 Web 端口。构建包含当前数据、快照、随机首登密码和离线 Docker 镜像的可交付 ZIP：

```powershell
npm run release:intranet
```

产物位于 `artifacts/intranet-package/`。目标机解压后依次执行 `verify.ps1`、`deploy.ps1`；首次安装程序依赖无需联网，采集外部网站仍需要受控的互联网出口。升级时覆盖程序文件并运行 `upgrade.ps1`，已有 `.env.production` 和 `runtime` 不会被覆盖。

部署说明见：

- [docs/deployment.md](docs/deployment.md)
- [docs/intranet-deployment.md](docs/intranet-deployment.md)
- [web/README.md](web/README.md)

## 目录

```text
crawler_system/
|-- server/
|-- web/
|-- frontend/
|-- scripts/
|-- docs/
|-- docker-compose.yml
`-- README.md
```
