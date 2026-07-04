import json
import hashlib
import time
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List
import logging

logger = logging.getLogger(__name__)


class UserManager:

    def __init__(self, data_dir=None):
        if data_dir is None:
            data_dir = str(Path(__file__).parent / "logs")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.users_file = self.data_dir / "users.json"
        self.avatars_dir = self.data_dir / "avatars"
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        self.users: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.users_file.exists():
            try:
                self.users = json.loads(self.users_file.read_text(encoding="utf-8"))
                logger.info(f"加载 {len(self.users)} 个用户")
            except Exception as e:
                logger.error(f"读取用户数据失败: {e}")
                self.users = {}

    def _save(self):
        try:
            self.users_file.write_text(json.dumps(self.users, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"保存用户数据失败: {e}")

    @staticmethod
    def _hash(pwd):
        return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

    # ---- 注册 / 登录 / 注销 ----

    def register(self, phone, password):
        phone = phone.strip()
        if not phone or not password:
            return {"success": False, "error": "手机号和密码不能为空"}
        if not phone.isdigit() or len(phone) != 11:
            return {"success": False, "error": "请输入11位手机号"}
        if len(password) < 6:
            return {"success": False, "error": "密码至少6位"}
        if phone in self.users:
            return {"success": False, "error": "该手机号已注册"}

        self.users[phone] = {
            "phone": phone,
            "password": self._hash(password),
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "avatar": "",
        }
        self._save()
        logger.info(f"新用户注册: {phone}")
        return {"success": True, "message": "注册成功", "phone": phone}

    def login(self, phone, password):
        phone = phone.strip()
        if not phone or not password:
            return {"success": False, "error": "请输入手机号和密码"}
        u = self.users.get(phone)
        if not u:
            return {"success": False, "error": "账号不存在，请先注册"}
        if u["password"] != self._hash(password):
            return {"success": False, "error": "密码错误"}
        u["last_login"] = datetime.now().isoformat()
        self._save()
        logger.info(f"用户登录: {phone}")
        return {
            "success": True, "message": "登录成功", "phone": phone,
            "session_id": hashlib.md5(f"{phone}{time.time()}".encode()).hexdigest()[:16],
        }

    def logout(self, phone):
        phone = phone.strip()
        if phone not in self.users:
            return {"success": False, "error": "账号不存在"}
        logger.info(f"用户登出: {phone}")
        return {"success": True, "message": "已退出登录"}

    def change_password(self, phone, old_pwd, new_pwd):
        phone = phone.strip()
        u = self.users.get(phone)
        if not u:
            return {"success": False, "error": "账号不存在"}
        if u["password"] != self._hash(old_pwd):
            return {"success": False, "error": "原密码错误"}
        if len(new_pwd) < 6:
            return {"success": False, "error": "新密码至少6位"}
        u["password"] = self._hash(new_pwd)
        self._save()
        return {"success": True, "message": "密码修改成功"}

    def delete_account(self, phone, password):
        phone = phone.strip()
        u = self.users.get(phone)
        if not u:
            return {"success": False, "error": "账号不存在"}
        if u["password"] != self._hash(password):
            return {"success": False, "error": "密码错误"}
        if u.get("avatar"):
            old = self.avatars_dir / u["avatar"]
            if old.exists():
                try:
                    old.unlink()
                except Exception:
                    pass
        del self.users[phone]
        self._save()
        logger.info(f"用户注销: {phone}")
        return {"success": True, "message": "账号已注销"}

    # ---- 查询 ----

    def get_user(self, phone):
        u = self.users.get(phone.strip())
        if not u:
            return None
        return {"phone": u["phone"], "created_at": u.get("created_at", "--"), "last_login": u.get("last_login", "--"), "avatar": u.get("avatar", "")}

    def get_stats(self):
        n = len(self.users)
        return {"total_users": n, "active_users": n}

    def get_all_users(self):
        return [
            {"phone": p, "created_at": u.get("created_at", "--"), "last_login": u.get("last_login", "--"), "avatar": u.get("avatar", "")}
            for p, u in self.users.items()
        ]

    # ---- 头像 ----

    def update_avatar(self, phone, fname):
        phone = phone.strip()
        u = self.users.get(phone)
        if not u:
            return {"success": False, "error": "账号不存在"}
        if u.get("avatar") and u["avatar"] != fname:
            old = self.avatars_dir / u["avatar"]
            if old.exists():
                try:
                    old.unlink()
                except Exception:
                    pass
        u["avatar"] = fname
        self._save()
        logger.info(f"头像更新: {phone}")
        return {"success": True, "message": "头像更新成功", "avatar": fname}

    def get_avatar_path(self, phone):
        u = self.users.get(phone.strip())
        if not u or not u.get("avatar"):
            return None
        p = self.avatars_dir / u["avatar"]
        return str(p) if p.exists() else None
