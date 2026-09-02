# 北邮电费通知桥接插件

此插件是 FastAPI 电费系统与 AstrBot 的边界适配器。

1. 用户在 Web 系统生成一次性绑定码，并在同一 QQ 私聊中发送 `/绑定 <绑定码>`；该动作同时建立 QQ 身份、通知目标与 QQ ID 到 UMO 的私聊路由。
2. 已绑定用户可私聊发送 `/电费` 或 `/查询电费`，读取已有 SQLite 快照；不会发起北邮实时查询。
3. 通知可在网页中关闭或重新开启，但网页不会要求输入或修改 QQ 号。
4. 插件仅在 AstrBot 的插件数据目录保存 QQ ID 到 UMO 的通知路由映射。
5. FastAPI 以 AstrBot API Key 调用受 `plugin` scope 保护的：
   `POST /api/v1/plugins/extensions/buptelec_bridge/api/send`

插件不会保存北邮账号、密码、Cookie、FastAPI 会话或 AstrBot API Key。

## 插件环境变量

- `BUPTELEC_APP_ENDPOINT`：电费系统根地址，例如 `https://buptelec.pureastar.top`
- `BUPTELEC_BRIDGE_TOKEN`：与 FastAPI 的 `ASTRBOT_BRIDGE_TOKEN` 相同的内部 Bridge 令牌
- `BUPTELEC_INTERNAL_TOKEN`：与 FastAPI 的 `ASTRBOT_INTERNAL_TOKEN` 相同，仅用于 QQ 身份绑定与只读摘要查询

这两项仅写入 AstrBot 容器环境，不写入插件文件或仓库。
