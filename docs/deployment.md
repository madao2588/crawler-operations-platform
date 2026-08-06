# 部署

## 推荐方式

当前推荐且已验证的部署方式是：

- 后端独立部署为 FastAPI API 服务
- 前端独立构建为 React 静态站点

不要把 Flutter 前端构建链耦合进后端容器启动流程。Flutter 仍然可以作为显式回退入口，但不是默认部署目标。

## 1. 准备环境变量

先从仓库根目录复制示例配置：

```powershell
Copy-Item .env.example .env
```

至少确认以下变量：

- `CRAWLER_BOOTSTRAP_ADMIN_USERNAME`
- `CRAWLER_BOOTSTRAP_ADMIN_PASSWORD`
- `CRAWLER_CORS_ALLOWED_ORIGINS`

如果 React 前端和 API 不在同一源上，还要在前端构建时提供：

- `VITE_API_BASE_URL`

如果部署环境需要出站代理，再确认：

- `CRAWLER_OUTBOUND_PROXY_URL`
- `CRAWLER_USE_SYSTEM_PROXY`
- `CRAWLER_OUTBOUND_NO_PROXY`

## 2. 启动后端

仓库里的 `docker-compose.yml` 只负责后端服务：

```powershell
docker compose up --build -d
```

后端健康检查地址：

```text
http://127.0.0.1:8000/health
```

## 3. 构建前端

React 前端的正式构建入口是：

```powershell
npm run build:web
```

这会调用 `web/` 下的 Vite 构建脚本，产物输出到：

```text
web/dist
```

如果你需要在构建前显式指定 API 地址，可以先设置：

```powershell
$env:VITE_API_BASE_URL = "https://api.example.com"
```

## 4. 发布静态文件

将 `web/dist` 上传到静态托管服务，例如：

- Nginx
- OSS / COS / S3 静态站点
- Vercel
- Netlify

如果前端路由使用 SPA 模式，静态托管需要把未知路径回退到 `index.html`。

## 5. 上线验收

上线后至少确认：

1. 前端首页可以访问
2. `/health` 返回 `200`
3. 可以使用管理员账号登录
4. 登录后能看到看板、任务、公告和来源页面

## 备注

- `docker compose` 不构建也不托管前端。
- 前端域名变化时，后端 CORS 配置也要同步更新。
- 如果本机 Flutter 只能读不能写，本地回退构建请继续使用 `scripts\flutterw.ps1`。
- 需要回退验证时，使用 `npm run start:flutter`，不要把 Flutter 当成默认上线链路。
