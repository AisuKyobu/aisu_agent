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

# Playwright 浏览器：使用本地上传的 Chromium zip（避免 CDN 下载失败）
COPY browsers/chrome-linux64.zip /tmp/chrome-linux64.zip
RUN mkdir -p /opt/chromium && \
    unzip /tmp/chrome-linux64.zip -d /opt/chromium && \
    rm /tmp/chrome-linux64.zip && \
    chmod +x /opt/chromium/chrome-linux/chrome

ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/opt/chromium/chrome-linux/chrome

# 只安装浏览器系统依赖（不下载浏览器）
RUN playwright install-deps chromium

COPY . .
RUN rm -rf /app/browsers && \
    mkdir -p /app/data/workspace /app/data/sessions /app/data/memory /app/data/sandbox && \
    chown -R 1000:1000 /app

USER 1000:1000

ENV DATA_DIR=/app/data
ENV PYTHONDONTWRITEBYTECODE=1
ENV SANDBOX_MODE=docker

EXPOSE 7890

CMD ["python", "main.py"]
