# 会理AI导游 - 统计模块
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import defaultdict, Counter

from config import config

logger = logging.getLogger(__name__)


class StatisticsManager:

    def __init__(self):
        self.start_time = datetime.now()
        self.logs_dir = Path(config.LOGS_DIR)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        self.session_data = {}
        self.feedback_data = []
        self.daily_stats = defaultdict(lambda: {
            "total_requests": 0,
            "unique_users": set(),
            "popular_queries": Counter(),
            "response_times": [],
            "feedback_counts": {"like": 0, "dislike": 0},
        })

        self._load_feedback()

    def _load_feedback(self):
        fb_file = self.logs_dir / "feedback.json"
        if fb_file.exists():
            try:
                with open(fb_file, 'r', encoding='utf-8') as f:
                    self.feedback_data = json.load(f)
                logger.info(f"加载 {len(self.feedback_data)} 条反馈")
            except Exception as e:
                logger.error(f"读取反馈数据失败: {e}")

    def _save_feedback(self):
        try:
            fb_file = self.logs_dir / "feedback.json"
            with open(fb_file, 'w', encoding='utf-8') as f:
                json.dump(self.feedback_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存反馈失败: {e}")

    # ---- 日志记录 ----

    def log_chat(self, session_id, user_input, reply, latency_ms, model_used, source_results=None):
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "user_input": user_input,
                "reply": reply[:500] if len(reply) > 500 else reply,
                "latency_ms": round(latency_ms, 2),
                "model_used": model_used,
                "source_count": len(source_results) if source_results else 0,
            }

            if session_id not in self.session_data:
                self.session_data[session_id] = {
                    "start_time": datetime.now().isoformat(),
                    "request_count": 0,
                    "last_activity": datetime.now().isoformat(),
                    "queries": [],
                }
            self.session_data[session_id]["request_count"] += 1
            self.session_data[session_id]["last_activity"] = datetime.now().isoformat()
            self.session_data[session_id]["queries"].append(user_input)

            today = datetime.now().strftime("%Y-%m-%d")
            self.daily_stats[today]["total_requests"] += 1
            self.daily_stats[today]["unique_users"].add(session_id)
            self.daily_stats[today]["popular_queries"][user_input] += 1
            self.daily_stats[today]["response_times"].append(latency_ms)

            with open(self.logs_dir / "chat.log", 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"log_chat 失败: {e}")

    def log_feedback(self, session_id, message_id, feedback):
        try:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
                "message_id": message_id,
                "feedback": feedback,
            }
            self.feedback_data.append(entry)
            today = datetime.now().strftime("%Y-%m-%d")
            if feedback in ("like", "dislike"):
                self.daily_stats[today]["feedback_counts"][feedback] += 1
            self._save_feedback()
            logger.info(f"反馈记录: {session_id} → {feedback}")
        except Exception as e:
            logger.error(f"log_feedback 失败: {e}")

    # ---- 查询 ----

    def get_session_stats(self, session_id):
        s = self.session_data.get(session_id)
        if not s:
            return {"error": "会话不存在"}
        return {
            "session_id": session_id,
            "start_time": s["start_time"],
            "request_count": s["request_count"],
            "last_activity": s["last_activity"],
            "query_count": len(s["queries"]),
        }

    def get_daily_stats(self, date_str=None):
        ds = date_str or datetime.now().strftime("%Y-%m-%d")
        if ds not in self.daily_stats:
            return {"date": ds, "total_requests": 0, "unique_users": 0, "avg_response_time": 0, "popular_queries": [], "feedback_counts": {"like": 0, "dislike": 0}}
        st = self.daily_stats[ds]
        rts = st["response_times"]
        return {
            "date": ds,
            "total_requests": st["total_requests"],
            "unique_users": len(st["unique_users"]),
            "avg_response_time": round(sum(rts) / len(rts), 2) if rts else 0,
            "popular_queries": [{"query": q, "count": c} for q, c in st["popular_queries"].most_common(10)],
            "feedback_counts": dict(st["feedback_counts"]),
        }

    def get_overall_stats(self, days=7):
        try:
            end = datetime.now()
            start = end - timedelta(days=days)
            total_req, total_users, all_rts = 0, set(), []
            fb = {"like": 0, "dislike": 0}
            daily_data = []

            cur = start
            while cur <= end:
                ds = cur.strftime("%Y-%m-%d")
                ds_info = self.get_daily_stats(ds)
                total_req += ds_info["total_requests"]
                total_users.update([f"{ds}:{i}" for i in range(ds_info["unique_users"])])
                if ds_info["avg_response_time"] > 0:
                    all_rts.append(ds_info["avg_response_time"])
                fb["like"] += ds_info["feedback_counts"]["like"]
                fb["dislike"] += ds_info["feedback_counts"]["dislike"]
                daily_data.append({"date": ds, "requests": ds_info["total_requests"], "users": ds_info["unique_users"]})
                cur += timedelta(days=1)

            recent = Counter()
            for ds_str, st in self.daily_stats.items():
                sd = datetime.strptime(ds_str, "%Y-%m-%d")
                if start <= sd <= end:
                    recent.update(st["popular_queries"])

            total_fb = fb["like"] + fb["dislike"]
            return {
                "period": f"{days}天",
                "total_requests": total_req,
                "total_unique_users": len(total_users),
                "avg_response_time": round(sum(all_rts) / len(all_rts), 2) if all_rts else 0,
                "daily_data": daily_data,
                "popular_queries": [{"query": q, "count": c} for q, c in recent.most_common(10)],
                "feedback_summary": {"like": fb["like"], "dislike": fb["dislike"], "satisfaction_rate": round(fb["like"] / max(total_fb, 1) * 100, 2)},
                "active_sessions": len(self.session_data),
            }
        except Exception as e:
            logger.error(f"get_overall_stats 失败: {e}")
            return {"error": str(e)}

    def get_recent_logs(self, limit=20):
        logf = self.logs_dir / "chat.log"
        if not logf.exists():
            return []
        try:
            lines = open(logf, 'r', encoding='utf-8').readlines()
            logs = []
            for line in lines[-limit:]:
                try:
                    logs.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    continue
            return logs[::-1]
        except Exception as e:
            logger.error(f"读取日志失败: {e}")
            return []

    # ---- 维护 ----

    def cleanup_old_sessions(self, max_age_hours=24):
        try:
            cutoff = datetime.now() - timedelta(hours=max_age_hours)
            to_remove = [
                sid for sid, info in self.session_data.items()
                if datetime.fromisoformat(info["last_activity"]) < cutoff
            ]
            for sid in to_remove:
                del self.session_data[sid]
            if to_remove:
                logger.info(f"清理 {len(to_remove)} 个过期会话")
        except Exception as e:
            logger.error(f"清理会话失败: {e}")

    def export_stats(self, output_file=None):
        if output_file is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.logs_dir / f"stats_export_{ts}.json"
        else:
            output_file = Path(output_file)
        data = {
            "export_time": datetime.now().isoformat(),
            "overall_stats": self.get_overall_stats(30),
            "recent_logs": self.get_recent_logs(100),
            "feedback_data": self.feedback_data[-100:],
            "active_sessions_count": len(self.session_data),
        }
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"统计已导出: {output_file}")
        return str(output_file)

    def get_uptime(self):
        secs = int((datetime.now() - self.start_time).total_seconds())
        h, m = divmod(secs, 3600)
        m, s = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"


# 兼容旧接口
class StatsManager(StatisticsManager):

    def record_request(self, session_id, user_input, response, from_cache, latency_ms, model_used="unknown", source_results=None):
        self.log_chat(session_id, user_input, response, latency_ms, model_used, source_results or [])

    def record_feedback(self, session_id, message_id, feedback):
        self.log_feedback(session_id, message_id, feedback)

    def log_survey(self, session_id, rating, comment=""):
        try:
            entry = {"timestamp": datetime.now().isoformat(), "session_id": session_id, "rating": rating, "comment": comment}
            self.feedback_data.append(entry)
            today = datetime.now().strftime("%Y-%m-%d")
            self.daily_stats[today].setdefault("survey_ratings", []).append(rating)
            self._save_feedback()
            logger.info(f"满意度调研: {session_id} → {rating}分")
        except Exception as e:
            logger.error(f"记录调研失败: {e}")

    def record_error(self, endpoint, error_message):
        logger.error(f"[{endpoint}] {error_message}")

    def get_stats(self, days=7):
        return self.get_overall_stats(days)
