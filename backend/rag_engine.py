# 会理AI导游 - RAG检索增强引擎
import os
import json
import time
import logging
import hashlib
import math
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from collections import defaultdict
from pathlib import Path

import chromadb
from chromadb.config import Settings
import jieba
from sentence_transformers import SentenceTransformer
import requests

from config import Config

logger = logging.getLogger(__name__)


class RAGEngine:

    def __init__(self):
        self.config = Config
        self.embedding_model = None
        self.chroma_client = None
        self.collection = None
        self.knowledge_base_ready = False
        self.bm25_index = {}
        self._init_components()
        self._init_bm25()

    # ---------- 初始化 ----------

    def _init_components(self):
        # 加载嵌入模型
        try:
            logger.info(f"加载嵌入模型: {self.config.EMBEDDING_MODEL}")
            self.embedding_model = SentenceTransformer(
                self.config.EMBEDDING_MODEL,
                model_kwargs={
                    "cache_dir": self.config.EMBEDDING_CACHE_PATH,
                    "local_files_only": True,
                },
                device="cpu"
            )
        except Exception as e:
            logger.error(f"嵌入模型加载失败: {e}")
            self.embedding_model = None
            self.knowledge_base_ready = False
            return

        # 连接 ChromaDB
        try:
            logger.info(f"连接 ChromaDB: {self.config.CHROMA_DB_PATH}")
            self.chroma_client = chromadb.PersistentClient(
                path=self.config.CHROMA_DB_PATH,
                settings=Settings(anonymized_telemetry=False)
            )
            try:
                self.collection = self.chroma_client.get_collection(self.config.COLLECTION_NAME)
                logger.info(f"已加载集合: {self.config.COLLECTION_NAME}")
                self.knowledge_base_ready = self.collection.count() > 0
            except Exception:
                logger.warning("集合不存在，创建新集合")
                self.collection = self.chroma_client.create_collection(
                    name=self.config.COLLECTION_NAME,
                    metadata={"description": "会理市旅游知识库"}
                )
                self.knowledge_base_ready = False

            # 空集合自动导入
            if self.collection is not None and self.collection.count() == 0:
                logger.warning("知识库为空，尝试从 raw_data 导入...")
                n = self._bootstrap_knowledge_base()
                self.knowledge_base_ready = n > 0

            logger.info("RAG 引擎初始化完成")
        except Exception as e:
            logger.error(f"ChromaDB 初始化失败: {e}")
            self.knowledge_base_ready = False

    def _bootstrap_knowledge_base(self):
        """向量库为空时自动从 raw_data / processed 导入数据"""
        raw_dir = Path(self.config.KNOWLEDGE_BASE_DIR) / "raw_data"
        processed = Path(self.config.KNOWLEDGE_BASE_DIR) / "processed" / "scenic_spots.json"

        docs, metas, ids = [], [], []

        # 优先读处理好的景点 JSON
        if processed.exists():
            try:
                items = json.loads(processed.read_text(encoding="utf-8"))
                for item in items:
                    content = (item.get("content") or item.get("summary") or "").strip()
                    if not content:
                        continue
                    title = item.get("title", "未命名")
                    for idx, chunk in enumerate(self._split_text(content)):
                        cid = hashlib.md5(f"{item.get('id', title)}-{idx}".encode()).hexdigest()[:16]
                        ids.append(cid)
                        docs.append(chunk)
                        metas.append({
                            "title": title,
                            "source": item.get("filename", "scenic_spots.json"),
                            "chunk_index": idx,
                            "tags": ",".join(item.get("tags", [])),
                            "location": item.get("location"),
                            "opening_hours": item.get("opening_hours"),
                            "ticket_price": item.get("ticket_price"),
                            "rating": item.get("rating"),
                            "lat": item.get("lat"),
                            "lng": item.get("lng"),
                        })
                logger.info(f"从 scenic_spots.json 读取 {len(items)} 条")
            except Exception as e:
                logger.warning(f"读取 scenic_spots.json 失败: {e}")

        # 再读 raw_data 里散落的 .txt/.md
        if raw_dir.exists():
            for fp in raw_dir.glob("*"):
                if fp.suffix.lower() not in (".txt", ".md"):
                    continue
                try:
                    text = fp.read_text(encoding="utf-8").strip()
                except UnicodeDecodeError:
                    text = fp.read_text(encoding="utf-8-sig").strip()
                except Exception:
                    continue
                if not text:
                    continue
                title = self._extract_title(text, fp.stem)
                for idx, chunk in enumerate(self._split_text(text)):
                    cid = hashlib.md5(f"{fp.name}-{idx}".encode()).hexdigest()[:16]
                    ids.append(cid)
                    docs.append(chunk)
                    metas.append({
                        "title": title,
                        "source": fp.name,
                        "chunk_index": idx,
                        "tags": self._infer_tags(text, fp.stem),
                    })

        if not docs:
            logger.warning("没有可导入的文本")
            return 0

        embs = self.embedding_model.encode(docs, batch_size=16, normalize_embeddings=True)
        self.collection.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs.tolist())
        logger.info(f"自动导入完成，{len(docs)} 个文本块")
        return len(docs)

    @staticmethod
    def _extract_title(content, fallback):
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            line = re.sub(r"^#+\s*", "", line)
            if len(line) <= 80:
                return line
        return fallback

    @staticmethod
    def _split_text(content, chunk_size=500, overlap=50):
        chunks = []
        start = 0
        while start < len(content):
            end = min(len(content), start + chunk_size)
            chunks.append(content[start:end])
            if end >= len(content):
                break
            start = max(0, end - overlap)
        return chunks

    @staticmethod
    def _infer_tags(content, fallback):
        tags = []
        t = f"{fallback} {content}"
        if "美食" in t or "羊肉粉" in t:
            tags.append("美食")
        if "古城" in t:
            tags.append("古城")
        if "会议" in t or "纪念地" in t:
            tags.append("红色旅游")
        if "绿陶" in t:
            tags.append("非遗")
        if "山" in t or "龙肘山" in t:
            tags.append("自然风光")
        return ",".join(tags)

    # ---------- BM25 ----------

    def _init_bm25(self):
        if not self.knowledge_base_ready:
            return
        try:
            all_data = self.collection.get(include=["documents", "metadatas"])
            for i, doc in enumerate(all_data["documents"]):
                doc_id = all_data["ids"][i]
                words = list(jieba.cut(doc))
                wf = defaultdict(int)
                for w in words:
                    wf[w] += 1
                self.bm25_index[doc_id] = {"words": words, "word_freq": dict(wf), "length": len(words)}
            logger.info(f"BM25 索引就绪，{len(self.bm25_index)} 篇文档")
        except Exception as e:
            logger.error(f"BM25 构建失败: {e}")

    def _bm25_score(self, query, doc_id):
        if doc_id not in self.bm25_index:
            return 0.0
        k1, b = 1.2, 0.75
        total_len = sum(d["length"] for d in self.bm25_index.values())
        avg_len = total_len / len(self.bm25_index)
        qwords = list(jieba.cut(query))
        di = self.bm25_index[doc_id]
        score = 0.0
        for w in qwords:
            if w not in di["word_freq"]:
                continue
            df = sum(1 for d in self.bm25_index.values() if w in d["word_freq"])
            idf = math.log((len(self.bm25_index) - df + 0.5) / (df + 0.5) + 1.0)
            tf = di["word_freq"][w]
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * di["length"] / avg_len))
        return score

    # ---------- 检索 ----------

    def _hybrid_search(self, query, top_k=None):
        if not self.knowledge_base_ready:
            return []
        if top_k is None:
            top_k = self.config.TOP_K_RESULTS

        try:
            q_emb = self.embedding_model.encode(query).tolist()
            vec_result = self.collection.query(
                query_embeddings=[q_emb],
                n_results=top_k * 2,
                include=["documents", "metadatas", "distances"]
            )

            # BM25 分数
            bm25 = {}
            for did in self.bm25_index:
                s = self._bm25_score(query, did)
                if s > 0:
                    bm25[did] = s
            max_bm25 = max(bm25.values()) if bm25 else 1.0

            results = []
            if vec_result["ids"] and vec_result["ids"][0]:
                for i, did in enumerate(vec_result["ids"][0]):
                    v_dist = vec_result["distances"][0][i]
                    v_score = 1.0 / (1.0 + v_dist)
                    b_score = bm25.get(did, 0.0) / max_bm25
                    hybrid = self.config.VECTOR_WEIGHT * v_score + self.config.BM25_WEIGHT * b_score
                    if hybrid >= self.config.SIMILARITY_THRESHOLD:
                        results.append({
                            "id": did,
                            "content": vec_result["documents"][0][i],
                            "metadata": vec_result["metadatas"][0][i],
                            "vector_score": v_score,
                            "bm25_score": b_score,
                            "hybrid_score": hybrid,
                        })

            results.sort(key=lambda x: x["hybrid_score"], reverse=True)
            return results[:top_k]
        except Exception as e:
            logger.error(f"混合检索失败: {e}")
            return []

    # ---------- 大模型调用 ----------

    def _call_llm(self, prompt, context=""):
        if not self.config.XIAOMI_API_KEY:
            return {"success": False, "error": "XIAOMI_API_KEY 未配置"}

        sys_msg = (
            "你是会理市专业导游，请根据提供的知识库信息回答游客问题。"
            "要求：准确、专业、友好；用中文回答；"
            "知识库没有的信息请如实告知；可适当补充旅游建议。"
        )
        msgs = [{"role": "system", "content": sys_msg}]
        if context:
            msgs.append({"role": "user", "content": f"参考信息：{context}"})
        msgs.append({"role": "user", "content": prompt})

        body = {
            "model": self.config.XIAOMI_MODEL,
            "messages": msgs,
            "max_tokens": self.config.MAX_TOKENS,
            "temperature": self.config.TEMPERATURE,
            "top_p": self.config.TOP_P,
        }

        url = f"{self.config.XIAOMI_BASE_URL}/chat/completions"
        # 兼容两种鉴权方式
        auth_headers = [
            {"api-key": self.config.XIAOMI_API_KEY, "Content-Type": "application/json"},
            {"Authorization": f"Bearer {self.config.XIAOMI_API_KEY}", "Content-Type": "application/json"},
        ]

        errors = []
        for h in auth_headers:
            try:
                r = requests.post(url, headers=h, json=body, timeout=self.config.REQUEST_TIMEOUT)
                if r.status_code == 200:
                    data = r.json()
                    return {
                        "success": True,
                        "content": data["choices"][0]["message"]["content"],
                        "model_used": self.config.XIAOMI_MODEL,
                    }
                errors.append(f"{r.status_code}: {r.text[:200]}")
            except requests.exceptions.RequestException as e:
                errors.append(str(e))

        return {"success": False, "error": " | ".join(errors) if errors else "未知错误"}

    # ---------- 降级 & 建议 ----------

    def _fallback(self, query, results):
        if not results:
            return {
                "reply": "抱歉，我暂时无法回答这个问题。您可以试试问其他关于会理旅游的问题。",
                "source": [],
                "suggestions": self._suggestions(query),
            }
        best = results[0]
        title = best["metadata"].get("title", "相关信息")
        return {
            "reply": f"根据知识库信息，关于{title}：\n\n{best['content']}",
            "source": [{"title": title, "content": best["content"], "score": best["hybrid_score"]}],
            "suggestions": self._suggestions(query),
        }

    def _suggestions(self, query):
        base = [
            "会理古城有什么特色？",
            "会理会议纪念地在哪里？",
            "龙肘山怎么去？",
            "会理有什么特色美食？",
            "会理绿陶有什么特点？",
        ]
        q = query
        if "开放" in q or "时间" in q:
            return ["会理古城开放时间", "会理会议纪念地开放时间", "龙肘山开放时间"]
        if "美食" in q or "吃" in q:
            return ["会理羊肉粉哪家好吃？", "会理有什么特色小吃？", "会理美食推荐"]
        if "交通" in q or "怎么去" in q:
            return ["会理古城怎么去？", "会理会议纪念地交通指南", "龙肘山自驾路线"]
        return base[:3]

    # ---------- 对外接口 ----------

    def is_available(self):
        return self.knowledge_base_ready and self.embedding_model is not None

    def has_knowledge_base(self):
        return self.knowledge_base_ready

    def get_knowledge_base_stats(self):
        if not self.knowledge_base_ready:
            return {"document_count": 0, "status": "not_initialized"}
        try:
            count = self.collection.count()
            tag_counts = {}
            raw = self.collection.get(include=["metadatas"])
            for m in raw["metadatas"]:
                t = m.get("tags", [])
                if isinstance(t, str):
                    t = [x.strip() for x in t.split(",") if x.strip()]
                for tag in t:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
            return {"document_count": count, "tags_count": tag_counts, "status": "ready"}
        except Exception as e:
            logger.error(f"统计知识库失败: {e}")
            return {"document_count": 0, "status": "error"}

    def generate_response(self, ctx):
        t0 = time.time()
        try:
            q = ctx["user_input"]
            loc = ctx.get("user_location")

            results = self._hybrid_search(q)

            # 拼接上下文
            ctx_text = ""
            if results:
                parts = []
                for i, r in enumerate(results[:3]):
                    title = r["metadata"].get("title", f"信息{i+1}")
                    parts.append(f"{i+1}. {title}: {r['content']}")
                ctx_text = "\n\n参考信息：\n" + "\n".join(parts)

            llm = self._call_llm(q, ctx_text)

            if llm["success"]:
                reply = llm["content"]
                model = llm.get("model_used", self.config.XIAOMI_MODEL)
            else:
                logger.warning(f"LLM 调用失败，降级: {llm.get('error')}")
                fb = self._fallback(q, results)
                reply = fb["reply"]
                model = "fallback"

            resp = {
                "reply": reply,
                "source": [],
                "suggestions": self._suggestions(q),
                "model_used": model,
                "search_results_count": len(results),
                "processing_time_ms": round((time.time() - t0) * 1000, 2),
            }

            if results:
                for r in results[:2]:
                    m = r["metadata"]
                    resp["source"].append({
                        "title": m.get("title", "未知"),
                        "content": r["content"][:100] + "...",
                        "score": round(r["hybrid_score"], 3),
                        "metadata": {k: v for k, v in m.items() if k not in ("chunk_index", "source")},
                    })

            return resp
        except Exception as e:
            logger.error(f"generate_response 异常: {e}")
            return {
                "reply": "抱歉，系统暂时无法处理您的请求，请稍后再试。",
                "source": [],
                "suggestions": self._suggestions(""),
                "model_used": "error",
                "error": str(e),
            }

    # ---------- 附近景点 ----------

    def find_nearby_attractions(self, lat, lng, radius_km):
        if not self.knowledge_base_ready:
            return []
        try:
            raw = self.collection.get(include=["documents", "metadatas"])
            nearby = []
            for i, m in enumerate(raw["metadatas"]):
                alat = m.get("lat")
                alng = m.get("lng")
                if alat is None or alng is None:
                    continue
                try:
                    d = self._haversine(lat, lng, float(alat), float(alng))
                    if d <= radius_km:
                        nearby.append({
                            "title": m.get("title", "未知景点"),
                            "content": raw["documents"][i][:200] + "...",
                            "metadata": m,
                            "distance_km": round(d, 2),
                        })
                except (ValueError, TypeError):
                    continue
            nearby.sort(key=lambda x: x["distance_km"])
            return nearby
        except Exception as e:
            logger.error(f"附近景点查询失败: {e}")
            return []

    @staticmethod
    def _haversine(lat1, lng1, lat2, lng2):
        from math import radians, sin, cos, sqrt, atan2
        lat1, lng1, lat2, lng2 = map(radians, [lat1, lng1, lat2, lng2])
        dlat = lat2 - lat1
        dlng = lng2 - lng1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlng/2)**2
        return 6371.0 * 2 * atan2(sqrt(a), sqrt(1-a))

    # ---------- 重建知识库 ----------

    def rebuild_knowledge_base(self, keep_original=True, clear_cache=True):
        try:
            logger.info("开始重建知识库...")
            # 重新扫描 raw_data 导入
            n = self._bootstrap_knowledge_base()
            self._init_bm25()
            return {
                "success": True,
                "message": f"重建完成，导入 {n} 个文本块",
                "chunks_created": n,
            }
        except Exception as e:
            logger.error(f"重建知识库失败: {e}")
            return {"success": False, "error": str(e)}
