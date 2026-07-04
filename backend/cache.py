# 会理AI导游 - 缓存模块
import hashlib
import json
import logging
import time
from typing import Any, Optional, Dict, Union
from functools import wraps

from config import config

logger = logging.getLogger(__name__)


class CacheManager:
    """缓存管理器，支持 Redis / fakeredis 自动切换"""

    def __init__(self):
        self.client = None
        self.use_fake_redis = config.USE_FAKE_REDIS
        self.ttl = config.CACHE_TTL
        self._init()

    def _init(self):
        try:
            if not self.use_fake_redis and config.REDIS_URL:
                import redis
                self.client = redis.from_url(config.REDIS_URL)
                logger.info("使用真实 Redis 缓存")
            else:
                import fakeredis
                self.client = fakeredis.FakeStrictRedis()
                logger.info("使用 fakeredis 缓存")
        except ImportError as e:
            logger.warning(f"缓存库导入失败: {e}")
            self.client = None
        except Exception as e:
            logger.error(f"缓存客户端初始化失败: {e}")
            self.client = None

    def is_available(self):
        return self.client is not None

    # ---- 基础操作 ----

    def generate_key(self, *args, **kwargs):
        parts = []
        for a in args:
            if isinstance(a, (str, int, float, bool)):
                parts.append(str(a))
            else:
                parts.append(hashlib.md5(str(a).encode()).hexdigest())
        for k, v in sorted(kwargs.items()):
            if isinstance(v, (str, int, float, bool)):
                parts.append(f"{k}:{v}")
            else:
                parts.append(f"{k}:{hashlib.md5(str(v).encode()).hexdigest()}")
        return f"huili:{hashlib.md5('|'.join(parts).encode()).hexdigest()}"

    def set(self, key, value, ttl=None):
        if not self.client:
            return False
        try:
            if isinstance(value, (dict, list, tuple)):
                raw = json.dumps(value, ensure_ascii=False)
            else:
                raw = str(value)
            expire = ttl if ttl is not None else self.ttl
            ok = self.client.setex(key, expire, raw)
            if not ok:
                logger.warning(f"setex 返回空: {key}")
            return bool(ok)
        except Exception as e:
            logger.error(f"set 缓存失败 [{key}]: {e}")
            return False

    def get(self, key):
        if not self.client:
            return None
        try:
            val = self.client.get(key)
            if val is None:
                return None
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return val.decode('utf-8') if isinstance(val, bytes) else val
        except Exception as e:
            logger.error(f"get 缓存失败 [{key}]: {e}")
            return None

    def delete(self, key):
        if not self.client:
            return False
        try:
            n = self.client.delete(key)
            return n > 0
        except Exception as e:
            logger.error(f"delete 缓存失败 [{key}]: {e}")
            return False

    def exists(self, key):
        if not self.client:
            return False
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"exists 检查失败 [{key}]: {e}")
            return False

    # ---- 批量 & 统计 ----

    def clear_pattern(self, pattern):
        """按 pattern 批量删除（如 'chat:*'）"""
        if not self.client:
            return 0
        try:
            keys = self.client.keys(pattern)
            if not keys:
                return 0
            count = self.client.delete(*keys)
            logger.info(f"清除 {pattern} → {count} 条")
            return count
        except Exception as e:
            logger.error(f"clear_pattern 失败 [{pattern}]: {e}")
            return 0

    def get_stats(self):
        info = {
            "available": self.is_available(),
            "use_fake_redis": self.use_fake_redis,
            "default_ttl": self.ttl,
        }
        if self.client:
            try:
                raw = self.client.info()
                info["redis_version"] = raw.get("redis_version", "?")
                info["used_memory"] = raw.get("used_memory_human", "?")
                info["connected_clients"] = raw.get("connected_clients", 0)
                info["cache_keys_count"] = len(self.client.keys("huili:*") or [])
            except Exception as e:
                info["error"] = str(e)
        return info


# 全局单例
cache_manager = CacheManager()


# ---- 装饰器 ----

def cached(ttl=None, key_prefix=""):
    """给函数加缓存，ttl 秒，不传就用默认值"""
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            ck = cache_manager.generate_key(key_prefix, func.__name__, *args, **kwargs)
            hit = cache_manager.get(ck)
            if hit is not None:
                return hit
            result = func(*args, **kwargs)
            if result is not None:
                cache_manager.set(ck, result, ttl)
            return result
        return wrapper
    return deco


# ---- 聊天缓存快捷方法 ----

def cache_chat_response(user_input, session_id, response):
    """缓存一次对话回复"""
    ck = cache_manager.generate_key("chat", user_input)
    cached = response.copy()
    cached["cached"] = True
    cached["cache_timestamp"] = time.time()
    cached["session_id"] = session_id
    return cache_manager.set(ck, cached)


def get_cached_chat_response(user_input):
    ck = cache_manager.generate_key("chat", user_input)
    return cache_manager.get(ck)
