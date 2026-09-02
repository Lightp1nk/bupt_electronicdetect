# 数据库与 Alembic 迁移

## 目的

系统使用 SQLite 和 SQLAlchemy Async 持久化用户、会话、宿舍配置、真实电费快照、预警、通知和 QQ 身份。结构迁移由 Alembic 管理；应用启动时先创建缺失的基础表，再升级至 Alembic `head`。

## 实体关系

```text
users
 ├─< app_sessions
 ├─1 upstream_sessions
 ├─1 collection_settings
 ├─1 alert_settings
 ├─< alert_events
 ├─< notification_bindings ─< notification_deliveries >─ alert_events
 ├─< chat_identities
 └─< pending_chat_bindings

electricity_records
 └─ 按宿舍与 source_time 保存共享真实快照
```

`electricity_records` 不带 `user_id`：同一物理宿舍的真实上游快照可以被多个拥有该宿舍配置的用户读取；用户侧配置、预警、通知和聊天身份仍按 `user_id` 隔离。

## 核心表

### `users`

| 字段 | 说明 |
| --- | --- |
| `id` | 本系统用户主键 |
| `bupt_username` | 唯一北邮用户名 |
| `display_name` | 可空显示名 |
| `created_at` / `last_login_at` | 创建和最近登录时间 |

### `app_sessions`

保存浏览器会话，不保存原始令牌。

| 关键字段 | 说明 |
| --- | --- |
| `user_id` | 所属用户 |
| `token_hash` | 唯一 SHA-256 令牌哈希 |
| `expires_at` / `revoked_at` | 过期和撤销控制 |
| `last_seen_at` | 访问活跃时间 |

### `upstream_sessions`

每个用户最多一条经 Fernet 加密的上游业务 Session。

| 关键字段 | 说明 |
| --- | --- |
| `user_id` | 唯一外键 |
| `encrypted_cookie_blob` | 加密的 allowlist Cookie payload |
| `status` | `ACTIVE`、`EXPIRED`、`REAUTH_REQUIRED` 等状态 |
| `last_validated_at` | 最近验证时间 |

### `collection_settings`

每个用户最多一个监测宿舍与采集结果状态。包括校区/楼栋/楼层/宿舍 ID 和名称、`enabled`、`status`、`last_attempt_time`、`last_success_time`、`last_source_time`。

### `electricity_records`

真实上游快照，包含宿舍定位、余额、剩余电量、累计用电、单价、`source_time`、`query_time` 和完整 `raw_data_json`。

唯一约束：

```text
(area_id, room_id, source_time)
```

当上游缺少或无法解析 `source_time` 时，不以该字段进行去重。

### `alert_settings` 与 `alert_events`

`alert_settings` 每用户一行，保存低余额和剩余天数的 warning/critical 阈值与启用状态。

`alert_events` 保存事件 episode、触发值、阈值、标题、消息、来源时间和状态时间线。SQLite partial unique index 限制同一用户、宿舍和类型最多一个 `status='active'` Event：

```text
(user_id, area_id, room_id, alert_type) WHERE status = 'active'
```

### `notification_bindings` 与 `notification_deliveries`

`notification_bindings` 记录用户到通知目标的绑定：`user_id`、`provider`、`platform`、`target_id`、`enabled`。同一 `(user_id, provider, platform)` 唯一。

`notification_deliveries` 是按事件阶段的投递记录；同一 `(alert_event_id, binding_id, provider, stage)` 唯一，保存 `pending`、`success`、`failed`、发送时间和安全化错误信息。

### `chat_identities` 与 `pending_chat_bindings`

`chat_identities` 保存已验证外部聊天身份。`(platform, external_id)` 唯一，`(user_id, platform)` 也唯一。

`pending_chat_bindings` 只保存绑定码哈希、状态、过期时间和使用时间；明文绑定码不入库。当前绑定码有效期为十分钟。

## Alembic 迁移历史

| Revision | 内容 |
| --- | --- |
| `20260901_01` | 预 Alembic 数据库基线 |
| `20260901_02` | collection settings 从无归属单例迁移为用户作用域 |
| `20260901_03` | alert settings 与 events 迁移为用户作用域 |
| `20260901_04` | 新建 notification bindings |
| `20260901_05` | 新建 notification deliveries |
| `20260902_06` | 新建 chat identities 与 pending chat bindings |

旧的单例 `collection_settings`、`alert_settings`、`alert_events` 在迁移时保留为 `*_legacy_unassigned`，不会自动归属给任一用户，也不会被 Repository 或 Scheduler 查询。

## 运维与安全注意事项

- 迁移前先备份 SQLite 文件，使用 `alembic upgrade head`，不要删除数据库或 reset revision。
- 应用只支持 SQLite URL；`APP_DATABASE_URL` 应使用 `sqlite+aiosqlite:///...`。
- 真实 Cookie 加密材料位于环境变量，不在数据库文档、SQL 导出或日志中公开。

