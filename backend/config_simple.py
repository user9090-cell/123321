#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会理市AI数字人导游 - 简化配置
用于快速测试
"""

import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

class ConfigSimple:
    """简化配置类"""
    
    # 基础配置
    APP_NAME = "会理市AI数字人导游系统"
    VERSION = "1.0.0"
    DEBUG = True
    HOST = "0.0.0.0"
    PORT = 5000
    
    # 小米大模型配置
    XIAOMI_API_KEY = os.getenv("XIAOMI_API_KEY", "test_key")
    XIAOMI_MODEL = "mimo-v2-flash"
    XIAOMI_BASE_URL = "https://api.xiaoai.mi.com/v1"
    
    # 模型参数
    MAX_TOKENS = 120
    TEMPERATURE = 0.3
    TOP_P = 0.9
    
    # 嵌入模型配置
    EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
    EMBEDDING_CACHE_PATH = "./models/embeddings"
    
    # 向量数据库配置
    CHROMA_DB_PATH = "./chroma_db_simple"
    COLLECTION_NAME = "huili_knowledge_base_simple"
    
    # 缓存配置
    CACHE_TTL = 3600
    USE_FAKE_REDIS = True
    
    # 音频处理配置
    MAX_AUDIO_SIZE = 10485760
    
    # 安全配置
    SECRET_KEY = "huili-smart-guide-simple-key"
    ADMIN_PASSWORD = "admin123"
    
    # 文件路径配置
    LOGS_DIR = "./logs"
    KNOWLEDGE_BASE_DIR = "../knowledge_base"
    
    # 性能配置
    MAX_CONCURRENT_REQUESTS = 10
    REQUEST_TIMEOUT = 30
    
    # 地理位置配置
    DEFAULT_LATITUDE = 26.6584
    DEFAULT_LONGITUDE = 102.2437
    NEARBY_RADIUS_KM = 10.0
    
    # RAG检索配置
    TOP_K_RESULTS = 3
    SIMILARITY_THRESHOLD = 0.7
    VECTOR_WEIGHT = 0.8
    BM25_WEIGHT = 0.2
    
    # 开发配置
    ENABLE_CORS = True
    CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"
    
    # 日志配置
    LOG_LEVEL = "INFO"
    LOG_FILE = "./logs/app.log"
    JSON_LOGS = False