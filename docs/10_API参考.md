# API 参考

## 目的

列出当前路由分类和认证方式。所有响应使用统一 `ApiResponse`：`success`、`code`、`message`、`data`。

## 浏览器认证 API

| 方法 | 路径 | 认证 | 说明 |
| --- | --- | --- | --- |
| POST | `/api/v1/auth/login` | 无 | 北邮 CAS 登录并创建本系统浏览器 Session |
| GET | `/api/v1/auth/status` | Cookie（可选） | 当前登录状态与上游 Session 状态 |
| POST | `/api/v1/auth/logout` | Cookie（可选） | 撤销当前 App Session 并关闭当前用户 Runtime Client |

## 电费与宿舍 API

`/api/v1/electricity/buildings`、`/floors`、`/rooms`、`/query` 需要浏览器认证及可用 Runtime Client。`query` 会请求北邮并保存快照。

`/history/{room_id}`、`/latest/{room_id}`、`/analysis/{room_id}` 需要浏览器认证，默认读取真实 SQLite；`source=demo` 仅在服务器启用 Demo Mode 时可读取演示数据。

`/collection/settings`（GET/PUT/DELETE）、`/collection/status`（GET）、`/collection/run`（POST）均只作用于当前用户。

当前用户采集控制接口：
* `GET /api/v1/electricity/collection/settings`
* `PUT /api/v1/electricity/collection/settings`
* `DELETE /api/v1/electricity/collection/settings`
* `GET /api/v1/electricity/collection/status`
* `POST /api/v1/electricity/collection/run`


## Alert 与通知 API

| 路径 | 说明 |
| --- | --- |
| `/api/v1/electricity/alerts` | 当前用户、指定宿舍的事件列表 |
| `/api/v1/electricity/alerts/active` | 当前用户活跃事件 |
| `/api/v1/electricity/alerts/settings` | GET/PUT 当前用户阈值设置 |
| `/api/v1/notification/bindings` | 当前用户通知绑定 |
| `/api/v1/notification/bindings/astrbot/qq/enabled` | 启停已验证 QQ 的 AstrBot 通知 |
| `/api/v1/notification/status` | 当前用户最近投递状态 |

## QQ 身份与 Internal API

网页 Cookie API：`GET /api/v1/chat/identity`、`POST /api/v1/chat/identity/binding-code`、`DELETE /api/v1/chat/identity/{platform}`。

AstrBot Internal API 不能由浏览器调用，需 `Authorization: Bearer <ASTRBOT_INTERNAL_TOKEN>`：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/internal/chat/bind` | 验证绑定码并保存 QQ 身份 |
| POST | `/api/internal/chat/electricity/summary` | 按 QQ 身份读取已采集摘要 |

完整字段以 FastAPI OpenAPI 文档和 `app/schemas/` 为准。
