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
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = str(Path(__file__).parent / "logs")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.users_file = self.data_dir / "users.json"
        self.avatars_dir = self.data_dir / "avatars"
        self.avatars_dir.mkdir(parents=True, exist_ok=True)
        self.users: Dict[str, dict] = {}
        self._load_users()

    def _load_users(self):
        if self.users_file.exists():
            try:
                with open(self.users_file, "r", encoding="utf-8") as f:
                    self.users = json.load(f)
                logger.info(f"Loaded {len(self.users)} users")
            except Exception as e:
                logger.error(f"Failed to load users: {e}")
                self.users = {}

    def _save_users(self):
        try:
            with open(self.users_file, "w", encoding="utf-8") as f:
                json.dump(self.users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save users: {e}")

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def register(self, phone: str, password: str) -> Dict:
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
            "password": self._hash_password(password),
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "avatar": ""
        }
        self._save_users()
        logger.info(f"User registered: {phone}")
        return {"success": True, "message": "注册成功", "phone": phone}

    def login(self, phone: str, password: str) -> Dict:
        phone = phone.strip()
        if not phone or not password:
            return {"success": False, "error": "手机号和密码不能为空"}

        user = self.users.get(phone)
        if not user:
            return {"success": False, "error": "账号不存在，请先注册"}
        if user["password"] != self._hash_password(password):
            return {"success": False, "error": "密码错误"}

        user["last_login"] = datetime.now().isoformat()
        self._save_users()
        logger.info(f"User logged in: {phone}")
        return {
            "success": True,
            "message": "登录成功",
            "phone": phone,
            "session_id": hashlib.md5(f"{phone}{time.time()}".encode()).hexdigest()[:16]
        }

    def logout(self, phone: str) -> Dict:
        phone = phone.strip()
        user = self.users.get(phone)
        if not user:
            return {"success": False, "error": "账号不存在"}
        logger.info(f"User logged out: {phone}")
        return {"success": True, "message": "已退出登录"}

    def change_password(self, phone: str, old_password: str, new_password: str) -> Dict:
        phone = phone.strip()
        user = self.users.get(phone)
        if not user:
            return {"success": False, "error": "账号不存在"}
        if user["password"] != self._hash_password(old_password):
            return {"success": False, "error": "原密码错误"}
        if len(new_password) < 6:
            return {"success": False, "error": "新密码至少6位"}
        user["password"] = self._hash_password(new_password)
        self._save_users()
        return {"success": True, "message": "密码修改成功"}

    def delete_account(self, phone: str, password: str) -> Dict:
        phone = phone.strip()
        user = self.users.get(phone)
        if not user:
            return {"success": False, "error": "账号不存在"}
        if user["password"] != self._hash_password(password):
            return {"success": False, "error": "密码错误"}
        if user.get("avatar"):
            old_path = self.avatars_dir / user["avatar"]
            if old_path.exists():
                try:
                    old_path.unlink()
                except Exception:
                    pass
        del self.users[phone]
        self._save_users()
        logger.info(f"User deleted account: {phone}")
        return {"success": True, "message": "账号已注销"}

    def get_user(self, phone: str) -> Optional[Dict]:
        user = self.users.get(phone.strip())
        if not user:
            return None
        return {
            "phone": user["phone"],
            "created_at": user.get("created_at", "--"),
            "last_login": user.get("last_login", "--"),
            "avatar": user.get("avatar", "")
        }

    def get_stats(self) -> Dict:
        total = len(self.users)
        return {
            "total_users": total,
            "active_users": total
        }

    def get_all_users(self) -> List[dict]:
        result = []
        for phone, user in self.users.items():
            result.append({
                "phone": phone,
                "created_at": user.get("created_at", "--"),
                "last_login": user.get("last_login", "--"),
                "avatar": user.get("avatar", "")
            })
        return result

    def update_avatar(self, phone: str, avatar_filename: str) -> Dict:
        phone = phone.strip()
        user = self.users.get(phone)
        if not user:
            return {"success": False, "error": "账号不存在"}
        if user.get("avatar") and user["avatar"] != avatar_filename:
            old_path = self.avatars_dir / user["avatar"]
            if old_path.exists():
                try:
                    old_path.unlink()
                except Exception:
                    pass
        user["avatar"] = avatar_filename
        self._save_users()
        logger.info(f"Avatar updated for: {phone}")
        return {"success": True, "message": "头像更新成功", "avatar": avatar_filename}

    def get_avatar_path(self, phone: str) -> Optional[str]:
        user = self.users.get(phone.strip())
        if not user or not user.get("avatar"):
            return None
        path = self.avatars_dir / user["avatar"]
        return str(path) if path.exists() else None
