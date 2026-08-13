新药情报平台 - 公司内网部署包

一、服务器要求
1. Windows 10/11，已安装并启动 Docker Desktop（Linux 容器模式）。如公司使用 Windows Server 或 Linux 服务器，请由运维先提供 Docker Engine 与 Docker Compose v2，再用同目录 compose.production.yml 部署。
2. 至少 4 核 CPU、8 GB 内存、20 GB 可用磁盘空间。
3. 防火墙仅对公司内网开放 8093 端口，不要开放后端 8000 端口。
4. 本发布包带有离线 Docker 镜像，首次安装无需从互联网下载程序依赖；系统运行时仍需访问需求中的外部采集网站。

二、首次部署
1. 解压整个 ZIP，不要只复制其中部分文件。
2. 在当前目录打开 PowerShell。
3. 执行：
   Set-ExecutionPolicy -Scope Process Bypass
   .\verify.ps1
   .\deploy.ps1
4. 部署完成后，浏览器访问：http://服务器IP:8093/
5. 初次账号见 FIRST-LOGIN.txt。登录后立即在头像/账户面板中修改密码，并妥善删除 FIRST-LOGIN.txt。

三、日常操作
- 查看状态：.\status.ps1
- 一致性备份：.\backup.ps1
- 停止服务：.\stop.ps1
- 更新版本：把新版发布包内容覆盖到当前目录，然后执行 .\upgrade.ps1。脚本会先做一致性备份；新版不会携带活动的 .env.production，也不会覆盖 runtime。

四、数据保护
- 正式数据库、快照与备份保存在 runtime 目录。
- deploy.ps1 和 upgrade.ps1 都不会用发布包里的 seed 覆盖已有 runtime/data/data.db；已有 .env.production 只会同步镜像版本号，端口、代理、账号等配置保持不变。
- 更新前 upgrade.ps1 会先创建 SQLite 一致性备份。
- 不要删除 runtime 目录；不要在服务运行时手工替换 data.db。

五、常见问题
- “Docker engine is not running”：启动 Docker Desktop 后重试。
- 8093 端口已占用：修改 .env.production 中 INTRANET_PORT 后重试。
- 页面打不开：运行 .\status.ps1，再运行 docker compose --env-file .env.production -f compose.production.yml logs --tail 200。
- deploy.ps1 在“加载镜像”阶段停留几分钟是正常的；只要仍有磁盘活动就不要关闭窗口。超过 10 分钟没有变化时再检查 Docker Desktop 状态和磁盘空间。
- 采集失败：先在系统首页查看具体来源、HTTP 状态和错误分类，再检查内网服务器的外网出口或代理。

VERSION.json 记录版本与数据数量，SHA256SUMS.txt 用于核对包内文件完整性；ZIP 同目录的 .sha256 文件用于核对整个发布包。
