# Frontend

这是 Crawler System 的 Flutter Web 前端，负责：

- 登录与会话恢复
- 看板与公告展示
- 任务管理与日志查看
- 模板与关键词规则管理

## 本地运行

不要直接依赖系统 `flutter`。请优先使用仓库内的 wrapper：

```powershell
..\scripts\flutterw.ps1 pub get
..\scripts\flutterw.ps1 analyze
..\scripts\flutterw.ps1 test
..\scripts\flutterw.ps1 run -d web-server --web-port 8093 --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

如果你在仓库根目录，直接用：

```powershell
npm start
```

## API 配置

前端通过 `API_BASE_URL` 读取后端地址，对应入口在 [app_config.dart](/D:/projects/my_third_app/crawler_system/frontend/lib/core/config/app_config.dart:4)。

开发运行示例：

```powershell
..\scripts\flutterw.ps1 run -d web-server --web-port 8093 --dart-define=API_BASE_URL=http://127.0.0.1:8000
```

生产构建示例：

```powershell
..\scripts\frontend-build.ps1 -ApiBaseUrl https://api.example.com
```

## 登录与会话

- 登录页不再预填默认账号
- 管理员账号由后端启动配置初始化
- 受保护接口返回 `401` 时，前端会自动清理会话并退回登录页

相关位置：

- [login_page.dart](/D:/projects/my_third_app/crawler_system/frontend/lib/features/auth/presentation/pages/login_page.dart:26)
- [api_client.dart](/D:/projects/my_third_app/crawler_system/frontend/lib/core/network/api_client.dart:16)
- [app_router.dart](/D:/projects/my_third_app/crawler_system/frontend/lib/app/router/app_router.dart:40)

## 构建与部署

当前前端只推荐静态部署，不再假设由后端容器托管。

构建命令：

```powershell
..\scripts\frontend-build.ps1 -ApiBaseUrl https://api.example.com
```

产物目录：

```text
frontend/build/web
```

可部署到任何静态托管服务，但后端必须放开对应域名的 CORS。
