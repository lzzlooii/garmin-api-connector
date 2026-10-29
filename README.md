# Garmin MCP · 纯官方个人 API 版 v0.1.0

第三方 MCP 封装，不是 Garmin 官方产品。仅使用 Garmin 官方个人 API 客户端的 24 项专用数据接口。已移除账号密码登录、MFA、登录令牌导入及全部高级模式依赖。

## 实测情况

维护者已在 WorkBuddy 中实际安装，并确认可以使用。24 项接口依据官方 SDK 对齐，不代表已经逐项完成实测。本项目不是 Garmin 官方产品，也不代表获得官方认可。

## 安装到 WorkBuddy

已在 WorkBuddy 手机 App 端实测可安装使用。将安装链接或 ZIP 发给 WorkBuddy，告诉它“帮我安装”。让其按以下方式安装：让其从解压目录执行 `uv sync --locked --no-dev --python 3.12`，不要重新从旧仓库安装。项目默认使用清华 PyPI 镜像。

配置 MCP 时，运行解压目录下 `.venv/bin/garmin-mcp`（Windows 为 `.venv/Scripts/garmin-mcp.exe`）。设置 `GARMIN_PERSONAL_API_KEY` 和 `GARMIN_REGION=cn`。密钥优先通过专用配置入口填写，不要发到普通聊天中。需要保存密钥时可执行 `.venv/bin/garmin-mcp-login --region cn`，输入会隐藏。

密钥只显示一次，请安全保存。遗失时去佳明设置撤销旧密钥、重新创建并更新。第一次安装仍需准备 Python 3.12 与 uv，下载速度取决于实际运行环境。

## 24 项官方接口

| 序号 | 内容 | 官方方法与同名 MCP 工具 |
|---|---|---|
| 1 | 每日压力 | `get_daily_stress` |
| 2 | 每日步数 | `get_daily_steps` |
| 3 | 每日饮水 | `get_daily_hydration` |
| 4 | 体重目标 | `get_effective_weight_goals` |
| 5 | 体重测量 | `get_weight_measurements` |
| 6 | 饮食记录 | `get_daily_food_logs` |
| 7 | 个人资料设置 | `get_user_profile_settings` |
| 8 | 单晚睡眠 | `get_daily_sleep` |
| 9 | 多日睡眠汇总 | `get_daily_sleep_summaries` |
| 10 | 身体电量 | `get_daily_body_battery` |
| 11 | 每日健康汇总 | `get_daily_summaries` |
| 12 | 单日 HRV | `get_daily_hrv` |
| 13 | 多日 HRV 汇总 | `get_daily_hrv_summaries` |
| 14 | 心率区间 | `get_heart_rate_zones` |
| 15 | 体能年龄 | `get_fitness_age` |
| 16 | 每日心率 | `get_daily_heart_rate` |
| 17 | 生理周期汇总 | `get_menstrual_cycle_summary` |
| 18 | 生理周期日视图 | `get_menstrual_cycle_day_view` |
| 19 | 每日血氧 | `get_daily_spo2` |
| 20 | 日常活动汇总 | `get_wellness_activity_summaries` |
| 21 | 搜索运动记录 | `search_activities` |
| 22 | 单次运动详情 | `get_activity` |
| 23 | 运动关联训练 | `get_activity_workouts` |
| 24 | 下载原始运动文件 | `download_activity` |

清单依据下载时 Garmin 官方 GitHub 的 `GarminPersonalApiClient`。不把认证、令牌刷新、通用 GET 计为额外数据项目；不会通过通用 GET 暴露未知端点。

JSON 数据直接返回，不做趋势计算、字段删减、日期截断、自动拆分或额外指标推断。参数与官方客户端一致，日期范围超限时返回官方错误。运动文件下载以 MCP 二进制资源（Base64 传输）提供，解码后与官方 ZIP 字节一致；客户端能否保存附件需实测。

## 安全与部署

个人密钥本身敏感，只读不等于没有隐私风险；查询结果会交给 AI 客户端处理。本服务按单人单账号设计。公网网页设置必须通过可信 HTTPS 代理使用，并设置独立 ADMIN_PASSWORD。不要把含凭证的兼容 URL 公开分享。未经全面安全审计，不承诺绝对安全。

网页可用 `garmin-mcp-web` 启动，提供个人密钥设置与 MCP 认证，不提供任何 Garmin 密码登录入口。

## 出处

- 开发过程：由维护者设计与维护，Claude Code 协助编写初版，Codex 协助修改与安全加固。保留源码中的 MIT 版权与许可声明。
- 官方客户端：https://github.com/garmin/connect-personal-api-python ，Garmin Ltd. 或其子公司，Apache-2.0；通过依赖安装，未修改其源码。
- MCP Python SDK：https://github.com/modelcontextprotocol/python-sdk ，许可证以依赖发行版为准。
- 本次修改：移除账号模式，将 MCP 数据工具与官方 24 项方法一一对应，保留中国区切换和国内依赖镜像。

Garmin 个人 API 适用其个人使用条款。使用官方 API 不代表本项目获得 Garmin 官方认可。原有源代码许可不替代 API 使用条款。

## v0.1.0 安全加固与更新

24 项官方数据接口与原始数据返回方式不变。本次更新涉及凭证与服务保护。

- 本地 WorkBuddy MCP 继续使用原命令及个人密钥。推荐在新解压目录安装，再更新命令路径并重启该 MCP，确认运行的是 0.1.0。
- 默认关闭带密钥的 `/k/<secret>/mcp` 网址认证。远程连接使用 `/mcp` 和 Authorization 请求头。仅 ALLOW_URL_SECRET=1 时恢复旧网址方式；它仍可能被外部日志记录。
- Web 默认绑定 127.0.0.1。容器明确配置 HOST=0.0.0.0 供可信入口访问；公网使用 HTTPS 反向代理，并配置 PUBLIC_URL 和真实可信代理 IP。不要直接明文暴露凭证页面。
- 管理密码至少 12 位，不接受示例占位密码。管理 POST 要求同源 Origin。
- 凭证文件私有权限与原子写入，拒绝符号链接。POSIX 已测试；Windows ACL 尚需验证。磁盘凭证仍是明文文件，不是加密保险箱。
- 环境中的网络代理和 TLS 信任由主机管理员控制，请使用可信主机和代理。
- 删除本地凭证不等于撤销 Garmin 密钥。停用时应去佳明设置撤销。

附 SECURITY.md 和检查记录；本次检查不是独立渗透测试或绝对安全保证。

## 开发与 AI 协助

- 项目维护者：需求设计、测试与发布维护。
- Claude Code（Anthropic）：协助编写初版。
- Codex（OpenAI）：协助修改、接口对齐与安全加固。

以上为开发工具致谢，不代表 Anthropic、OpenAI 或 Garmin 对项目的官方认可。
