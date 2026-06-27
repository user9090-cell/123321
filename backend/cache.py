#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会理市AI数字人导游 - 缓存模块
功能：提供Redis缓存封装，支持fakeredis回退
作者：资深全栈架构师
日期：2026年4月20日
"""

import hashlib
import json
import logging
import time
from typing import Any, Optional, Dict, Union
from functools import wraps

from config import config

# 配置日志
logger = logging.getLogger(__name__)


class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        """初始化缓存管理器"""
        self.client = None
        self.use_fake_redis = config.USE_FAKE_REDIS
        self.ttl = config.CACHE_TTL
        
        self._init_cache_client()
    
    def _init_cache_client(self):
        """初始化缓存客户端"""
        try:
            if not self.use_fake_redis and config.REDIS_URL:
                # 使用真实Redis
                import redis
                self.client = redis.from_url(config.REDIS_URL)
                logger.info("使用真实Redis缓存")
            else:
                # 使用fakeredis
                import fakeredis
                self.client = fakeredis.FakeStrictRedis()
                logger.info("使用fakeredis模拟缓存")
                
        except ImportError as e:
            logger.warning(f"缓存库导入失败: {e}")
            self.client = None
        except Exception as e:
            logger.error(f"初始化缓存客户端失败: {e}")
            self.client = None
    
    def is_available(self) -> bool:
        """
        检查缓存是否可用
        
        Returns:
            bool: 缓存是否可用
        """
        return self.client is not None
    
    def generate_key(self, *args, **kwargs) -> str:
        """
        生成缓存键
        
        Args:
            *args: 位置参数
            **kwargs: 关键字参数
            
        Returns:
            str: 缓存键
        """
        # 将参数转换为字符串
        key_parts = []
        
        for arg in args:
            if isinstance(arg, (str, int, float, bool)):
                key_parts.append(str(arg))
            else:
                key_parts.append(hashlib.md5(str(arg).encode()).hexdigest())
        
        for key, value in sorted(kwargs.items()):
            if isinstance(value, (str, int, float, bool)):
                key_parts.append(f"{key}:{value}")
            else:
                key_parts.append(f"{key}:{hashlib.md5(str(value).encode()).hexdigest()}")
        
        # 生成MD5哈希
        key_string = "|".join(key_parts)
        return f"huili:{hashlib.md5(key_string.encode()).hexdigest()}"
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None表示使用默认值
            
        Returns:
            bool: 是否设置成功
        """
        if not self.is_available():
            return False
        
        try:
            # 序列化值
            if isinstance(value, (dict, list, tuple)):
                serialized_value = json.dumps(value, ensure_ascii=False)
            else:
                serialized_value = str(value)
            
            # 设置缓存
            expire_time = ttl if ttl is not None else self.ttl
            result = self.client.setex(key, expire_time, serialized_value)
            
            if result:
                logger.debug(f"缓存设置成功: {key} (TTL: {expire_time}s)")
            else:
                logger.warning(f"缓存设置失败: {key}")
            
            return bool(result)
            
        except Exception as e:
            logger.error(f"设置缓存失败 {key}: {e}")
            return False
    
    def get(self, key: str) -> Optional[Any]:
        """
        获取缓存
        
        Args:
            key: 缓存键
            
        Returns:
            Optional[Any]: 缓存值，不存在返回None
        """
        if not self.is_available():
            return None
        
        try:
            value = self.client.get(key)
            if value is None:
                return None
            
            # 尝试反序列化JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                # 如果不是JSON，返回原始字符串
                return value.decode('utf-8')
                
        except Exception as e:
            logger.error(f"获取缓存失败 {key}: {e}")
            return None
    
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否删除成功
        """
        if not self.is_available():
            return False
        
        try:
            result = self.client.delete(key)
            logger.debug(f"缓存删除: {key} (删除数量: {result})")
            return result > 0
        except Exception as e:
            logger.error(f"删除缓存失败 {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """
        检查缓存是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            bool: 是否存在
        """
        if not self.is_available():
            return False
        
        try:
            return self.client.exists(key) > 0
        except Exception as e:
            logger.error(f"检查缓存存在失败 {key}: {e}")
            return False
    
    def clear_pattern(self, pattern: str) -> int:
        """
        清除匹配模式的缓存
        
        Args:
            pattern: 键模式（支持通配符）
            
        Returns:
            int: 删除的键数量
        """
        if not self.is_available():
            return 0
        
        try:
            keys = self.client.keys(pattern)
            if keys:
                count = self.client.delete(*keys)
                logger.info(f"清除缓存模式 {pattern}: 删除 {count} 个键")
                return count
            return 0
        except Exception as e:
            logger.error(f"清除缓存模式失败 {pattern}: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            Dict[str, Any]: 统计信息
        """
        stats = {
            "available": self.is_available(),
            "use_fake_redis": self.use_fake_redis,
            "default_ttl": self.ttl,
        }
        
        if self.is_available():
            try:
                # 获取缓存信息
                info = self.client.info()
                stats.update({
                    "redis_version": info.get("redis_version", "unknown"),
                    "used_memory": info.get("used_memory_human", "unknown"),
                    "connected_clients": info.get("connected_clients", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                })
                
                # 统计缓存键数量（仅统计huili:开头的键）
                pattern = "huili:*"
                keys = self.client.keys(pattern)
                stats["cache_keys_count"] = len(keys)
                
            except Exception as e:
                logger.error(f"获取缓存统计信息失败: {e}")
                stats["error"] = str(e)
        
        return stats


# 全局缓存实例
cache_manager = CacheManager()


def cached(ttl: Optional[int] = None, key_prefix: str = ""):
    """
    缓存装饰器
    
    Args:
        ttl: 缓存过期时间（秒）
        key_prefix: 键前缀
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = cache_manager.generate_key(key_prefix, func.__name__, *args, **kwargs)
            
            # 尝试从缓存获取
            cached_result = cache_manager.get(cache_key)
            if cached_result is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return cached_result
            
            # 执行函数
            result = func(*args, **kwargs)
            
            # 缓存结果
            if result is not None:
                cache_manager.set(cache_key, result, ttl)
                logger.debug(f"缓存设置: {cache_key}")
            
            return result
        return wrapper
    return decorator


def cache_chat_response(user_input: str, session_id: str, response: Dict[str, Any]) -> bool:
    """
    缓存聊天响应
    
    Args:
        user_input: 用户输入
        session_id: 会话ID
        response: 响应数据
        
    Returns:
        bool: 是否缓存成功
    """
    # 生成基于用户输入的缓存键
    cache_key = cache_manager.generate_key("chat", user_input)
    
    # 添加会话信息到响应
    cached_response = response.copy()
    cached_response["cached"] = True
    cached_response["cache_timestamp"] = time.time()
    cached_response["session_id"] = session_id
    
    return cache_manager.set(cache_key, cached_response)


def get_cached_chat_response(user_input: str) -> Optional[Dict[str, Any]]:
    """
    获取缓存的聊天响应
    
    Args:
        user_input: 用户输入
        
    Returns:
        Optional[Dict[str, Any]]: 缓存的响应数据
    """
    cache_key = cache_manager.generate_key("chat", user_input)
    return cache_manager.get(cache_key)


if __name__ == "__main__":
    # 测试缓存功能
    import sys
    
    # 配置日志级别
    logging.basicConfig(level=logging.DEBUG)
    
    # 创建缓存管理器
    cm = CacheManager()
    
    print("缓存测试:")
    print(f"缓存可用: {cm.is_available()}")
    print(f"使用fakeredis: {cm.use_fake_redis}")
    
    # 测试设置和获取
    test_key = "test:key"
    test_value = {"message": "Hello, World!", "timestamp": time.time()}
    
    print(f"\n设置缓存: {test_key}")
    cm.set(test_key, test_value, ttl=60)
    
    print(f"获取缓存: {test_key}")
    cached_value = cm.get(test_key)
    print(f"缓存值: {cached_value}")
    
    print(f"缓存存在: {cm.exists(test_key)}")
    
    # 测试装饰器
    @cached(ttl=30, key_prefix="test")
    def expensive_operation(x: int, y: int) -> int:
        print(f"执行昂贵操作: {x} + {y}")
        time.sleep(0.1)  # 模拟耗时操作
        return x + y
    
    print("\n测试缓存装饰器:")
    result1 = expensive_operation(10, 20)
    print(f"第一次调用结果: {result1}")
    
    result2 = expensive_operation(10, 20)
    print(f"第二次调用结果: {result2} (应该来自缓存)")
    
    # 获取统计信息
    stats = cm.get_stats()
    print(f"\n缓存统计: {stats}")