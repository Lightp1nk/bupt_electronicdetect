# AstrBot 与 QQ 集成

## 目的

说明 AstrBot Bridge 插件在 QQ 身份验证、主动查询和预警投递中的职责。

## 插件职责

插件位于 `astrbot_plugins/buptelec_bridge/`，运行在 AstrBot 环境。它：

- 从 QQ 私聊事件中获取 QQ ID 和 AstrBot `unified_msg_origin`；
- 在插件数据目录保存 QQ ID → UMO 路由；
- 提供 `/绑定`、`/电费`、`/查询电费` 命令；
- 暴露 Bridge HTTP 发送接口；
- 调用 FastAPI Internal API 完成绑定与只读电费摘要查询。

FastAPI 不保存 UMO，也不调用 AstrBot 官方 IM API。

## QQ 绑定

网页用户生成十分钟有效的一次性绑定码。用户在同一 QQ 私聊发送 `/绑定 <code>` 后，插件调用 Internal API。成功时 FastAPI 创建 `chat_identities`，并自动创建启用的 AstrBot QQ `notification_binding`；插件保存该 QQ 的 UMO 路由。

网页可以启停通知或解绑 QQ，但不要求用户手工输入 QQ ID。解绑会删除聊天身份及其派生的通知目标。

## QQ 查询与通知

`/电费` 和 `/查询电费` 只读取绑定用户已配置宿舍的 SQLite 最新快照与 StatisticsService 结果，不请求北邮实时上游。

预警通知时，FastAPI 向 Bridge 发送 QQ ID 与纯文本消息；插件通过本地 QQ ID → UMO 映射投递私聊。未绑定或路由缺失会返回失败，交由 NotificationDelivery 记录。

## 安全边界

- Internal API 使用 `ASTRBOT_INTERNAL_TOKEN` / `BUPTELEC_INTERNAL_TOKEN` Bearer Token。
- Bridge 方向使用独立 Bridge Token。
- 插件不保存北邮账号、密码、Cookie、FastAPI 浏览器 Session 或 AstrBot API Key。
- QQ 命令只能基于事件发送者的 QQ ID 查询对应绑定用户，不能传入任意 `user_id`。
