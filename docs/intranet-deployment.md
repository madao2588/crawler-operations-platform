# 公司内网部署、升级与回滚

## 首次部署

服务器需安装 Docker Engine 与 Docker Compose v2，并允许访问目标采集网站。将整个 `crawler_system` 目录复制到服务器后：

```powershell
Copy-Item .env.production.example .env.production
notepad .env.production
docker compose --env-file .env.production -f compose.production.yml config
docker compose --env-file .env.production -f compose.production.yml up -d --build
docker compose --env-file .env.production -f compose.production.yml ps
```

必须先把示例管理员密码换成长随机密码。浏览器访问 `http://服务器IP:8093/`；对外只需放行配置的 Web 端口，8000 不应开放。数据库、快照和备份分别保存在 `runtime/data`、`runtime/storage`、`runtime/backups`。

## 健康检查与日志

```powershell
Invoke-RestMethod http://服务器IP:8093/health
docker compose --env-file .env.production -f compose.production.yml logs --tail 200 api
docker compose --env-file .env.production -f compose.production.yml logs --tail 100 web
```

健康接口应返回 `status=ok`、数据库可用、调度器运行。若采集异常，应先看系统页面的失败分类和下次重试时间，再检查 API 日志；不要用不断重启代替定位原因。

## 升级

1. 在旧版本目录执行 `npm run delivery:check`，确认并保存一致性备份。
2. 记录当前 Git 提交或发布包版本，不覆盖 `runtime` 和 `.env.production`。
3. 更新代码后执行：

```powershell
docker compose --env-file .env.production -f compose.production.yml build
docker compose --env-file .env.production -f compose.production.yml up -d
docker compose --env-file .env.production -f compose.production.yml ps
Invoke-RestMethod http://127.0.0.1:8093/health
```

数据库迁移在 API 启动时幂等执行。升级后需实际验证登录、公告筛选、个人关注、管理员修改和一键更新。

API 会在启动时以及每天上海时间 03:30 自动备份并清理过期运行文件；升级仍应额外保留一份离线备份，不能只依赖容器内的自动保留周期。

## 回滚与恢复

代码回滚优先切回上一发布版本并重新构建。若必须恢复数据库：

1. `docker compose --env-file .env.production -f compose.production.yml down`
2. 复制 `runtime/data/data.db` 留存当前故障现场。
3. 从 `runtime/backups/runtime` 选择经完整性检查的 `.db`，复制为 `runtime/data/data.db`。
4. 重新 `up -d --build`，检查 `/health` 和交付报告。

不要在 API 容器运行时直接覆盖 SQLite 文件。公司域名、TLS 证书、服务器账号、防火墙和出口代理属于部署环境；如需 HTTPS，应由公司反向代理或网关终止 TLS，再转发到本系统 Web 端口。
