
import os

# 必须最先设置 HuggingFace 环境变量（在任何模型/模块导入前）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HOME"] = os.path.join(PROJECT_ROOT, "models", "hub")
os.environ["HUGGINGFACE_HUB_CACHE"] = os.path.join(PROJECT_ROOT, "models", "hub")
os.environ["TRANSFORMERS_CACHE"] = os.path.join(PROJECT_ROOT, "models", "hub")

import json
import time
import logging
import hashlib
import re
import urllib.parse
import mimetypes
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import requests as http_requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

# 导入自定义模块
from config import Config
from cache import CacheManager
from rag_engine import RAGEngine
from stats import StatsManager
from user_manager import UserManager
from admin_manager import AdminManager
from scenic_manager import ScenicImageManager

# 初始化应用
mimetypes.add_type('application/octet-stream', '.moc')
mimetypes.add_type('application/octet-stream', '.mtn')
mimetypes.add_type('application/json', '.exp3.json')
app = Flask(__name__)
app.config.from_object(Config)

# 启用CORS（开发环境）
if Config.ENABLE_CORS:
    CORS(app, resources={r"/api/*": {"origins": "*", "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"], "allow_headers": ["Content-Type", "X-Session-ID", "X-Admin-User", "X-Admin-Password", "X-Phone"]}})

# 配置日志
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 初始化组件
cache_manager = CacheManager()
rag_engine = RAGEngine()
stats_manager = StatsManager()
user_manager = UserManager()
admin_manager = AdminManager()
scenic_manager = ScenicImageManager()

# 会话管理
sessions = {}

# ========== 辅助函数 ==========

def generate_session_id() -> str:
    """生成会话ID"""
    return hashlib.md5(f"{time.time()}{os.urandom(16)}".encode()).hexdigest()

def get_session(session_id: str) -> Dict:
    """获取或创建会话"""
    if session_id not in sessions:
        sessions[session_id] = {
            "id": session_id,
            "created_at": datetime.now(),
            "last_active": datetime.now(),
            "messages": [],
            "user_location": None,
            "preferences": {}
        }
    else:
        sessions[session_id]["last_active"] = datetime.now()
    
    return sessions[session_id]

def validate_request(data: Dict, required_fields: List[str]) -> Optional[Dict]:
    """验证请求数据"""
    if not data:
        return {"success": False, "error": "请求数据不能为空"}
    
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return {"success": False, "error": f"缺少必要字段: {', '.join(missing_fields)}"}
    
    return None


def process_chat_request(data: Dict[str, Any], start_time: Optional[float] = None):
    """处理聊天请求，供文本和语音接口复用。"""
    start_time = start_time or time.time()

    validation_error = validate_request(data, ["user_input"])
    if validation_error:
        return validation_error, 400

    user_input = str(data["user_input"]).strip()
    session_id = data.get("session_id")
    latitude = data.get("latitude")
    longitude = data.get("longitude")

    if not user_input:
        return {
            "success": False,
            "error": "用户输入不能为空"
        }, 400

    if not session_id:
        session_id = generate_session_id()

    session = get_session(session_id)

    if latitude is not None and longitude is not None:
        session["user_location"] = {
            "latitude": float(latitude),
            "longitude": float(longitude)
        }

    cache_key = f"chat:{hashlib.md5(user_input.encode()).hexdigest()}"
    cached_response = cache_manager.get(cache_key)

    if cached_response:
        logger.info(f"缓存命中: {user_input[:50]}...")

        session["messages"].append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now()
        })

        session["messages"].append({
            "role": "assistant",
            "content": cached_response["reply"],
            "timestamp": datetime.now(),
            "from_cache": True
        })

        stats_manager.record_request(
            session_id=session_id,
            user_input=user_input,
            response=cached_response["reply"],
            from_cache=True,
            latency_ms=(time.time() - start_time) * 1000
        )

        return {
            "success": True,
            "reply": cached_response["reply"],
            "session_id": session_id,
            "source": cached_response.get("source", []),
            "suggestions": cached_response.get("suggestions", []),
            "from_cache": True,
            "latency_ms": round((time.time() - start_time) * 1000, 2)
        }, 200

    logger.info(f"处理请求: {user_input[:50]}...")

    context = {
        "user_input": user_input,
        "session_id": session_id,
        "user_location": session.get("user_location"),
        "conversation_history": session["messages"][-5:]
    }

    result = rag_engine.generate_response(context)

    cache_manager.set(cache_key, {
        "reply": result["reply"],
        "source": result.get("source", []),
        "suggestions": result.get("suggestions", [])
    }, ttl=Config.CACHE_TTL)

    session["messages"].append({
        "role": "user",
        "content": user_input,
        "timestamp": datetime.now()
    })

    session["messages"].append({
        "role": "assistant",
        "content": result["reply"],
        "timestamp": datetime.now(),
        "source": result.get("source", []),
        "model_used": result.get("model_used")
    })

    stats_manager.record_request(
        session_id=session_id,
        user_input=user_input,
        response=result["reply"],
        from_cache=False,
        latency_ms=(time.time() - start_time) * 1000,
        model_used=result.get("model_used")
    )

    return {
        "success": True,
        "reply": result["reply"],
        "session_id": session_id,
        "source": result.get("source", []),
        "suggestions": result.get("suggestions", []),
        "latency_ms": round((time.time() - start_time) * 1000, 2),
        "model_used": result.get("model_used", "unknown")
    }, 200

# ========== API路由 ==========

@app.route('/api/health', methods=['GET'])
def api_health():
    """健康检查接口"""
    try:
        # 检查各个组件状态
        components = {
            "flask": True,
            "cache": cache_manager.is_available(),
            "rag_engine": rag_engine.is_available(),
            "knowledge_base": rag_engine.has_knowledge_base()
        }

        # 缓存属于可降级组件，不应导致整体服务被判定为不可用
        critical_components = {
            "flask": components["flask"],
            "rag_engine": components["rag_engine"]
        }
        healthy = all(critical_components.values())
        degraded = healthy and not all(components.values())
        
        return jsonify({
            "success": True,
            "healthy": healthy,
            "degraded": degraded,
            "components": components,
            "timestamp": datetime.now().isoformat(),
            "uptime": stats_manager.get_uptime(),
            "version": "1.0.0"
        })
    
    except Exception as e:
        logger.error(f"健康检查异常: {str(e)}")
        return jsonify({
            "success": False,
            "healthy": False,
            "error": str(e)
        }), 500

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据不能为空"}), 400
        result = user_manager.register(
            data.get("phone", ""),
            data.get("password", "")
        )
        if result["success"]:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"注册异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据不能为空"}), 400
        result = user_manager.login(
            data.get("phone", ""),
            data.get("password", "")
        )
        if result["success"]:
            sessions[result["session_id"]] = {
                "phone": result["phone"],
                "created_at": datetime.now().isoformat()
            }
            return jsonify(result)
        return jsonify(result), 401
    except Exception as e:
        logger.error(f"登录异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/user/stats', methods=['GET'])
def api_user_stats():
    try:
        stats = user_manager.get_stats()
        users = user_manager.get_all_users()
        return jsonify({"success": True, "stats": stats, "users": users})
    except Exception as e:
        logger.error(f"获取用户统计异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/logout', methods=['POST'])
def api_logout():
    try:
        data = request.get_json()
        phone = (data or {}).get("phone", "")
        result = user_manager.logout(phone)
        if result["success"]:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"退出登录异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/user/info', methods=['GET'])
def api_user_info():
    try:
        phone = request.args.get("phone", "").strip()
        if not phone:
            return jsonify({"success": False, "error": "缺少手机号"}), 400
        user = user_manager.get_user(phone)
        if not user:
            return jsonify({"success": False, "error": "用户不存在"}), 404
        return jsonify({"success": True, "user": user})
    except Exception as e:
        logger.error(f"获取用户信息异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/user/change_password', methods=['POST'])
def api_change_password():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据不能为空"}), 400
        result = user_manager.change_password(
            data.get("phone", ""),
            data.get("old_password", ""),
            data.get("new_password", "")
        )
        if result["success"]:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"修改密码异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/user/delete', methods=['POST'])
def api_delete_account():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据不能为空"}), 400
        result = user_manager.delete_account(
            data.get("phone", ""),
            data.get("password", "")
        )
        if result["success"]:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"注销账号异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据不能为空"}), 400
        result = admin_manager.login(
            data.get("username", ""),
            data.get("password", "")
        )
        if result["success"]:
            return jsonify(result)
        return jsonify(result), 401
    except Exception as e:
        logger.error(f"管理员登录异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/change_password', methods=['POST'])
def api_admin_change_password():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据不能为空"}), 400
        result = admin_manager.change_password(
            data.get("username", ""),
            data.get("old_password", ""),
            data.get("new_password", "")
        )
        if result["success"]:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"管理员改密异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/info', methods=['GET'])
def api_admin_info():
    username = request.args.get("username", "").strip()
    if not username:
        return jsonify({"success": False, "error": "缺少账号"}), 400
    admin = admin_manager.get_admin(username)
    if not admin:
        return jsonify({"success": False, "error": "账号不存在"}), 404
    return jsonify({"success": True, "admin": admin})

@app.route('/api/avatar/upload', methods=['POST'])
def api_avatar_upload():
    try:
        phone = (request.form or {}).get("phone", "").strip()
        if not phone:
            return jsonify({"success": False, "error": "缺少手机号"}), 400
        if 'avatar' not in request.files:
            return jsonify({"success": False, "error": "未找到头像文件"}), 400
        file = request.files['avatar']
        if file.filename == '':
            return jsonify({"success": False, "error": "未选择文件"}), 400
        allowed_ext = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_ext:
            return jsonify({"success": False, "error": "仅支持 PNG/JPG/GIF/WEBP 格式"}), 400
        safe_name = hashlib.md5(f"{phone}{time.time()}".encode()).hexdigest()[:12]
        filename = f"{safe_name}{ext}"
        save_path = os.path.join(str(user_manager.avatars_dir), filename)
        file.save(save_path)
        result = user_manager.update_avatar(phone, filename)
        if result["success"]:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        logger.error(f"头像上传异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/avatar/<phone>', methods=['GET'])
def api_avatar_get(phone):
    try:
        avatar_path = user_manager.get_avatar_path(phone)
        if avatar_path:
            return send_from_directory(os.path.dirname(avatar_path), os.path.basename(avatar_path))
        return '', 204
    except Exception as e:
        logger.error(f"获取头像异常: {str(e)}")
        return '', 204

@app.route('/api/chat', methods=['POST'])
def api_chat():
    """
    聊天接口
    
    请求格式:
    {
        "user_input": "用户输入的问题",
        "session_id": "可选，会话ID",
        "latitude": 可选，纬度,
        "longitude": 可选，经度
    }
    """
    start_time = time.time()
    
    try:
        data = request.get_json()
        response_data, status_code = process_chat_request(data, start_time=start_time)
        return jsonify(response_data), status_code
    
    except Exception as e:
        error_msg = f"聊天处理异常: {str(e)}"
        logger.error(error_msg)
        
        # 记录错误统计
        stats_manager.record_error(
            endpoint="api_chat",
            error_message=error_msg
        )
        
        return jsonify({
            "success": False,
            "error": error_msg,
            "fallback_reply": "抱歉，系统暂时无法处理您的请求。您可以尝试重新提问或稍后再试。"
        }), 500

@app.route('/api/voice', methods=['POST'])
def api_voice():
    """
    语音处理接口
    
    请求格式: multipart/form-data
    - audio: 音频文件
    - session_id: 可选
    - latitude: 可选
    - longitude: 可选
    """
    try:
        # 检查文件上传
        if 'audio' not in request.files:
            return jsonify({
                "success": False,
                "error": "未找到音频文件"
            }), 400
        
        audio_file = request.files['audio']
        
        if audio_file.filename == '':
            return jsonify({
                "success": False,
                "error": "未选择文件"
            }), 400
        
        # 检查文件大小
        audio_file.seek(0, 2)  # 移动到文件末尾
        file_size = audio_file.tell()
        audio_file.seek(0)  # 重置文件指针
        
        if file_size > Config.MAX_AUDIO_SIZE:
            return jsonify({
                "success": False,
                "error": f"文件大小超过限制 ({Config.MAX_AUDIO_SIZE / 1024 / 1024}MB)"
            }), 400
        
        # 获取其他参数
        session_id = request.form.get('session_id')
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        
        # 这里应该集成语音识别
        # 由于时间关系，我们暂时返回一个模拟的文本
        # 实际应用中应该调用语音识别API
        
        # 模拟语音识别结果
        voice_text = "会理古城开放时间是多少？"
        
        # 使用聊天接口处理识别后的文本
        chat_data = {
            "user_input": voice_text,
            "session_id": session_id,
            "latitude": latitude,
            "longitude": longitude
        }

        response_data, status_code = process_chat_request(chat_data)
        response_data["voice_text"] = voice_text
        return jsonify(response_data), status_code
    
    except Exception as e:
        error_msg = f"语音处理异常: {str(e)}"
        logger.error(error_msg)
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500

@app.route('/api/geo_nearby', methods=['GET'])
def api_geo_nearby():
    """
    附近景点查询接口
    
    参数:
    - lat: 纬度 (默认: 会理市纬度)
    - lng: 经度 (默认: 会理市经度)
    - radius_km: 搜索半径公里数 (默认: 10)
    """
    try:
        # 获取参数
        lat = float(request.args.get('lat', Config.DEFAULT_LATITUDE))
        lng = float(request.args.get('lng', Config.DEFAULT_LONGITUDE))
        radius_km = float(request.args.get('radius_km', Config.NEARBY_RADIUS_KM))
        
        # 查询附近景点
        nearby_attractions = rag_engine.find_nearby_attractions(lat, lng, radius_km)
        
        return jsonify({
            "success": True,
            "latitude": lat,
            "longitude": lng,
            "radius_km": radius_km,
            "attractions": nearby_attractions,
            "count": len(nearby_attractions)
        })
    
    except ValueError as e:
        return jsonify({
            "success": False,
            "error": "参数格式错误"
        }), 400
    
    except Exception as e:
        error_msg = f"附近景点查询异常: {str(e)}"
        logger.error(error_msg)
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500

@app.route('/api/stats', methods=['GET'])
def api_stats():
    """
    统计信息接口
    
    参数:
    - days: 统计天数 (默认: 7)
    """
    try:
        days = int(request.args.get('days', 7))
        
        stats = stats_manager.get_stats(days)
        
        return jsonify({
            "success": True,
            "stats": stats,
            "cache_stats": cache_manager.get_stats(),
            "knowledge_base_stats": rag_engine.get_knowledge_base_stats(),
            "feedback_data": stats_manager.feedback_data[-100:],
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        error_msg = f"获取统计信息异常: {str(e)}"
        logger.error(error_msg)
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500

@app.route('/api/feedback', methods=['POST'])
def api_feedback():
    """
    反馈API接口
    
    请求格式:
    {
        "session_id": "session-id",
        "message_id": "message-id",
        "feedback": "like/dislike"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                "success": False,
                "error": "请求数据不能为空"
            }), 400
        
        session_id = data.get('session_id')
        message_id = data.get('message_id')
        feedback = data.get('feedback')
        
        if not all([session_id, message_id, feedback]):
            return jsonify({
                "success": False,
                "error": "缺少必要参数"
            }), 400
        
        if feedback not in ['like', 'dislike']:
            return jsonify({
                "success": False,
                "error": "feedback必须是'like'或'dislike'"
            }), 400
        
        # 记录反馈
        stats_manager.record_feedback(session_id, message_id, feedback)
        
        return jsonify({
            "success": True,
            "message": "反馈已记录",
            "feedback": feedback
        })
        
    except Exception as e:
        error_msg = f"记录反馈异常: {str(e)}"
        logger.error(error_msg)
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500

@app.route('/api/survey', methods=['POST'])
def api_survey():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "请求数据不能为空"}), 400

        session_id = data.get('session_id', 'anonymous')
        rating = data.get('rating')
        comment = data.get('comment', '')

        if rating is None or not (1 <= int(rating) <= 5):
            return jsonify({"success": False, "error": "rating必须是1-5的整数"}), 400

        stats_manager.log_survey(session_id, int(rating), comment)

        return jsonify({
            "success": True,
            "message": "感谢您的反馈！",
            "rating": rating
        })
    except Exception as e:
        logger.error(f"满意度调研异常: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/admin/upload', methods=['POST'])
def api_admin_upload():
    """
    管理员上传文档接口
    """
    try:
        # 验证管理员权限
        admin_user = request.headers.get('X-Admin-User', '')
        admin_pwd = request.headers.get('X-Admin-Password', '')
        if not admin_manager.verify(admin_user, admin_pwd):
            return jsonify({
                "success": False,
                "error": "权限不足"
            }), 403
        
        # 检查文件上传
        if 'files' not in request.files:
            return jsonify({
                "success": False,
                "error": "未找到文件"
            }), 400
        
        files = request.files.getlist('files')
        
        if not files:
            return jsonify({
                "success": False,
                "error": "未选择文件"
            }), 400
        
        # 保存文件
        saved_files = []
        for file in files:
            if file.filename == '':
                continue
            
            # 生成安全文件名
            safe_filename = hashlib.md5(f"{file.filename}{time.time()}".encode()).hexdigest()[:8]
            file_extension = os.path.splitext(file.filename)[1]
            new_filename = f"{safe_filename}{file_extension}"
            
            # 保存到知识库目录
            save_path = os.path.join(Config.KNOWLEDGE_BASE_DIR, 'raw_data', new_filename)
            file.save(save_path)
            
            saved_files.append({
                "original_name": file.filename,
                "saved_name": new_filename,
                "size": os.path.getsize(save_path)
            })
        
        return jsonify({
            "success": True,
            "message": f"成功上传 {len(saved_files)} 个文件",
            "files": saved_files
        })
        
    except Exception as e:
        error_msg = f"文件上传异常: {str(e)}"
        logger.error(error_msg)
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500

@app.route('/api/admin/rebuild', methods=['POST'])
def api_admin_rebuild():
    """
    管理员重建知识库接口
    """
    try:
        # 验证管理员权限
        admin_user = request.headers.get('X-Admin-User', '')
        admin_pwd = request.headers.get('X-Admin-Password', '')
        if not admin_manager.verify(admin_user, admin_pwd):
            return jsonify({
                "success": False,
                "error": "权限不足"
            }), 403
        
        data = request.get_json() or {}
        keep_original = data.get('keep_original', True)
        clear_cache = data.get('clear_cache', True)
        
        # 重建知识库
        result = rag_engine.rebuild_knowledge_base(keep_original, clear_cache)
        
        if clear_cache:
            cache_manager.clear()
        
        return jsonify({
            "success": True,
            "message": "知识库重建完成",
            "result": result
        })
        
    except Exception as e:
        error_msg = f"重建知识库异常: {str(e)}"
        logger.error(error_msg)
        
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500

# ========== 景点图片搜索 ==========

SCENIC_KEYWORDS = [
    "景点", "景区", "公园", "广场", "博物馆", "寺庙", "古镇", "古城",
    "山", "湖", "河", "海", "瀑布", "温泉", "遗址", "纪念馆",
    "塔", "桥", "楼", "阁", "院", "宫", "殿", "亭", "台",
    "会理", "鹿厂", "龙肘", "金江", "岔河", "六华", "黎溪",
    "通安", "新发", "树堡", "绿水", "中厂", "内东", "益门",
    "关河", "木厂", "新安", "鱼鲊", "海潮", "江普", "竹箐",
    "矮郎", "仓田", "下村", "白鸡", "法坪", "黄柏", "槽元"
]

def extract_scenic_name(text: str) -> Optional[str]:
    if not text:
        return None
    patterns = [
        r'(?:去|到|玩|看|参观|游览|介绍|了解|推荐|说说|聊聊|问问|查询|搜索|找)\s*([\u4e00-\u9fa5]{2,10})(?:景点|景区|公园|广场|博物馆|寺庙|古镇|古城)?',
        r'([\u4e00-\u9fa5]{2,6})(?:景点|景区|公园|广场|博物馆|寺庙|古镇|古城|山|湖|河|瀑布|温泉|遗址|纪念馆)',
        r'([\u4e00-\u9fa5]{2,6})(?:怎么样|有什么|好玩|好看|值得|漂亮|美丽)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            name = match.group(1).strip()
            if len(name) >= 2 and not re.match(r'^[怎么什么哪为什么如何是否]', name):
                return name
    for keyword in SCENIC_KEYWORDS:
        if keyword in text and len(keyword) >= 2:
            idx = text.find(keyword)
            start = max(0, idx - 4)
            end = min(len(text), idx + len(keyword) + 4)
            segment = text[start:end]
            match = re.search(r'([\u4e00-\u9fa5]{2,10})', segment)
            if match:
                return match.group(1)
    return None


@app.route('/api/admin/scenic_images', methods=['GET'])
def api_admin_get_images():
    admin_user = request.headers.get('X-Admin-User', '')
    admin_pwd = request.headers.get('X-Admin-Password', '')
    if not admin_manager.verify(admin_user, admin_pwd):
        return jsonify({"success": False, "error": "权限不足"}), 403
    keyword = request.args.get("keyword", "").strip()
    if keyword:
        images = scenic_manager.search_images(keyword)
    else:
        images = scenic_manager.get_all_images()
    return jsonify({"success": True, "images": images, "total": len(images)})


@app.route('/api/admin/scenic_images', methods=['POST'])
def api_admin_add_image():
    admin_user = request.headers.get('X-Admin-User', '')
    admin_pwd = request.headers.get('X-Admin-Password', '')
    if not admin_manager.verify(admin_user, admin_pwd):
        return jsonify({"success": False, "error": "权限不足"}), 403

    content_type = request.content_type or ""
    if "application/json" in content_type:
        data = request.get_json() or {}
        place_name = data.get("place_name", "").strip()
        description = data.get("description", "").strip()
        image_url = data.get("image_url", "").strip()
    else:
        place_name = request.form.get("place_name", "").strip()
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()

    if not place_name:
        return jsonify({"success": False, "error": "请填写景区名称"}), 400
    if image_url:
        result = scenic_manager.add_image_url(place_name, description, image_url)
    elif 'file' in request.files:
        file = request.files['file']
        if not file or file.filename == '':
            return jsonify({"success": False, "error": "请选择图片文件"}), 400
        allowed_ext = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in allowed_ext:
            return jsonify({"success": False, "error": "仅支持 jpg/png/gif/webp 格式"}), 400
        result = scenic_manager.add_image(place_name, description, file)
    else:
        return jsonify({"success": False, "error": "请上传图片文件或提供图片链接"}), 400
    if result["success"]:
        return jsonify(result)
    return jsonify(result), 400


@app.route('/api/admin/scenic_images/<image_id>', methods=['DELETE'])
def api_admin_delete_image(image_id):
    admin_user = request.headers.get('X-Admin-User', '')
    admin_pwd = request.headers.get('X-Admin-Password', '')
    if not admin_manager.verify(admin_user, admin_pwd):
        return jsonify({"success": False, "error": "权限不足"}), 403
    result = scenic_manager.delete_image(image_id)
    if result["success"]:
        return jsonify(result)
    return jsonify(result), 404


@app.route('/api/scenic/local/<filename>')
def api_serve_local_image(filename):
    image_path = scenic_manager.get_image_path(filename)
    if not image_path:
        return jsonify({"success": False, "error": "图片不存在"}), 404
    return send_from_directory(
        str(scenic_manager.images_dir),
        filename,
        mimetype=mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    )


def search_scenic_image(place_name: str, count: int = 6) -> Optional[Dict]:
    try:
        query = urllib.parse.quote(f"{place_name} 景点 风景 旅游")
        url = f"https://www.bing.com/images/search?q={query}&qft=+filterui:photo-photo&form=IRFLTR"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9"
        }
        resp = http_requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return None
        murls = re.findall(r'murl&quot;:&quot;(https?://[^&]+)&quot;', resp.text)
        if not murls:
            return None
        images = []
        for u in murls[:count]:
            clean_url = u.replace("&amp;", "&")
            images.append({
                "url": clean_url,
                "source": "Bing",
                "place_name": place_name
            })
        return {"image": images[0], "images": images}
    except Exception as e:
        logger.warning(f"图片搜索失败 [{place_name}]: {e}")
        return None

@app.route('/api/scenic_image', methods=['GET'])
def api_scenic_image():
    place_name = request.args.get("place", "").strip()
    if not place_name:
        return jsonify({"success": False, "error": "缺少景点名称"}), 400

    local_images = scenic_manager.search_images(place_name)
    if local_images:
        local_urls = [{"url": img["url"], "place_name": img["place_name"], "source": "本地图库"} for img in local_images]
        cache_key = f"scenic_img:{hashlib.md5(place_name.encode()).hexdigest()}"
        cached_bing = cache_manager.get(cache_key)
        bing_urls = []
        if cached_bing and cached_bing.get("images"):
            bing_urls = cached_bing["images"][:3]
        all_images = local_urls + bing_urls
        return jsonify({"success": True, "image": all_images[0] if all_images else None, "images": all_images}), 200

    cache_key = f"scenic_img:{hashlib.md5(place_name.encode()).hexdigest()}"
    cached = cache_manager.get(cache_key)
    if cached:
        return jsonify({"success": True, "image": cached.get("image"), "images": cached.get("images", []), "from_cache": True}), 200
    result = search_scenic_image(place_name)
    if result:
        cache_manager.set(cache_key, result, ttl=86400)
        return jsonify({"success": True, "image": result.get("image"), "images": result.get("images", [])}), 200
    return jsonify({"success": False, "error": "未找到相关图片"}), 404

# ========== 前端静态文件服务 ==========

FRONTEND_DIR = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'frontend'))

@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/accounts.html')
def serve_accounts():
    return send_from_directory(FRONTEND_DIR, 'accounts.html')

@app.route('/admin.html')
def serve_admin():
    return send_from_directory(FRONTEND_DIR, 'admin.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(FRONTEND_DIR, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

@app.route('/<path:filename>')
def serve_frontend_file(filename):
    if filename.startswith('api/'):
        return jsonify({"success": False, "error": "请求的资源不存在"}), 404
    filepath = os.path.join(FRONTEND_DIR, filename)
    if os.path.isfile(filepath):
        return send_from_directory(FRONTEND_DIR, filename)
    return send_from_directory(FRONTEND_DIR, 'index.html')

# ========== 错误处理 ==========

@app.errorhandler(404)
def not_found(error):
    """404错误处理"""
    return jsonify({
        "success": False,
        "error": "请求的资源不存在"
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    """405错误处理"""
    return jsonify({
        "success": False,
        "error": "请求方法不允许"
    }), 405

@app.errorhandler(500)
def internal_error(error):
    """500错误处理"""
    logger.error(f"服务器内部错误: {str(error)}")
    return jsonify({
        "success": False,
        "error": "服务器内部错误",
        "message": "系统暂时无法处理您的请求，请稍后再试"
    }), 500

@app.errorhandler(501)
def not_implemented(error):
    """501错误处理"""
    logger.error(f"请求未实现: {str(error)}")
    return jsonify({
        "success": False,
        "error": "请求方法未实现",
        "message": "该功能暂未实现，请检查请求方式"
    }), 501

@app.errorhandler(Exception)
def handle_exception(error):
    """全局异常处理"""
    logger.error(f"未捕获异常: {str(error)}", exc_info=True)
    return jsonify({
        "success": False,
        "error": "服务器处理请求时发生错误",
        "message": str(error)
    }), 500

# ========== 应用启动 ==========

if __name__ == '__main__':
    # 打印启动信息
    print("=" * 60)
    print("会理市AI数字人导游系统 - 后端服务")
    print(f"版本: 1.0.0")
    print(f"作者: 资深全栈架构师")
    print(f"日期: 2026年4月20日")
    print("=" * 60)
    
    # 检查配置
    print(f"配置检查:")
    print(f"  - 调试模式: {Config.DEBUG}")
    print(f"  - 服务器地址: {Config.HOST}:{Config.PORT}")
    print(f"  - 知识库路径: {Config.KNOWLEDGE_BASE_DIR}")
    print(f"  - 向量数据库: {Config.CHROMA_DB_PATH}")
    
    # 检查知识库
    if rag_engine.has_knowledge_base():
        kb_stats = rag_engine.get_knowledge_base_stats()
        print(f"知识库状态: 正常 (文档数: {kb_stats.get('document_count', 0)})")
    else:
        print("警告: 知识库未初始化，请运行 build_kb.py 构建知识库")
    
    # 检查缓存
    if cache_manager.is_available():
        cache_type = "fakeredis" if cache_manager.use_fake_redis else "redis"
        print(f"缓存状态: 正常 ({cache_type})")
    else:
        print("警告: 缓存不可用，使用内存缓存")
    
    print("=" * 60)
    print(f"服务启动中...")
    print(f"访问地址: http://{Config.HOST}:{Config.PORT}")
    print(f"API文档: http://{Config.HOST}:{Config.PORT}/")
    print("=" * 60)
    
    # 启动Flask应用
    app.run(
        host=Config.HOST,
        port=Config.PORT,
        debug=Config.DEBUG,
        threaded=True
    )
