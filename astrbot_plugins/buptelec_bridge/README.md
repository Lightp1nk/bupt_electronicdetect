# 北邮电费通知桥接插件

此插件是 FastAPI 电费系统与 AstrBot 的边界适配器。

1. 用户先在 Web 系统中保存并启用自己的 QQ ID。
2. 同一 QQ 用户私聊 AstrBot 并发送 `/电费绑定`。插件会校验该 QQ 号，未保存或已关闭时不会写入 UMO 映射。
3. 插件仅在 AstrBot 的插件数据目录保存 QQ ID 到 UMO 的映射。
4. FastAPI 以 AstrBot API Key 调用受 `plugin` scope 保护的：
   `POST /api/v1/plugins/extensions/buptelec_bridge/api/send`

插件不会保存北邮账号、密码、Cookie、FastAPI 会话或 AstrBot API Key。

## 插件环境变量

- `BUPTELEC_APP_ENDPOINT`：电费系统根地址，例如 `https://buptelec.pureastar.top`
- `BUPTELEC_BRIDGE_TOKEN`：与 FastAPI 的 `ASTRBOT_BRIDGE_TOKEN` 相同的内部 Bridge 令牌

这两项仅写入 AstrBot 容器环境，不写入插件文件或仓库。
