FROM python:3.12-slim

WORKDIR /app

# apt 国内镜像（兼容新旧两种 Debian 源格式）
RUN if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list.d/debian.sources; \
    else \
      sed -i 's|deb.debian.org|mirrors.aliyun.com|g' /etc/apt/sources.list; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
    curl git && \
    rm -rf /var/lib/apt/lists/*

# pip 安装：使用 BuildKit 缓存挂载，避免每次重新下载包
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# Playwright 浏览器（使用官方 CDN）
RUN --mount=type=cache,target=/root/.cache/pip \
    playwright install chromium && \
    playwright install-deps chromium

COPY . .

RUN mkdir -p /app/data/workspace /app/data/sessions /app/data/memory /app/data/sandbox && \
    chown -R 1000:1000 /app

USER 1000:1000

ENV DATA_DIR=/app/data
ENV PYTHONDONTWRITEBYTECODE=1
ENV SANDBOX_MODE=docker

EXPOSE 7890

CMD ["python", "main.py"]
