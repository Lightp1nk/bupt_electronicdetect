# 北邮宿舍用电监测系统

面向北邮宿舍电费查询、历史分析与提醒的 Web 系统。系统使用北邮 CAS 完成登录，以用户隔离的业务 Session 查询电费，将真实快照保存到 SQLite，并提供自动采集、统计预测、低余额/剩余天数预警、AstrBot QQ 通知和 QQ 主动查询。

## 核心能力

- 北邮 CAS 登录：Bootstrap Client 与长期 Runtime Client 分离；密码、CAS ticket 与 CAS Cookie 不持久化。
- 多用户本地身份：浏览器 App Session、加密上游业务 Session、Runtime Client Pool 均按用户隔离。
- 宿舍电费采集：支持手动查询与每日定时采集；按 `(area_id, room_id, source_time)` 去重保存历史快照。
- 统计预测：计算每日耗电量、近 3/7 日平均耗电，以及基于剩余电量的预计可用天数。
- 用户级预警：低余额与剩余天数预警以事件 episode 维护 `active` / `resolved` 生命周期。
- AstrBot 集成：网页生成 QQ 绑定码，QQ 私聊 `/绑定` 建立身份；支持 `/电费`、`/查询电费` 读取已采集摘要，并向已绑定 QQ 投递预警。
- 只读演示数据：可在受认证保护的演示模式中展示 90 天历史、Heatmap 和预测，不写数据库、不触发预警或通知。

## 技术栈

| 范围 | 技术 |
| --- | --- |
| 后端 | Python、FastAPI、SQLAlchemy Async、Alembic、APScheduler、httpx、cryptography/Fernet |
| 前端 | Vue 3、TypeScript、Vite、ECharts、lucide-vue-next |
| 数据库 | SQLite（`aiosqlite`） |
| 外部集成 | 北邮 CAS / 电费业务站点、AstrBot Bridge Plugin、QQ |
| 生产运行 | Nginx、systemd、单 worker Uvicorn、独立 AstrBot Docker 容器 |

## 运行架构

```text
Vue 3 → Nginx → FastAPI → Services / Repositories → SQLite
                         ↘ BUPT Runtime Client → 北邮电费上游
AstrBot QQ → Bridge Plugin → FastAPI Internal API → SQLite / Statistics
FastAPI NotificationService → Bridge Plugin → AstrBot → QQ 私聊
```

详细设计见 [docs/README.md](docs/README.md)。

## 本地开发

```powershell
python -m venv .venv
.\.venv\bin\python.exe -m pip install -r requirements.txt
cd frontend
npm install
cd ..
```

配置必需的 `APP_UPSTREAM_SESSION_KEY` 后启动：

```powershell
.\.venv\bin\python.exe -m alembic upgrade head
.\.venv\bin\python.exe -m uvicorn app.main:app --reload
```

前端开发服务：

```powershell
cd frontend
npm run dev
```

环境变量、迁移和生产注意事项见 [docs/02_部署与运维指南.md](docs/02_部署与运维指南.md) 与 [docs/03_配置参考.md](docs/03_配置参考.md)。

## 验证

```powershell
.\.venv\bin\python.exe -m pytest -q
cd frontend
npm run build
```

## 运行限制

- 自动采集按 **单进程、单 worker** FastAPI 部署设计；多个 worker 会重复注册 Scheduler Job。
- SQLite 数据文件必须位于持久化目录，并在迁移前备份。
- QQ `/电费` 只读取已有快照，不会主动请求北邮。
- 演示模式必须显式启用 `DEMO_MODE_ENABLED=true`，且仍需浏览器登录。
