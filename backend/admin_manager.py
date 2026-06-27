import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AdminManager:
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = str(Path(__file__).parent / "logs")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.admin_file = self.data_dir / "admin.json"
        self.admins: Dict[str, dict] = {}
        self._load()
        self._ensure_default()

    def _load(self):
        if self.admin_file.exists():
            try:
                with open(self.admin_file, "r", encoding="utf-8") as f:
                    self.admins = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load admin data: {e}")
                self.admins = {}

    def _save(self):
        try:
            with open(self.admin_file, "w", encoding="utf-8") as f:
                json.dump(self.admins, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save admin data: {e}")

    def _ensure_default(self):
        if "guanli001" not in self.admins:
            self.admins["guanli001"] = {
                "username": "guanli001",
                "password": self._hash_password("123456"),
                "created_at": datetime.now().isoformat(),
                "last_login": None
            }
            self._save()
            logger.info("Default admin account created: guanli001")

    @staticmethod
    def _hash_password(password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    def login(self, username: str, password: str) -> Dict:
        username = username.strip()
        password = password.strip()
        if not username or not password:
            return {"success": False, "error": "请输入账号和密码"}
        admin = self.admins.get(username)
        if not admin:
            return {"success": False, "error": "账号不存在"}
        if admin["password"] != self._hash_password(password):
            return {"success": False, "error": "密码错误"}
        admin["last_login"] = datetime.now().isoformat()
        self._save()
        return {"success": True, "message": "登录成功", "username": username}

    def change_password(self, username: str, old_password: str, new_password: str) -> Dict:
        username = username.strip()
        admin = self.admins.get(username)
        if not admin:
            return {"success": False, "error": "账号不存在"}
        if admin["password"] != self._hash_password(old_password):
            return {"success": False, "error": "原密码错误"}
        if len(new_password.strip()) < 6:
            return {"success": False, "error": "新密码至少6位"}
        admin["password"] = self._hash_password(new_password.strip())
        self._save()
        return {"success": True, "message": "密码修改成功"}

    def verify(self, username: str, password: str) -> bool:
        admin = self.admins.get(username.strip())
        if not admin:
            return False
        return admin["password"] == self._hash_password(password.strip())

    def get_admin(self, username: str) -> Optional[Dict]:
        admin = self.admins.get(username.strip())
        if not admin:
            return None
        return {
            "username": admin["username"],
            "created_at": admin.get("created_at", "--"),
            "last_login": admin.get("last_login", "--")
        }
