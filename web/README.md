# React 前端

这是现有 Flutter Web 客户端的并行迁移版本。后端接口保持不变，Flutter 工程仍保留在 `../frontend/`，可随时作为回滚入口。

## 本地命令

在 `crawler_system` 目录运行：

```powershell
npm start
```

该命令会构建 React、启动 FastAPI（`http://127.0.0.1:8000`），并在 `http://127.0.0.1:8093` 提供 React 页面。

需要回到 Flutter 时：

```powershell
npm run start:flutter
```

只调试 React（后端需已启动）时：

```powershell
npm --prefix ./web run dev
```

React 调试端口为 `8094`，Vite 会把 `/v1` 和 `/health` 转发到本机 `8000`。

## 验证

```powershell
npm --prefix ./web test
npm --prefix ./web run typecheck
npm --prefix ./web run build
npm run test:start
```

应用使用浏览器原生 History API 保存筛选和详情上下文；主要路由包括 `/`、`/notices`、`/keywords`、`/sources` 和 `/system`。
