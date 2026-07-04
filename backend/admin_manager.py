import json
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class AdminManager:

    def __init__(self, data_dir=None):
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
                self.admins = json.loads(self.admin_file.read_text(encoding="utf-8"))
            except Exception as e:
                logger.error(f"读取管理员数据失败: {e}")
                self.admins = {}

    def _save(self):
        try:
            self.admin_file.write_text(json.dumps(self.admins, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.error(f"保存管理员数据失败: {e}")

    def _ensure_default(self):
        if "guanli001" not in self.admins:
            self.admins["guanli001"] = {
                "username": "guanli001",
                "password": self._hash("change-me-on-first-login"),
                "created_at": datetime.now().isoformat(),
                "last_login": None,
            }
            self._save()
            logger.info("已创建默认管理员账号: guanli001")

    @staticmethod
    def _hash(pwd):
        return hashlib.sha256(pwd.encode("utf-8")).hexdigest()

    def login(self, username, password):
        u = username.strip()
        p = password.strip()
        if not u or not p:
            return {"success": False, "error": "请输入账号和密码"}
        a = self.admins.get(u)
        if not a:
            return {"success": False, "error": "账号不存在"}
        if a["password"] != self._hash(p):
            return {"success": False, "error": "密码错误"}
        a["last_login"] = datetime.now().isoformat()
        self._save()
        return {"success": True, "message": "登录成功", "username": u}

    def change_password(self, username, old_pwd, new_pwd):
        u = username.strip()
        a = self.admins.get(u)
        if not a:
            return {"success": False, "error": "账号不存在"}
        if a["password"] != self._hash(old_pwd):
            return {"success": False, "error": "原密码错误"}
        if len(new_pwd.strip()) < 6:
            return {"success": False, "error": "新密码至少6位"}
        a["password"] = self._hash(new_pwd.strip())
        self._save()
        return {"success": True, "message": "密码修改成功"}

    def verify(self, username, password):
        a = self.admins.get(username.strip())
        return a is not None and a["password"] == self._hash(password.strip())

    def get_admin(self, username):
        a = self.admins.get(username.strip())
        if not a:
            return None
        return {"username": a["username"], "created_at": a.get("created_at", "--"), "last_login": a.get("last_login", "--")}
