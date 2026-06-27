# 会理市AI数字人导游 - Docker镜像构建文件
# 多阶段构建，优化镜像大小
# 作者：资深全栈架构师
# 日期：2026年4月20日

# ========== 第一阶段：构建阶段 ==========
FROM python:3.9-slim AS builder

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY backend/requirements.txt .

# 安装Python依赖
RUN pip install --user --no-cache-dir -r requirements.txt

# ========== 第二阶段：运行阶段 ==========
FROM python:3.9-slim

# 设置元数据
LABEL maintainer="资深全栈架构师 <architect@huili-guide.com>"
LABEL version="1.0.0"
LABEL description="会理市AI数字人导游系统 - 国家级软件设计大赛参赛作品"

# 设置工作目录
WORKDIR /app

# 创建非root用户
RUN groupadd -r appuser && useradd -r -g appuser -s /bin/false appuser

# 安装系统依赖（运行所需）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制已安装的Python包
COPY --from=builder /root/.local /root/.local

# 复制应用程序代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/logs \
    /app/backend/chroma_db \
    /app/knowledge_base/raw_data \
    /app/knowledge_base/processed \
    && chown -R appuser:appuser /app

# 设置环境变量
ENV PATH=/root/.local/bin:$PATH \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # 应用配置
    APP_NAME="会理市AI数字人导游系统" \
    VERSION="1.0.0" \
    DEBUG="False" \
    HOST="0.0.0.0" \
    PORT="5000" \
    # 模型配置
    XIAOMI_MODEL="mimo-v2-flash" \
    MAX_TOKENS="120" \
    TEMPERATURE="0.3" \
    TOP_P="0.9" \
    # 嵌入模型
    EMBEDDING_MODEL="BAAI/bge-small-zh-v1.5" \
    EMBEDDING_CACHE_PATH="/app/models/embeddings" \
    # 向量数据库
    CHROMA_DB_PATH="/app/backend/chroma_db" \
    COLLECTION_NAME="huili_knowledge_base" \
    # 缓存配置
    USE_FAKE_REDIS="True" \
    CACHE_TTL="3600" \
    # 音频处理
    WHISPER_MODEL="tiny" \
    MAX_AUDIO_SIZE="10485760" \
    # 安全配置
    SECRET_KEY="huili-smart-guide-docker-secret-2026" \
    ADMIN_PASSWORD="admin123" \
    # 文件路径
    LOGS_DIR="/app/logs" \
    KNOWLEDGE_BASE_DIR="/app/knowledge_base" \
    # 性能配置
    MAX_CONCURRENT_REQUESTS="10" \
    REQUEST_TIMEOUT="30" \
    # 地理位置
    DEFAULT_LATITUDE="26.6584" \
    DEFAULT_LONGITUDE="102.2437" \
    NEARBY_RADIUS_KM="10.0" \
    # RAG配置
    TOP_K_RESULTS="3" \
    SIMILARITY_THRESHOLD="0.7" \
    VECTOR_WEIGHT="0.8" \
    BM25_WEIGHT="0.2" \
    # Gunicorn配置
    GUNICORN_WORKERS="4" \
    GUNICORN_WORKER_CLASS="sync" \
    GUNICORN_BIND="0.0.0.0:5000"

# 切换到非root用户
USER appuser

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# 暴露端口
EXPOSE 5000

# 构建知识库（如果不存在）
RUN if [ ! -f "/app/backend/chroma_db/chroma.sqlite3" ]; then \
    echo "构建知识库..." && \
    python knowledge_base/build_kb_simple.py; \
    fi

# 启动命令
CMD ["gunicorn", "backend.app:app", \
    "--workers", "4", \
    "--worker-class", "sync", \
    "--bind", "0.0.0.0:5000", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "--timeout", "120"]

# ========== 构建说明 ==========
# 构建镜像：
#   docker build -t huili-smart-guide:latest .
#
# 运行容器：
#   docker run -d \
#     --name huili-guide \
#     -p 5000:5000 \
#     -v ./data:/app/data \
#     -e XIAOMI_API_KEY="your_api_key" \
#     huili-smart-guide:latest
#
# 使用Docker Compose：
#   docker-compose up -d
#
# 访问应用：
#   http://localhost:5000
#   http://localhost:5000/api/health (健康检查)
#
# 查看日志：
#   docker logs -f huili-guide
#
# 进入容器：
#   docker exec -it huili-guide /bin/bash
#
# 停止容器：
#   docker stop huili-guide
#
# 删除容器：
#   docker rm huili-guide
#
# 删除镜像：
#   docker rmi huili-smart-guide:latest