# 会理AI导游 - 配置模块（从 .env 读取）
import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_BASE_DIR)

# 离线模式 —— 强制使用项目目录下的模型缓存
_model_hub = os.path.join(PROJECT_ROOT, "models", "hub")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HOME"] = _model_hub
os.environ["HUGGINGFACE_HUB_CACHE"] = _model_hub
os.environ["TRANSFORMERS_CACHE"] = _model_hub

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Config:

    BASE_DIR = _BASE_DIR
    PROJECT_ROOT = PROJECT_ROOT

    APP_NAME = "会理市AI数字人导游系统"
    VERSION = "1.0.0"
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5000"))

    # 小米大模型
    XIAOMI_API_KEY = os.getenv("XIAOMI_API_KEY", "")
    XIAOMI_MODEL = os.getenv("XIAOMI_MODEL", "mimo-v2-flash")
    XIAOMI_BASE_URL = os.getenv("XIAOMI_BASE_URL", "https://api.xiaomimimo.com/v1")

    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))
    TOP_P = float(os.getenv("TOP_P", "0.9"))

    # 嵌入模型
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", os.path.join(PROJECT_ROOT, "models", "hub", "models--BAAI--bge-small-zh-v1.5", "snapshots", "7999e1d3359715c523056ef9478215996d62a620"))
    EMBEDDING_CACHE_PATH = os.getenv("EMBEDDING_CACHE_PATH", os.path.join(PROJECT_ROOT, "models", "hub"))

    # ChromaDB
    CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", os.path.join(BASE_DIR, "chroma_db"))
    COLLECTION_NAME = os.getenv("COLLECTION_NAME", "huili_knowledge_base")

    # 缓存
    REDIS_URL = os.getenv("REDIS_URL", "")
    CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))
    USE_FAKE_REDIS = os.getenv("USE_FAKE_REDIS", "True").lower() == "true"

    # 音频
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
    MAX_AUDIO_SIZE = int(os.getenv("MAX_AUDIO_SIZE", "10485760"))

    # 安全
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-in-production")

    # 路径
    LOGS_DIR = os.getenv("LOGS_DIR", os.path.join(BASE_DIR, "logs"))
    KNOWLEDGE_BASE_DIR = os.getenv("KNOWLEDGE_BASE_DIR", os.path.join(PROJECT_ROOT, "knowledge_base"))
    LOG_FILE = os.getenv("LOG_FILE", os.path.join(BASE_DIR, "logs", "app.log"))

    # 性能
    MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

    # 会理位置
    DEFAULT_LATITUDE = float(os.getenv("DEFAULT_LATITUDE", "26.6584"))
    DEFAULT_LONGITUDE = float(os.getenv("DEFAULT_LONGITUDE", "102.2437"))
    NEARBY_RADIUS_KM = float(os.getenv("NEARBY_RADIUS_KM", "20.0"))

    # RAG
    TOP_K_RESULTS = int(os.getenv("TOP_K_RESULTS", "3"))
    SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))
    VECTOR_WEIGHT = float(os.getenv("VECTOR_WEIGHT", "0.8"))
    BM25_WEIGHT = float(os.getenv("BM25_WEIGHT", "0.2"))

    ENABLE_CORS = os.getenv("ENABLE_CORS", "True").lower() == "true"
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    JSON_LOGS = os.getenv("JSON_LOGS", "False").lower() == "true"

    @classmethod
    def validate(cls):
        errors = []
        if not cls.XIAOMI_API_KEY:
            errors.append("XIAOMI_API_KEY 未设置，请检查 .env 文件")
        for d in [cls.LOGS_DIR, cls.CHROMA_DB_PATH]:
            if not os.path.exists(d):
                try:
                    os.makedirs(d, exist_ok=True)
                    logger.info(f"创建目录: {d}")
                except Exception as e:
                    errors.append(f"无法创建目录 {d}: {e}")
        if errors:
            for e in errors:
                logger.error(e)
            return False
        return True

    @classmethod
    def to_dict(cls):
        d = {}
        for key in dir(cls):
            if not key.startswith("_") and key.isupper():
                v = getattr(cls, key)
                d[key] = "***HIDDEN***" if (("KEY" in key or "SECRET" in key or "PASSWORD" in key) and v) else v
        return d

    @classmethod
    def print_summary(cls):
        logger.info("=" * 50)
        logger.info(f"{cls.APP_NAME} v{cls.VERSION}")
        logger.info("=" * 50)
        for k, v in cls.to_dict().items():
            logger.info(f"{k}: {v}")
        logger.info("=" * 50)
        if cls.validate():
            logger.info("配置验证通过")
        else:
            logger.warning("配置验证失败")


config = Config()

if __name__ == "__main__":
    config.print_summary()
