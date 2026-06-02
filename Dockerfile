FROM python:3.11-slim

WORKDIR /app

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# 复制依赖定义文件（利用 Docker 缓存层）
COPY pyproject.toml uv.lock ./

# 安装依赖（使用 uv.lock 锁定版本）
RUN uv sync --frozen --no-dev --no-install-project

# 复制项目文件
COPY . .

# 创建数据和图片目录
RUN mkdir -p data/met data/asianart data/philamuseum \
    images/met images/asianart images/philamuseum

# 默认执行全部流程
ENTRYPOINT ["uv", "run", "python", "main.py"]
CMD ["--step", "all"]
