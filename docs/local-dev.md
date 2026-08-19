# 本地开发

## 工具链

- Python 通过 `scripts\pythonw.ps1` 管理隔离环境。
- React 通过 `web\` 下的 npm 脚本运行。
- `scripts\dev-up.ps1` 是前后端联合启动的唯一入口。

`scripts\pythonw.ps1` 会先验证工作区 `.venv`。如果该环境指向缺失的解释器，它会使用已安装的 `uv`，并基于仓库依赖创建隔离的 Python 3.11 环境。

## 启动应用

在工作区根目录或 `crawler_system` 目录执行：

```powershell
npm start
```

该命令启动 FastAPI 后端和 React 前端，默认监听：

- 后端：`http://127.0.0.1:8000`
- 前端：`http://127.0.0.1:8093`

启动成功后还会打印 `LAN URL`。同一局域网内的用户可通过该地址访问。Windows 首次询问网络访问权限时，只允许“专用网络”即可，不要把开发端口直接暴露到公网。

启动时可选创建本地管理员账号：

```powershell
$env:CRAWLER_BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:CRAWLER_BOOTSTRAP_ADMIN_PASSWORD = "change-this-password"
npm start
```

两个变量必须同时设置。如果都不设置，后端不会创建初始管理员；如果只设置一个，启动会直接失败。

停止应用：

```powershell
npm stop
```

## 单独调试前端

后端已经启动时，可以执行：

```powershell
npm --prefix .\web run dev
```

如果 API 不与前端同源，可在构建前设置：

```powershell
$env:VITE_API_BASE_URL = "https://api.example.com"
```

本地联合启动时，也可以通过 `API_BASE_URL` 显式指定后端地址。

## 出站网络

`CRAWLER_OUTBOUND_NO_PROXY` 默认只包含本机地址。全局代理存在时，下载器会先走代理，连接失败后再尝试直连；任务级显式代理不会被自动绕过。若代理和直连均失败，需要修复服务器的 VPN、代理规则或目标网站网络可达性。

## 校验

运行完整校验链：

```powershell
.\scripts\dev-check.ps1
```

脚本依次执行后端测试，以及 React 的类型检查、测试和生产构建。

只验证联合启动脚本映射：

```powershell
npm run test:start
```

部署说明见 [deployment.md](deployment.md)。
