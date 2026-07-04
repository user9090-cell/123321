
import os

# 必须在最前面设置 HF 环境变量
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
import tempfile
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import requests as http_requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

try:
    import speech_recognition as sr
    SPEECH_AVAILABLE = True
except ImportError:
    SPEECH_AVAILABLE = False

from config import Config
from cache import CacheManager
from rag_engine import RAGEngine
from stats import StatsManager
from user_manager import UserManager
from admin_manager import AdminManager
from scenic_manager import ScenicImageManager

# ---- 应用初始化 ----

mimetypes.add_type('application/octet-stream', '.moc')
mimetypes.add_type('application/octet-stream', '.mtn')
mimetypes.add_type('application/json', '.exp3.json')

app = Flask(__name__)
app.config.from_object(Config)

if Config.ENABLE_CORS:
    CORS(app, resources={
        r"/api/*": {
            "origins": "*",
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "X-Session-ID", "X-Admin-User", "X-Admin-Password", "X-Phone"]
        }
    })

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

cache_manager = CacheManager()
rag_engine = RAGEngine()
stats_manager = StatsManager()
user_manager = UserManager()
admin_manager = AdminManager()
scenic_manager = ScenicImageManager()

sessions: Dict[str, dict] = {}


# ---- 会话 & 工具函数 ----

def generate_session_id():
    return hashlib.md5(f"{time.time()}{os.urandom(16)}".encode()).hexdigest()


def get_session(sid):
    if sid not in sessions:
        sessions[sid] = {
            "id": sid,
            "created_at": datetime.now(),
            "last_active": datetime.now(),
            "messages": [],
            "user_location": None,
            "preferences": {},
        }
    else:
        sessions[sid]["last_active"] = datetime.now()
        s = sessions[sid]
        s.setdefault("messages", [])
        s.setdefault("user_location", None)
        s.setdefault("preferences", {})
    return sessions[sid]


def check_fields(data, required):
    """检查必填字段，有问题返回 error dict，没问题返回 None"""
    if not data:
        return {"success": False, "error": "请求数据不能为空"}
    missing = [f for f in required if f not in data]
    if missing:
        return {"success": False, "error": f"缺少必要字段: {', '.join(missing)}"}
    return None


def _error(msg, code=400):
    return jsonify({"success": False, "error": msg}), code


def _ok(data=None, **kw):
    resp = {"success": True}
    if data:
        resp.update(data)
    resp.update(kw)
    return jsonify(resp), 200


# ---- 核心聊天逻辑（文本 & 语音共用）----

def process_chat_request(data, start_time=None):
    t0 = start_time or time.time()

    err = check_fields(data, ["user_input"])
    if err:
        return err, 400

    text = str(data["user_input"]).strip()
    sid = data.get("session_id")
    lat = data.get("latitude")
    lng = data.get("longitude")

    if not text:
        return {"success": False, "error": "用户输入不能为空"}, 400
    if not sid:
        sid = generate_session_id()

    session = get_session(sid)
    if lat is not None and lng is not None:
        session["user_location"] = {"latitude": float(lat), "longitude": float(lng)}

    # 查缓存
    ck = f"chat:{hashlib.md5(text.encode()).hexdigest()}"
    hit = cache_manager.get(ck)
    if hit:
        logger.info(f"缓存命中: {text[:50]}...")
        session["messages"].append({"role": "user", "content": text, "timestamp": datetime.now()})
        session["messages"].append({"role": "assistant", "content": hit["reply"], "timestamp": datetime.now(), "from_cache": True})
        stats_manager.record_request(sid, text, hit["reply"], True, (time.time() - t0) * 1000)
        return {
            "success": True, "reply": hit["reply"], "session_id": sid,
            "source": hit.get("source", []), "suggestions": hit.get("suggestions", []),
            "from_cache": True, "latency_ms": round((time.time() - t0) * 1000, 2),
        }, 200

    logger.info(f"处理请求: {text[:50]}...")
    ctx = {
        "user_input": text, "session_id": sid,
        "user_location": session.get("user_location"),
        "conversation_history": session["messages"][-5:],
    }
    result = rag_engine.generate_response(ctx)

    # 写缓存
    cache_manager.set(ck, {
        "reply": result["reply"],
        "source": result.get("source", []),
        "suggestions": result.get("suggestions", []),
    }, ttl=Config.CACHE_TTL)

    session["messages"].append({"role": "user", "content": text, "timestamp": datetime.now()})
    session["messages"].append({
        "role": "assistant", "content": result["reply"], "timestamp": datetime.now(),
        "source": result.get("source", []), "model_used": result.get("model_used"),
    })

    stats_manager.record_request(sid, text, result["reply"], False, (time.time() - t0) * 1000, result.get("model_used"))

    return {
        "success": True, "reply": result["reply"], "session_id": sid,
        "source": result.get("source", []), "suggestions": result.get("suggestions", []),
        "latency_ms": round((time.time() - t0) * 1000, 2),
        "model_used": result.get("model_used", "unknown"),
    }, 200


# ========== 健康检查 ==========

@app.route('/api/health', methods=['GET'])
def api_health():
    try:
        comps = {
            "flask": True,
            "cache": cache_manager.is_available(),
            "rag_engine": rag_engine.is_available(),
            "knowledge_base": rag_engine.has_knowledge_base(),
        }
        critical = {"flask": comps["flask"], "rag_engine": comps["rag_engine"]}
        healthy = all(critical.values())
        degraded = healthy and not all(comps.values())
        return jsonify({
            "success": True, "healthy": healthy, "degraded": degraded,
            "components": comps, "timestamp": datetime.now().isoformat(),
            "uptime": stats_manager.get_uptime(), "version": "1.0.0",
        })
    except Exception as e:
        logger.error(f"health check 失败: {e}")
        return jsonify({"success": False, "healthy": False, "error": str(e)}), 500


# ========== 用户相关 ==========

@app.route('/api/register', methods=['POST'])
def api_register():
    try:
        d = request.get_json()
        if not d:
            return _error("请求数据不能为空")
        r = user_manager.register(d.get("phone", ""), d.get("password", ""))
        return (jsonify(r), 200) if r["success"] else (jsonify(r), 400)
    except Exception as e:
        logger.error(f"注册失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/login', methods=['POST'])
def api_login():
    try:
        d = request.get_json()
        if not d:
            return _error("请求数据不能为空")
        r = user_manager.login(d.get("phone", ""), d.get("password", ""))
        if r["success"]:
            sessions[r["session_id"]] = {"phone": r["phone"], "created_at": datetime.now().isoformat()}
            return jsonify(r)
        return jsonify(r), 401
    except Exception as e:
        logger.error(f"登录失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/logout', methods=['POST'])
def api_logout():
    try:
        d = request.get_json() or {}
        r = user_manager.logout(d.get("phone", ""))
        return (jsonify(r), 200) if r["success"] else (jsonify(r), 400)
    except Exception as e:
        logger.error(f"登出失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/user/info', methods=['GET'])
def api_user_info():
    phone = request.args.get("phone", "").strip()
    if not phone:
        return _error("缺少手机号")
    u = user_manager.get_user(phone)
    if not u:
        return _error("用户不存在", 404)
    return jsonify({"success": True, "user": u})


@app.route('/api/user/stats', methods=['GET'])
def api_user_stats():
    try:
        s = user_manager.get_stats()
        users = user_manager.get_all_users()
        return jsonify({"success": True, "stats": s, "users": users})
    except Exception as e:
        logger.error(f"用户统计失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/user/change_password', methods=['POST'])
def api_change_password():
    try:
        d = request.get_json()
        if not d:
            return _error("请求数据不能为空")
        r = user_manager.change_password(d.get("phone", ""), d.get("old_password", ""), d.get("new_password", ""))
        return (jsonify(r), 200) if r["success"] else (jsonify(r), 400)
    except Exception as e:
        logger.error(f"改密失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/user/delete', methods=['POST'])
def api_delete_account():
    try:
        d = request.get_json()
        if not d:
            return _error("请求数据不能为空")
        r = user_manager.delete_account(d.get("phone", ""), d.get("password", ""))
        return (jsonify(r), 200) if r["success"] else (jsonify(r), 400)
    except Exception as e:
        logger.error(f"注销失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 头像 ==========

@app.route('/api/avatar/upload', methods=['POST'])
def api_avatar_upload():
    try:
        phone = (request.form or {}).get("phone", "").strip()
        if not phone:
            return _error("缺少手机号")
        if 'avatar' not in request.files:
            return _error("未找到头像文件")
        f = request.files['avatar']
        if f.filename == '':
            return _error("未选择文件")
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in {'.png', '.jpg', '.jpeg', '.gif', '.webp'}:
            return _error("仅支持 PNG/JPG/GIF/WEBP 格式")
        safe = hashlib.md5(f"{phone}{time.time()}".encode()).hexdigest()[:12]
        fname = f"{safe}{ext}"
        f.save(os.path.join(str(user_manager.avatars_dir), fname))
        r = user_manager.update_avatar(phone, fname)
        return (jsonify(r), 200) if r["success"] else (jsonify(r), 400)
    except Exception as e:
        logger.error(f"头像上传失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/avatar/<phone>', methods=['GET'])
def api_avatar_get(phone):
    try:
        p = user_manager.get_avatar_path(phone)
        if p:
            return send_from_directory(os.path.dirname(p), os.path.basename(p))
    except Exception:
        pass
    return '', 204


# ========== 聊天 & 语音 ==========

@app.route('/api/chat', methods=['POST'])
def api_chat():
    t0 = time.time()
    try:
        data = request.get_json()
        resp, code = process_chat_request(data, start_time=t0)
        return jsonify(resp), code
    except Exception as e:
        logger.error(f"聊天异常: {e}\n{traceback.format_exc()}")
        stats_manager.record_error("api_chat", str(e))
        return jsonify({
            "success": False, "error": str(e),
            "fallback_reply": "抱歉，系统暂时无法处理您的请求。您可以尝试重新提问或稍后再试。",
        }), 500


@app.route('/api/voice', methods=['POST'])
def api_voice():
    try:
        if 'audio' not in request.files:
            return _error("未找到音频文件")
        af = request.files['audio']
        if af.filename == '':
            return _error("未选择文件")

        # 文件大小检查
        af.seek(0, 2)
        size = af.tell()
        af.seek(0)
        if size > Config.MAX_AUDIO_SIZE:
            return _error(f"文件超过 {Config.MAX_AUDIO_SIZE // 1024 // 1024}MB 限制")

        sid = request.form.get('session_id')
        lat = request.form.get('latitude')
        lng = request.form.get('longitude')

        # 写临时文件
        suffix = os.path.splitext(af.filename)[1] or '.wav'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            af.save(tmp.name)
            tmp_path = tmp.name

        try:
            if not SPEECH_AVAILABLE:
                return _error("语音识别服务不可用，请使用文字输入", 503)
            rec = sr.Recognizer()
            with sr.AudioFile(tmp_path) as src:
                audio_data = rec.record(src)
            voice_text = rec.recognize_google(audio_data, language='zh-CN')
        except sr.UnknownValueError:
            return _error("未能识别出文字，请重试", 422)
        except sr.RequestError as e:
            return _error(f"语音识别服务连接失败: {e}", 503)
        except Exception as e:
            logger.error(f"语音识别异常: {e}")
            return _error(f"语音识别处理异常: {e}", 500)
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        chat_data = {"user_input": voice_text, "session_id": sid, "latitude": lat, "longitude": lng}
        resp, code = process_chat_request(chat_data)
        resp["voice_text"] = voice_text
        return jsonify(resp), code
    except Exception as e:
        logger.error(f"语音接口异常: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 附近景点 ==========

@app.route('/api/geo_nearby', methods=['GET'])
def api_geo_nearby():
    try:
        lat = float(request.args.get('lat', Config.DEFAULT_LATITUDE))
        lng = float(request.args.get('lng', Config.DEFAULT_LONGITUDE))
        r = float(request.args.get('radius_km', Config.NEARBY_RADIUS_KM))
        spots = rag_engine.find_nearby_attractions(lat, lng, r)
        return jsonify({"success": True, "latitude": lat, "longitude": lng, "radius_km": r, "attractions": spots, "count": len(spots)})
    except ValueError:
        return _error("参数格式错误")
    except Exception as e:
        logger.error(f"附近景点查询失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 统计 & 反馈 ==========

@app.route('/api/stats', methods=['GET'])
def api_stats():
    try:
        days = int(request.args.get('days', 7))
        s = stats_manager.get_stats(days)
        return jsonify({
            "success": True, "stats": s,
            "cache_stats": cache_manager.get_stats(),
            "knowledge_base_stats": rag_engine.get_knowledge_base_stats(),
            "feedback_data": stats_manager.feedback_data[-100:],
            "timestamp": datetime.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"统计接口异常: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/feedback', methods=['POST'])
def api_feedback():
    try:
        d = request.get_json()
        if not d:
            return _error("请求数据不能为空")
        sid = d.get('session_id')
        mid = d.get('message_id')
        fb = d.get('feedback')
        if not all([sid, mid, fb]):
            return _error("缺少必要参数")
        if fb not in ('like', 'dislike'):
            return _error("feedback 必须是 like 或 dislike")
        stats_manager.record_feedback(sid, mid, fb)
        return jsonify({"success": True, "message": "反馈已记录", "feedback": fb})
    except Exception as e:
        logger.error(f"反馈记录失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/survey', methods=['POST'])
def api_survey():
    try:
        d = request.get_json()
        if not d:
            return _error("请求数据不能为空")
        sid = d.get('session_id', 'anonymous')
        rating = d.get('rating')
        comment = d.get('comment', '')
        if rating is None or not (1 <= int(rating) <= 5):
            return _error("rating 必须是 1-5 的整数")
        stats_manager.log_survey(sid, int(rating), comment)
        return jsonify({"success": True, "message": "感谢您的反馈！", "rating": rating})
    except Exception as e:
        logger.error(f"满意度调研失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 管理后台 ==========

def _admin_check():
    u = request.headers.get('X-Admin-User', '')
    p = request.headers.get('X-Admin-Password', '')
    return admin_manager.verify(u, p)


@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    try:
        d = request.get_json()
        if not d:
            return _error("请求数据不能为空")
        r = admin_manager.login(d.get("username", ""), d.get("password", ""))
        return (jsonify(r), 200) if r["success"] else (jsonify(r), 401)
    except Exception as e:
        logger.error(f"管理员登录失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admin/change_password', methods=['POST'])
def api_admin_change_password():
    try:
        d = request.get_json()
        if not d:
            return _error("请求数据不能为空")
        r = admin_manager.change_password(d.get("username", ""), d.get("old_password", ""), d.get("new_password", ""))
        return (jsonify(r), 200) if r["success"] else (jsonify(r), 400)
    except Exception as e:
        logger.error(f"管理员改密失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admin/info', methods=['GET'])
def api_admin_info():
    u = request.args.get("username", "").strip()
    if not u:
        return _error("缺少账号")
    a = admin_manager.get_admin(u)
    if not a:
        return _error("账号不存在", 404)
    return jsonify({"success": True, "admin": a})


@app.route('/api/admin/upload', methods=['POST'])
def api_admin_upload():
    try:
        if not _admin_check():
            return _error("权限不足", 403)
        if 'files' not in request.files:
            return _error("未找到文件")
        files = request.files.getlist('files')
        if not files:
            return _error("未选择文件")

        saved = []
        for f in files:
            if f.filename == '':
                continue
            safe = hashlib.md5(f"{f.filename}{time.time()}".encode()).hexdigest()[:8]
            ext = os.path.splitext(f.filename)[1]
            new_name = f"{safe}{ext}"
            dest = os.path.join(Config.KNOWLEDGE_BASE_DIR, 'raw_data', new_name)
            f.save(dest)
            saved.append({"original_name": f.filename, "saved_name": new_name, "size": os.path.getsize(dest)})

        return jsonify({"success": True, "message": f"成功上传 {len(saved)} 个文件", "files": saved})
    except Exception as e:
        logger.error(f"文件上传失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/admin/rebuild', methods=['POST'])
def api_admin_rebuild():
    try:
        if not _admin_check():
            return _error("权限不足", 403)
        d = request.get_json() or {}
        keep = d.get('keep_original', True)
        clear = d.get('clear_cache', True)
        r = rag_engine.rebuild_knowledge_base(keep, clear)
        if clear:
            cache_manager.clear()
        return jsonify({"success": True, "message": "知识库重建完成", "result": r})
    except Exception as e:
        logger.error(f"重建知识库失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# ========== 景点图片 ==========

SCENIC_KEYWORDS = [
    "景点", "景区", "公园", "广场", "博物馆", "寺庙", "古镇", "古城",
    "山", "湖", "河", "海", "瀑布", "温泉", "遗址", "纪念馆",
    "塔", "桥", "楼", "阁", "院", "宫", "殿", "亭", "台",
    "会理", "鹿厂", "龙肘", "金江", "岔河", "六华", "黎溪",
    "通安", "新发", "树堡", "绿水", "中厂", "内东", "益门",
    "关河", "木厂", "新安", "鱼鲊", "海潮", "江普", "竹箐",
    "矮郎", "仓田", "下村", "白鸡", "法坪", "黄柏", "槽元",
]


def extract_scenic_name(text):
    """从用户输入中提取景点名"""
    if not text:
        return None
    patterns = [
        r'(?:去|到|玩|看|参观|游览|介绍|了解|推荐|说说|聊聊|问问|查询|搜索|找)\s*([一-龥]{2,10})(?:景点|景区|公园|广场|博物馆|寺庙|古镇|古城)?',
        r'([一-龥]{2,6})(?:景点|景区|公园|广场|博物馆|寺庙|古镇|古城|山|湖|河|瀑布|温泉|遗址|纪念馆)',
        r'([一-龥]{2,6})(?:怎么样|有什么|好玩|好看|值得|漂亮|美丽)',
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            name = m.group(1).strip()
            if len(name) >= 2 and not re.match(r'^[怎么什么哪为什么如何是否]', name):
                return name
    # 兜底：关键词匹配
    for kw in SCENIC_KEYWORDS:
        if kw in text and len(kw) >= 2:
            idx = text.find(kw)
            seg = text[max(0, idx-4):min(len(text), idx+len(kw)+4)]
            m = re.search(r'([一-龥]{2,10})', seg)
            if m:
                return m.group(1)
    return None


@app.route('/api/admin/scenic_images', methods=['GET'])
def api_admin_get_images():
    if not _admin_check():
        return _error("权限不足", 403)
    kw = request.args.get("keyword", "").strip()
    imgs = scenic_manager.search_images(kw) if kw else scenic_manager.get_all_images()
    return jsonify({"success": True, "images": imgs, "total": len(imgs)})


@app.route('/api/admin/scenic_images', methods=['POST'])
def api_admin_add_image():
    if not _admin_check():
        return _error("权限不足", 403)

    ct = request.content_type or ""
    if "application/json" in ct:
        d = request.get_json() or {}
        place = d.get("place_name", "").strip()
        desc = d.get("description", "").strip()
        url = d.get("image_url", "").strip()
    else:
        place = request.form.get("place_name", "").strip()
        desc = request.form.get("description", "").strip()
        url = request.form.get("image_url", "").strip()

    if not place:
        return _error("请填写景区名称")

    if url:
        r = scenic_manager.add_image_url(place, desc, url)
    elif 'file' in request.files:
        f = request.files['file']
        if not f or f.filename == '':
            return _error("请选择图片文件")
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.gif', '.webp'}:
            return _error("仅支持 jpg/png/gif/webp 格式")
        r = scenic_manager.add_image(place, desc, f)
    else:
        return _error("请上传图片文件或提供图片链接")

    return (jsonify(r), 200) if r["success"] else (jsonify(r), 400)


@app.route('/api/admin/scenic_images/<image_id>', methods=['DELETE'])
def api_admin_delete_image(image_id):
    if not _admin_check():
        return _error("权限不足", 403)
    r = scenic_manager.delete_image(image_id)
    return (jsonify(r), 200) if r["success"] else (jsonify(r), 404)


@app.route('/api/scenic/local/<filename>')
def api_serve_local_image(filename):
    p = scenic_manager.get_image_path(filename)
    if not p:
        return _error("图片不存在", 404)
    mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
    return send_from_directory(str(scenic_manager.images_dir), filename, mimetype=mime)


# ---- 图片搜索（Bing 兜底）----

def search_scenic_image(place_name, count=6):
    try:
        q = urllib.parse.quote(f"{place_name} 景点 风景 旅游")
        url = f"https://www.bing.com/images/search?q={q}&qft=+filterui:photo-photo&form=IRFLTR"
        hdrs = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        r = http_requests.get(url, headers=hdrs, timeout=10)
        if r.status_code != 200:
            return None
        urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+)&quot;', r.text)
        if not urls:
            return None
        imgs = [{"url": u.replace("&amp;", "&"), "source": "Bing", "place_name": place_name} for u in urls[:count]]
        return {"image": imgs[0], "images": imgs}
    except Exception as e:
        logger.warning(f"Bing 图片搜索失败 [{place_name}]: {e}")
        return None


@app.route('/api/scenic_image', methods=['GET'])
def api_scenic_image():
    place = request.args.get("place", "").strip()
    if not place:
        return _error("缺少景点名称")

    # 先查本地
    local = scenic_manager.search_images(place)
    ck = f"scenic_img:{hashlib.md5(place.encode()).hexdigest()}"

    if local:
        local_urls = [{"url": i["url"], "place_name": i["place_name"], "source": "本地图库"} for i in local]
        bing_hit = cache_manager.get(ck)
        bing_urls = bing_hit["images"][:3] if bing_hit and bing_hit.get("images") else []
        all_imgs = local_urls + bing_urls
        return jsonify({"success": True, "image": all_imgs[0] if all_imgs else None, "images": all_imgs})

    cached = cache_manager.get(ck)
    if cached:
        return jsonify({"success": True, "image": cached.get("image"), "images": cached.get("images", []), "from_cache": True})

    result = search_scenic_image(place)
    if result:
        cache_manager.set(ck, result, ttl=86400)
        return jsonify({"success": True, "image": result.get("image"), "images": result.get("images", [])})
    return _error("未找到相关图片", 404)


# ========== 前端静态文件 ==========

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
        return _error("请求的资源不存在", 404)
    fp = os.path.join(FRONTEND_DIR, filename)
    if os.path.isfile(fp):
        return send_from_directory(FRONTEND_DIR, filename)
    return send_from_directory(FRONTEND_DIR, 'index.html')


# ========== 错误处理 ==========

@app.errorhandler(404)
def not_found(e):
    return jsonify({"success": False, "error": "请求的资源不存在"}), 404


@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({"success": False, "error": "请求方法不允许"}), 405


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"500: {e}")
    return jsonify({"success": False, "error": "服务器内部错误", "message": "请稍后再试"}), 500


@app.errorhandler(501)
def not_implemented(e):
    logger.error(f"501: {e}")
    return jsonify({"success": False, "error": "该功能暂未实现"}), 501


@app.errorhandler(Exception)
def handle_exception(e):
    logger.error(f"未捕获异常: {e}", exc_info=True)
    return jsonify({"success": False, "error": "服务器处理请求时发生错误", "message": str(e)}), 500


# ========== 启动 ==========

if __name__ == '__main__':
    print("=" * 50)
    print("会理市AI数字人导游系统 v1.0.0")
    print(f"http://{Config.HOST}:{Config.PORT}")
    print("=" * 50)

    if rag_engine.has_knowledge_base():
        kb = rag_engine.get_knowledge_base_stats()
        print(f"知识库: {kb.get('document_count', 0)} 条文档")
    else:
        print("⚠ 知识库未初始化，请先运行 build_kb.py")

    ctype = "fakeredis" if cache_manager.use_fake_redis else "redis"
    print(f"缓存: {ctype}")

    app.run(host=Config.HOST, port=Config.PORT, debug=Config.DEBUG, threaded=True)
