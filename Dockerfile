# 佳明 AI 连接器 · 网络模式镜像
FROM python:3.12-slim

# uv：快速安装依赖（用 pip 装，避免依赖 ghcr.io，国内网络也能构建）
RUN pip install --no-cache-dir uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# 先装依赖（利用缓存），再复制代码
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

# 数据文件夹：设置和佳明凭证都在这里，部署时一定要挂载持久化存储到 /data
ENV GARMIN_MCP_DATA=/data \
    TZ=Asia/Shanghai \
    PORT=8000 \
    HOST=0.0.0.0 \
    PATH="/app/.venv/bin:$PATH"

# 不用 root 运行
RUN useradd --create-home --uid 1000 app && mkdir -p /data && chown app:app /data
USER app

EXPOSE 8000
HEALTHCHECK --interval=60s --timeout=5s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz')"

CMD ["garmin-mcp-web"]
