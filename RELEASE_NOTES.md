# v0.1.0 · 首个公开测试版

面向 WorkBuddy 等 MCP 客户端的 Garmin 个人 API 连接器，支持中国区，使用用户自己的个人 API 密钥，不要求填写 Garmin 账号密码。

## 安装

下载本页附件 garmin-mcp-v0.1.0.zip，上传给 WorkBuddy，发送“请安装这个 ZIP 中的 Garmin MCP 连接器，按 README 配置中国区”。安装后通过专用配置入口填写自己的个人 API 密钥，不要把密钥发到普通聊天中。

维护者已在 WorkBuddy 实际安装并确认可用；未声称全部 24 项查询均已逐项实测。运行环境仍需支持 Python 3.12 和 uv。

## 本版内容

- 与官方客户端的 24 项专用数据方法对应，返回原始数据。
- 保留中国区设置与清华依赖镜像。
- 加强密钥文件权限、后台会话保护、日志脱敏和联网地址限制。
- 默认关闭网址携带访问密钥的方式，远程使用 HTTPS 和 Authorization 请求头。

## 检查与边界

20 项回归测试通过；34 个第三方依赖数据库检查未报告已知漏洞；应用源码 Bandit 扫描没有报告问题。本地项目未在 PyPI 发布，不适用该数据库的包版本漏洞核对。以上不构成全面安全审计或绝对安全承诺。

个人 API 密钥可读取敏感健康数据；本地凭证文件仍为明文；查询结果会交给所用 AI 平台处理。公开部署请阅读 SECURITY.md。请勿上传个人密钥、令牌或真实健康数据到 Issues。

## 出处

- Garmin 官方个人 API SDK：https://github.com/garmin/connect-personal-api-python （Apache-2.0，未修改其源码）
- MCP Python SDK：https://github.com/modelcontextprotocol/python-sdk （MIT）
- 维护者设计与维护，Claude 协助编写初版，GPT 协助修改与安全加固；源码中的 MIT LICENSE 及第三方声明保留。

使用官方接口不代表获得 Garmin 官方认可；API 使用仍须遵守其适用条款。
