#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会理市AI数字人导游 - 配置管理模块
功能：管理应用配置，从环境变量读取敏感信息
日期：2026年4月20日
"""

import os
import logging
from typing import Dict, Any, Optional
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 计算项目根目录
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_BASE_DIR)

# 离线模式 + 模型缓存路径 —— .env 中的 HF_HOME 等值不可靠，强制使用项目目录
_model_hub = os.path.join(PROJECT_ROOT, "models", "hub")
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HOME"] = _model_hub
os.environ["HUGGINGFACE_HUB_CACHE"] = _model_hub
os.environ["TRANSFORMERS_CACHE"] = _model_hub

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class Config:
    """应用配置类"""

    BASE_DIR = _BASE_DIR
    PROJECT_ROOT = PROJECT_ROOT
    
    # 基础配置
    APP_NAME = "会理市AI数字人导游系统"
    VERSION = "1.0.0"
    DEBUG = os.getenv("DEBUG", "False").lower() == "true"
    
    # 服务器配置
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "5000"))
    
    # 小米大模型配置
    XIAOMI_API_KEY = os.getenv("XIAOMI_API_KEY", "")
    XIAOMI_MODEL = os.getenv("XIAOMI_MODEL", "mimo-v2-flash")
    XIAOMI_BASE_URL = os.getenv("XIAOMI_BASE_URL", "https://api.xiaomimimo.com/v1")
    
    # 模型参数
    MAX_TOKENS = int(os.getenv("MAX_TOKENS", "512"))
    TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))
    TOP_P = float(os.getenv("TOP_P", "0.9"))
    
    # 嵌入模型配置
    EMBEDDING_MODEL = os.getenv(
        "EMBEDDING_MODEL",
        os.path.join(PROJECT_ROOT, "models", "hub", "models--BAAI--bge-small-zh-v1.5", "snapshots", "7999e1d3359715c523056ef9478215996d62a620")
    )
    EMBEDDING_CACHE_PATH = os.getenv(
        "EMBEDDING_CACHE_PATH",
        os.path.join(PROJECT_ROOT, "models", "hub")
    )
    
    # 向量数据库配置
    CHROMA_DB_PATH = os.getenv(
        "CHROMA_DB_PATH",
        os.path.join(BASE_DIR, "chroma_db")
    )
    COLLECTION_NAME = os.getenv("COLLECTION_NAME", "huili_knowledge_base")
    
    # 缓存配置
    REDIS_URL = os.getenv("REDIS_URL", "")
    CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # 1小时
    USE_FAKE_REDIS = os.getenv("USE_FAKE_REDIS", "True").lower() == "true"
    
    # 音频处理配置
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")  # tiny, base, small, medium, large
    MAX_AUDIO_SIZE = int(os.getenv("MAX_AUDIO_SIZE", "10485760"))  # 10MB
    
    # 安全配置
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "change-me-in-production")
    
    # 文件路径配置
    LOGS_DIR = os.getenv("LOGS_DIR", os.path.join(BASE_DIR, "logs"))
    KNOWLEDGE_BASE_DIR = os.getenv(
        "KNOWLEDGE_BASE_DIR",
        os.path.join(PROJECT_ROOT, "knowledge_base")
    )
    LOG_FILE = os.getenv("LOG_FILE", os.path.join(BASE_DIR, "logs", "app.log"))
    
    # 性能配置
    MAX_CONCURRENT_REQUESTS = int(os.getenv("MAX_CONCURRENT_REQUESTS", "10"))
    REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))
    
    # 地理位置配置
    DEFAULT_LATITUDE = float(os.getenv("DEFAULT_LATITUDE", "26.6584"))
    DEFAULT_LONGITUDE = float(os.getenv("DEFAULT_LONGITUDE", "102.2437"))
    NEARBY_RADIUS_KM = float(os.getenv("NEARBY_RADIUS_KM", "20.0"))
    
    # RAG配置
    TOP_K_RESULTS = int(os.getenv("TOP_K_RESULTS", "3"))
    SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))
    VECTOR_WEIGHT = float(os.getenv("VECTOR_WEIGHT", "0.8"))
    BM25_WEIGHT = float(os.getenv("BM25_WEIGHT", "0.2"))

    # 开发与跨域配置
    ENABLE_CORS = os.getenv("ENABLE_CORS", "True").lower() == "true"
    CORS_ORIGINS = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000"
    )

    # 日志配置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
    JSON_LOGS = os.getenv("JSON_LOGS", "False").lower() == "true"
    
    @classmethod
    def validate(cls) -> bool:
        """
        验证配置是否有效
        
        Returns:
            bool: 配置是否有效
        """
        errors = []
        
        # 检查必需配置
        if not cls.XIAOMI_API_KEY:
            errors.append("XIAOMI_API_KEY 未设置，请检查 .env 文件")
        
        # 检查路径是否存在
        required_dirs = [cls.LOGS_DIR, cls.CHROMA_DB_PATH]
        for dir_path in required_dirs:
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    logger.info(f"创建目录: {dir_path}")
                except Exception as e:
                    errors.append(f"无法创建目录 {dir_path}: {e}")
        
        if errors:
            for error in errors:
                logger.error(error)
            return False
        
        return True
    
    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """
        将配置转换为字典（排除敏感信息）
        
        Returns:
            Dict[str, Any]: 配置字典
        """
        config_dict = {}
        
        for key in dir(cls):
            if not key.startswith("_") and key.isupper():
                value = getattr(cls, key)
                
                # 隐藏敏感信息
                if "KEY" in key or "SECRET" in key or "PASSWORD" in key:
                    if value:
                        config_dict[key] = "***HIDDEN***"
                    else:
                        config_dict[key] = value
                else:
                    config_dict[key] = value
        
        return config_dict
    
    @classmethod
    def print_summary(cls):
        """打印配置摘要"""
        logger.info("=" * 50)
        logger.info(f"{cls.APP_NAME} v{cls.VERSION} 配置摘要")
        logger.info("=" * 50)
        
        config_dict = cls.to_dict()
        for key, value in config_dict.items():
            logger.info(f"{key}: {value}")
        
        logger.info("=" * 50)
        
        # 检查配置有效性
        if cls.validate():
            logger.info("✅ 配置验证通过")
        else:
            logger.warning("⚠️ 配置验证失败，请检查错误信息")


# 全局配置实例
config = Config()


if __name__ == "__main__":
    # 测试配置
    config.print_summary()
