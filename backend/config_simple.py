# 会理AI导游 - 简化配置（本地测试用）
import os
from dotenv import load_dotenv

load_dotenv()


class ConfigSimple:

    APP_NAME = "会理市AI数字人导游系统"
    VERSION = "1.0.0"
    DEBUG = True
    HOST = "0.0.0.0"
    PORT = 5000

    XIAOMI_API_KEY = os.getenv("XIAOMI_API_KEY", "test_key")
    XIAOMI_MODEL = "mimo-v2-flash"
    XIAOMI_BASE_URL = "https://api.xiaoai.mi.com/v1"

    MAX_TOKENS = 120
    TEMPERATURE = 0.3
    TOP_P = 0.9

    EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_CACHE_PATH = "./models/embeddings"

    CHROMA_DB_PATH = "./chroma_db_simple"
    COLLECTION_NAME = "huili_knowledge_base_simple"

    CACHE_TTL = 3600
    USE_FAKE_REDIS = True
    MAX_AUDIO_SIZE = 10485760

    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-in-production")

    LOGS_DIR = "./logs"
    KNOWLEDGE_BASE_DIR = "../knowledge_base"

    MAX_CONCURRENT_REQUESTS = 10
    REQUEST_TIMEOUT = 30

    DEFAULT_LATITUDE = 26.6584
    DEFAULT_LONGITUDE = 102.2437
    NEARBY_RADIUS_KM = 10.0

    TOP_K_RESULTS = 3
    SIMILARITY_THRESHOLD = 0.7
    VECTOR_WEIGHT = 0.8
    BM25_WEIGHT = 0.2

    ENABLE_CORS = True
    CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"

    LOG_LEVEL = "INFO"
    LOG_FILE = "./logs/app.log"
    JSON_LOGS = False
