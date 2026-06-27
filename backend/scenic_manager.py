import json
import uuid
import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ScenicImageManager:
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = str(Path(__file__).parent / "logs")
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_file = self.data_dir / "scenic_images.json"
        self.images_dir = self.data_dir / "scenic_images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.images: Dict[str, dict] = {}
        self._load()

    def _load(self):
        if self.images_file.exists():
            try:
                with open(self.images_file, "r", encoding="utf-8") as f:
                    self.images = json.load(f)
                logger.info(f"Loaded {len(self.images)} scenic images")
            except Exception as e:
                logger.error(f"Failed to load scenic images: {e}")
                self.images = {}

    def _save(self):
        try:
            with open(self.images_file, "w", encoding="utf-8") as f:
                json.dump(self.images, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save scenic images: {e}")

    def add_image(self, place_name: str, description: str, image_file) -> Dict:
        image_id = str(uuid.uuid4())[:8]
        ext = Path(image_file.filename).suffix or ".jpg"
        filename = f"{image_id}{ext}"
        filepath = self.images_dir / filename
        try:
            with open(filepath, "wb") as f:
                shutil.copyfileobj(image_file.stream, f)
        except Exception as e:
            logger.error(f"Failed to save image file: {e}")
            return {"success": False, "error": "图片保存失败"}

        self.images[image_id] = {
            "id": image_id,
            "place_name": place_name.strip(),
            "description": description.strip(),
            "filename": filename,
            "url": f"/api/scenic/local/{filename}",
            "created_at": datetime.now().isoformat()
        }
        self._save()
        logger.info(f"Added scenic image: {image_id} for {place_name}")
        return {"success": True, "message": "图片添加成功", "image": self.images[image_id]}

    def add_image_url(self, place_name: str, description: str, url: str) -> Dict:
        image_id = str(uuid.uuid4())[:8]
        self.images[image_id] = {
            "id": image_id,
            "place_name": place_name.strip(),
            "description": description.strip(),
            "filename": None,
            "url": url.strip(),
            "created_at": datetime.now().isoformat()
        }
        self._save()
        logger.info(f"Added scenic image URL: {image_id} for {place_name}")
        return {"success": True, "message": "图片链接添加成功", "image": self.images[image_id]}

    def delete_image(self, image_id: str) -> Dict:
        image_id = image_id.strip()
        image = self.images.get(image_id)
        if not image:
            return {"success": False, "error": "图片不存在"}
        if image.get("filename"):
            filepath = self.images_dir / image["filename"]
            if filepath.exists():
                try:
                    filepath.unlink()
                except Exception:
                    pass
        del self.images[image_id]
        self._save()
        logger.info(f"Deleted scenic image: {image_id}")
        return {"success": True, "message": "图片已删除"}

    def get_all_images(self) -> List[dict]:
        return list(self.images.values())

    def search_images(self, keyword: str) -> List[dict]:
        keyword = keyword.strip().lower()
        if not keyword:
            return self.get_all_images()
        results = []
        for img in self.images.values():
            if (keyword in img.get("place_name", "").lower() or
                    keyword in img.get("description", "").lower()):
                results.append(img)
        return results

    def get_image_path(self, filename: str) -> Optional[str]:
        for img in self.images.values():
            if img.get("filename") == filename:
                filepath = self.images_dir / filename
                return str(filepath) if filepath.exists() else None
        filepath = self.images_dir / filename
        return str(filepath) if filepath.exists() else None
