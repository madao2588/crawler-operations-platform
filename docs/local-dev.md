# 本地开发

## 工具链

本仓库使用以下包装脚本：

- Python 通过 `scripts\pythonw.ps1`
- React 通过 `web\` 下的 `npm` 脚本
- Flutter 通过 `scripts\flutterw.ps1`

不要直接依赖 PATH 里的 `flutter`。这台机器上的系统 Flutter SDK 当前可读但不可写，Flutter 可能无法创建或更新 `bin\cache\lockfile`。

`scripts\flutterw.ps1` 会按以下顺序处理 SDK：

1. 优先使用显式设置的 `CRAWLER_FLUTTER_ROOT`
2. 其次使用 PATH 上可写的 Flutter SDK
3. 如果 PATH 上的 SDK 只读，则复制到工作区内可写的 `.local-tools\flutter-sdk`

`scripts\pythonw.ps1` 会先验证工作区 `.venv`。如果该环境指向了缺失的解释器，它会回退到已安装的 `uv`，并基于仓库依赖创建隔离的 Python 3.11 环境。

## 启动应用

本地默认入口是 React：

```powershell
npm start
```

这会启动 FastAPI 后端和 React 前端组合，并监听 `8000` / `8093`。后端只在本机开放；React 前端会额外打印一条 `LAN URL`，同一局域网内的其他用户可直接用该地址访问，例如：

```text
LAN URL: http://192.168.1.20:8093
```

Windows 首次询问网络访问权限时，只允许“专用网络”即可。不要把 `8093` 端口直接暴露到公网。

如果你需要显式使用 React 入口，也可以执行：

```powershell
npm run start:react
```

如果你需要回退到 Flutter 组合，请使用：

```powershell
npm run start:flutter
```

启动时可选创建本地管理员账号。请在启动前同时设置这两个变量：

```powershell
$env:CRAWLER_BOOTSTRAP_ADMIN_USERNAME = "admin"
$env:CRAWLER_BOOTSTRAP_ADMIN_PASSWORD = "change-this-password"
```

如果两者都不设置，后端会跳过 bootstrap 管理员创建。如果只设置其中一个，启动会直接失败，避免配置半残留。

如果你要单独跑 React 构建或预览，并且 API 不与前端同源，请在构建前设置：

```powershell
$env:VITE_API_BASE_URL = "https://api.example.com"
```

如果要回退到 Flutter，则在构建脚本中使用 `API_BASE_URL` 和可写 Flutter SDK 根目录：

```powershell
$env:API_BASE_URL = "http://127.0.0.1:8000"
$env:CRAWLER_FLUTTER_ROOT = "D:\path\to\your\writable\flutter"
```

需求 1 的 7 个固定政府来源已经纳入默认 `CRAWLER_OUTBOUND_NO_PROXY` 直连列表。若使用 Clash/Vortex 一类 TUN/Fake-IP 代理，还需要把运行模式设为 `rule`，并让这些域名命中 `DIRECT`。`global` 模式会忽略域名规则，应用层 `NO_PROXY` 也无法覆盖系统级拦截。

停止当前组合：

```powershell
npm stop
```

## 校验

运行本地完整校验链：

```powershell
.\scripts\dev-check.ps1
```

这条脚本会依次执行：

1. 后端测试 `pytest -q`
2. React 前端类型检查 `typecheck`
3. React 前端测试 `test`
4. React 前端构建 `build`
5. Flutter `analyze`
6. Flutter `test`

如果你只想验证脚本映射是否正确，可以运行仓库测试：

```powershell
npm run test:start
```

## 部署方向

当前推荐的本地开发和部署思路都是前后端分离：

- 前端主线：React 静态包
- 回退前端：Flutter Web
- 后端：FastAPI API 服务

React 和 Flutter 都依赖同一个后端，但 React 是默认启动路径，Flutter 只保留为显式回退。

详见：

- [deployment.md](deployment.md)
