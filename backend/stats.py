#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会理市AI数字人导游 - 统计与日志模块
功能：记录对话日志、统计服务数据、管理用户反馈
作者：资深全栈架构师
日期：2026年4月20日
"""

import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict, Counter

from config import config

# 配置日志
logger = logging.getLogger(__name__)


class StatisticsManager:
    """统计管理器"""
    
    def __init__(self):
        """初始化统计管理器"""
        self.start_time = datetime.now()
        self.logs_dir = Path(config.LOGS_DIR)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        
        # 内存中的统计数据
        self.session_data = {}  # 会话数据
        self.feedback_data = []  # 反馈数据
        self.daily_stats = defaultdict(lambda: {
            "total_requests": 0,
            "unique_users": set(),
            "popular_queries": Counter(),
            "response_times": [],
            "feedback_counts": {"like": 0, "dislike": 0}
        })
        
        # 加载历史数据
        self._load_historical_data()
    
    def _load_historical_data(self):
        """加载历史数据"""
        try:
            # 加载反馈数据
            feedback_file = self.logs_dir / "feedback.json"
            if feedback_file.exists():
                with open(feedback_file, 'r', encoding='utf-8') as f:
                    self.feedback_data = json.load(f)
                logger.info(f"加载 {len(self.feedback_data)} 条反馈数据")
            
            # 加载会话数据（简化实现）
            logger.info("统计管理器初始化完成")
            
        except Exception as e:
            logger.error(f"加载历史数据失败: {e}")
    
    def _save_feedback_data(self):
        """保存反馈数据"""
        try:
            feedback_file = self.logs_dir / "feedback.json"
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(self.feedback_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存反馈数据失败: {e}")
    
    def log_chat(self, session_id: str, user_input: str, reply: str, 
                latency_ms: float, model_used: str, source_results: List[Dict[str, Any]] = None):
        """
        记录聊天日志
        
        Args:
            session_id: 会话ID
            user_input: 用户输入
            reply: 回复内容
            latency_ms: 响应时间（毫秒）
            model_used: 使用的模型
            source_results: 检索结果
        """
        try:
            # 创建日志条目
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "user_input": user_input,
                "reply": reply[:500] if len(reply) > 500 else reply,  # 限制长度
                "latency_ms": round(latency_ms, 2),
                "model_used": model_used,
                "source_count": len(source_results) if source_results else 0
            }
            
            # 添加到会话数据
            if session_id not in self.session_data:
                self.session_data[session_id] = {
                    "start_time": datetime.now().isoformat(),
                    "request_count": 0,
                    "last_activity": datetime.now().isoformat(),
                    "queries": []
                }
            
            self.session_data[session_id]["request_count"] += 1
            self.session_data[session_id]["last_activity"] = datetime.now().isoformat()
            self.session_data[session_id]["queries"].append(user_input)
            
            # 更新每日统计
            today = datetime.now().strftime("%Y-%m-%d")
            self.daily_stats[today]["total_requests"] += 1
            self.daily_stats[today]["unique_users"].add(session_id)
            self.daily_stats[today]["popular_queries"][user_input] += 1
            self.daily_stats[today]["response_times"].append(latency_ms)
            
            # 写入日志文件
            log_file = self.logs_dir / "chat.log"
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            
            logger.debug(f"记录聊天日志: session={session_id}, latency={latency_ms}ms")
            
        except Exception as e:
            logger.error(f"记录聊天日志失败: {e}")
    
    def log_feedback(self, session_id: str, message_id: str, feedback: str):
        """
        记录用户反馈
        
        Args:
            session_id: 会话ID
            message_id: 消息ID
            feedback: 反馈类型（like/dislike）
        """
        try:
            feedback_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "message_id": message_id,
                "feedback": feedback
            }
            
            # 添加到反馈数据
            self.feedback_data.append(feedback_entry)
            
            # 更新每日统计
            today = datetime.now().strftime("%Y-%m-%d")
            if feedback in ["like", "dislike"]:
                self.daily_stats[today]["feedback_counts"][feedback] += 1
            
            # 保存反馈数据
            self._save_feedback_data()
            
            logger.info(f"记录用户反馈: session={session_id}, feedback={feedback}")
            
        except Exception as e:
            logger.error(f"记录用户反馈失败: {e}")
    
    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """
        获取会话统计信息
        
        Args:
            session_id: 会话ID
            
        Returns:
            Dict[str, Any]: 会话统计信息
        """
        if session_id not in self.session_data:
            return {"error": "会话不存在"}
        
        session_info = self.session_data[session_id]
        
        return {
            "session_id": session_id,
            "start_time": session_info["start_time"],
            "request_count": session_info["request_count"],
            "last_activity": session_info["last_activity"],
            "query_count": len(session_info["queries"])
        }
    
    def get_daily_stats(self, date_str: Optional[str] = None) -> Dict[str, Any]:
        """
        获取每日统计信息
        
        Args:
            date_str: 日期字符串（YYYY-MM-DD），None表示今天
            
        Returns:
            Dict[str, Any]: 每日统计信息
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        
        if date_str not in self.daily_stats:
            return {
                "date": date_str,
                "total_requests": 0,
                "unique_users": 0,
                "avg_response_time": 0,
                "popular_queries": [],
                "feedback_counts": {"like": 0, "dislike": 0}
            }
        
        stats = self.daily_stats[date_str]
        response_times = stats["response_times"]
        
        return {
            "date": date_str,
            "total_requests": stats["total_requests"],
            "unique_users": len(stats["unique_users"]),
            "avg_response_time": round(sum(response_times) / len(response_times), 2) if response_times else 0,
            "popular_queries": [
                {"query": query, "count": count}
                for query, count in stats["popular_queries"].most_common(10)
            ],
            "feedback_counts": dict(stats["feedback_counts"])
        }
    
    def get_overall_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        获取总体统计信息
        
        Args:
            days: 统计天数
            
        Returns:
            Dict[str, Any]: 总体统计信息
        """
        try:
            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # 收集数据
            total_requests = 0
            total_users = set()
            all_response_times = []
            feedback_counts = {"like": 0, "dislike": 0}
            daily_data = []
            
            current_date = start_date
            while current_date <= end_date:
                date_str = current_date.strftime("%Y-%m-%d")
                daily_stat = self.get_daily_stats(date_str)
                
                total_requests += daily_stat["total_requests"]
                total_users.update([f"{date_str}:{i}" for i in range(daily_stat["unique_users"])])
                if daily_stat["avg_response_time"] > 0:
                    all_response_times.append(daily_stat["avg_response_time"])
                
                feedback_counts["like"] += daily_stat["feedback_counts"]["like"]
                feedback_counts["dislike"] += daily_stat["feedback_counts"]["dislike"]
                
                daily_data.append({
                    "date": date_str,
                    "requests": daily_stat["total_requests"],
                    "users": daily_stat["unique_users"]
                })
                
                current_date += timedelta(days=1)
            
            # 计算热门问题（最近7天）
            recent_queries = Counter()
            for date_str, stats in self.daily_stats.items():
                stat_date = datetime.strptime(date_str, "%Y-%m-%d")
                if start_date <= stat_date <= end_date:
                    recent_queries.update(stats["popular_queries"])
            
            return {
                "period": f"{days}天",
                "total_requests": total_requests,
                "total_unique_users": len(total_users),
                "avg_response_time": round(sum(all_response_times) / len(all_response_times), 2) if all_response_times else 0,
                "daily_data": daily_data,
                "popular_queries": [
                    {"query": query, "count": count}
                    for query, count in recent_queries.most_common(10)
                ],
                "feedback_summary": {
                    "like": feedback_counts["like"],
                    "dislike": feedback_counts["dislike"],
                    "satisfaction_rate": round(
                        feedback_counts["like"] / max(feedback_counts["like"] + feedback_counts["dislike"], 1) * 100, 2
                    )
                },
                "active_sessions": len(self.session_data)
            }
            
        except Exception as e:
            logger.error(f"获取总体统计信息失败: {e}")
            return {"error": str(e)}
    
    def get_recent_logs(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取最近日志
        
        Args:
            limit: 日志条数限制
            
        Returns:
            List[Dict[str, Any]]: 最近日志列表
        """
        try:
            log_file = self.logs_dir / "chat.log"
            if not log_file.exists():
                return []
            
            # 读取最后N行
            with open(log_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            recent_logs = []
            for line in lines[-limit:]:
                try:
                    log_entry = json.loads(line.strip())
                    recent_logs.append(log_entry)
                except json.JSONDecodeError:
                    continue
            
            return recent_logs[::-1]  # 反转，最新的在前
            
        except Exception as e:
            logger.error(f"获取最近日志失败: {e}")
            return []
    
    def cleanup_old_sessions(self, max_age_hours: int = 24):
        """
        清理旧会话
        
        Args:
            max_age_hours: 最大年龄（小时）
        """
        try:
            cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
            sessions_to_remove = []
            
            for session_id, session_info in self.session_data.items():
                last_activity = datetime.fromisoformat(session_info["last_activity"])
                if last_activity < cutoff_time:
                    sessions_to_remove.append(session_id)
            
            for session_id in sessions_to_remove:
                del self.session_data[session_id]
            
            if sessions_to_remove:
                logger.info(f"清理 {len(sessions_to_remove)} 个旧会话")
                
        except Exception as e:
            logger.error(f"清理旧会话失败: {e}")
    
    def export_stats(self, output_file: Optional[str] = None) -> str:
        """
        导出统计信息
        
        Args:
            output_file: 输出文件路径，None表示生成默认路径
            
        Returns:
            str: 导出文件路径
        """
        try:
            if output_file is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_file = self.logs_dir / f"stats_export_{timestamp}.json"
            else:
                output_file = Path(output_file)
            
            export_data = {
                "export_time": datetime.now().isoformat(),
                "overall_stats": self.get_overall_stats(30),
                "recent_logs": self.get_recent_logs(100),
                "feedback_data": self.feedback_data[-100:],  # 最近100条反馈
                "active_sessions_count": len(self.session_data)
            }
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"统计信息已导出到: {output_file}")
            return str(output_file)
            
        except Exception as e:
            logger.error(f"导出统计信息失败: {e}")
            raise

    def get_uptime(self) -> str:
        """获取服务运行时长。"""
        uptime = datetime.now() - self.start_time
        total_seconds = int(uptime.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


# 全局统计管理器实例
stats_manager = StatisticsManager()


if __name__ == "__main__":
    # 测试统计管理器
    import sys
    
    # 配置日志
    logging.basicConfig(level=logging.INFO)
    
    print("测试统计管理器...")
    
    try:
        # 创建管理器
        manager = StatisticsManager()
        
        # 生成测试数据
        test_session_id = str(uuid.uuid4())
        
        print(f"测试会话ID: {test_session_id}")
        
        # 记录测试聊天
        for i in range(3):
            manager.log_chat(
                session_id=test_session_id,
                user_input=f"测试问题 {i+1}",
                reply=f"测试回答 {i+1}",
                latency_ms=150 + i * 50,
                model_used="mimo-v2-flash"
            )
        
        # 记录测试反馈
        manager.log_feedback(
            session_id=test_session_id,
            message_id="test_msg_1",
            feedback="like"
        )
        
        # 获取会话统计
        print(f"\n会话统计:")
        session_stats = manager.get_session_stats(test_session_id)
        for key, value in session_stats.items():
            print(f"  {key}: {value}")
        
        # 获取每日统计
        print(f"\n今日统计:")
        daily_stats = manager.get_daily_stats()
        for key, value in daily_stats.items():
            if key == "popular_queries":
                print(f"  {key}:")
                for item in value:
                    print(f"    - {item['query']}: {item['count']}")
            elif key == "feedback_counts":
                print(f"  {key}:")
                for fb_key, fb_value in value.items():
                    print(f"    - {fb_key}: {fb_value}")
            else:
                print(f"  {key}: {value}")
        
        # 获取总体统计
        print(f"\n总体统计 (7天):")
        overall_stats = manager.get_overall_stats(7)
        for key, value in overall_stats.items():
            if key == "popular_queries":
                print(f"  {key}:")
                for item in value[:5]:
                    print(f"    - {item['query']}: {item['count']}")
            elif key == "feedback_summary":
                print(f"  {key}:")
                for fb_key, fb_value in value.items():
                    print(f"    - {fb_key}: {fb_value}")
            elif key == "daily_data":
                print(f"  {key}: 共 {len(value)} 天的数据")
            else:
                print(f"  {key}: {value}")
        
        # 获取最近日志
        print(f"\n最近日志:")
        recent_logs = manager.get_recent_logs(5)
        for i, log in enumerate(recent_logs, 1):
            print(f"  {i}. [{log['timestamp']}] {log['user_input'][:30]}...")
        
        # 清理旧会话
        manager.cleanup_old_sessions(1)
        
        print("\n✅ 统计管理器测试完成")
        
    except Exception as e:
        print(f"❌ 统计管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


class StatsManager(StatisticsManager):
    """兼容 app.py 旧接口的统计管理器包装类。"""

    def record_request(
        self,
        session_id: str,
        user_input: str,
        response: str,
        from_cache: bool,
        latency_ms: float,
        model_used: str = "unknown",
        source_results: Optional[List[Dict[str, Any]]] = None
    ):
        self.log_chat(
            session_id=session_id,
            user_input=user_input,
            reply=response,
            latency_ms=latency_ms,
            model_used=model_used,
            source_results=source_results or []
        )

    def record_feedback(self, session_id: str, message_id: str, feedback: str):
        self.log_feedback(session_id, message_id, feedback)

    def log_survey(self, session_id: str, rating: int, comment: str = ""):
        try:
            survey_entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "rating": rating,
                "comment": comment
            }
            self.feedback_data.append(survey_entry)

            today = datetime.now().strftime("%Y-%m-%d")
            if "survey_ratings" not in self.daily_stats[today]:
                self.daily_stats[today]["survey_ratings"] = []
            self.daily_stats[today]["survey_ratings"].append(rating)

            self._save_feedback_data()
            logger.info(f"记录满意度调研: session={session_id}, rating={rating}")
        except Exception as e:
            logger.error(f"记录满意度调研失败: {e}")

    def record_error(self, endpoint: str, error_message: str):
        logger.error(f"[{endpoint}] {error_message}")

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        return self.get_overall_stats(days)
