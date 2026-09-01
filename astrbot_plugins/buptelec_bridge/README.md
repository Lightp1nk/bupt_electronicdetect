# 北邮电费通知桥接插件

此插件是 FastAPI 电费系统与 AstrBot 的边界适配器。

1. 用户先在 Web 系统中保存自己的 QQ ID。
2. 同一 QQ 用户私聊 AstrBot 并发送 `/电费绑定`。
3. 插件仅在 AstrBot 的插件数据目录保存 QQ ID 到 UMO 的映射。
4. FastAPI 以 AstrBot API Key 调用受 `plugin` scope 保护的：
   `POST /api/v1/plugins/extensions/buptelec_bridge/api/send`

插件不会保存北邮账号、密码、Cookie、FastAPI 会话或 AstrBot API Key。
