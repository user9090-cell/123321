#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
会理市AI数字人导游 - 知识库构建脚本
功能：读取原始文档，分块处理，生成向量数据库
作者：资深全栈架构师
日期：2026年4月20日
"""

import os
import json
import hashlib
import re
from pathlib import Path
from typing import List, Dict, Any
import logging

# 第三方库
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
import numpy as np

try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    RecursiveCharacterTextSplitter = None

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent


class SimpleRecursiveCharacterTextSplitter:
    """在缺少 langchain-text-splitters 时提供基础分块能力。"""

    def __init__(
        self,
        chunk_size: int,
        chunk_overlap: int,
        length_function=len,
        separators: List[str] | None = None
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.length_function = length_function
        self.separators = separators or ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]

    def split_text(self, text: str) -> List[str]:
        if not text:
            return []

        pieces = self._split_recursive(text, self.separators)
        return self._merge_pieces([piece for piece in pieces if piece and piece.strip()])

    def _split_recursive(self, text: str, separators: List[str]) -> List[str]:
        if self.length_function(text) <= self.chunk_size or not separators:
            return [text]

        separator = separators[0]
        if separator == "":
            return [text[i:i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]

        parts = text.split(separator)
        if len(parts) == 1:
            return self._split_recursive(text, separators[1:])

        results = []
        for index, part in enumerate(parts):
            if not part:
                continue
            candidate = part if index == len(parts) - 1 else part + separator
            if self.length_function(candidate) <= self.chunk_size:
                results.append(candidate)
            else:
                results.extend(self._split_recursive(candidate, separators[1:]))
        return results

    def _merge_pieces(self, pieces: List[str]) -> List[str]:
        chunks = []
        current = ""

        for piece in pieces:
            if not current:
                current = piece
                continue

            if self.length_function(current) + self.length_function(piece) <= self.chunk_size:
                current += piece
                continue

            chunks.append(current.strip())
            overlap = current[-self.chunk_overlap:] if self.chunk_overlap > 0 else ""
            current = overlap + piece

        if current.strip():
            chunks.append(current.strip())

        return chunks

class KnowledgeBaseBuilder:
    """知识库构建器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化知识库构建器
        
        Args:
            config: 配置字典
        """
        self.config = config
        self.embedding_model = None
        self.chroma_client = None
        self.collection = None
        
        # 初始化路径
        self.raw_data_dir = Path(config['raw_data_dir'])
        self.processed_dir = Path(config['processed_dir'])
        self.chroma_db_dir = Path(config['chroma_db_dir'])
        
        # 创建目录
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.chroma_db_dir.mkdir(parents=True, exist_ok=True)
        
    def load_embedding_model(self):
        """加载嵌入模型"""
        logger.info("正在加载嵌入模型...")
        try:
            # 使用BAAI的中文优化嵌入模型
            model_name = "BAAI/bge-small-zh-v1.5"
            self.embedding_model = SentenceTransformer(model_name)
            logger.info(f"嵌入模型加载成功: {model_name}")
        except Exception as e:
            logger.error(f"加载嵌入模型失败: {e}")
            raise
    
    def init_chromadb(self):
        """初始化ChromaDB"""
        logger.info("正在初始化ChromaDB...")
        try:
            # 创建ChromaDB客户端
            self.chroma_client = chromadb.PersistentClient(
                path=str(self.chroma_db_dir),
                settings=Settings(anonymized_telemetry=False)
            )
            
            # 创建或获取集合
            collection_name = self.config['collection_name']
            try:
                self.collection = self.chroma_client.get_collection(collection_name)
                logger.info(f"使用现有集合: {collection_name}")
            except:
                self.collection = self.chroma_client.create_collection(
                    name=collection_name,
                    metadata={"description": "会理市旅游知识库"}
                )
                logger.info(f"创建新集合: {collection_name}")
                
        except Exception as e:
            logger.error(f"初始化ChromaDB失败: {e}")
            raise
    
    def read_raw_documents(self) -> List[Dict[str, Any]]:
        """
        读取原始文档
        
        Returns:
            文档列表，每个文档包含内容和元数据
        """
        logger.info(f"正在读取原始文档，目录: {self.raw_data_dir}")
        
        documents = []
        supported_extensions = ['.txt', '.pdf', '.md']
        
        for file_path in self.raw_data_dir.glob('*'):
            if file_path.suffix.lower() in supported_extensions:
                try:
                    content = self._read_file(file_path)
                    
                    # 提取文档信息
                    doc_info = {
                        'id': hashlib.md5(str(file_path).encode()).hexdigest()[:16],
                        'file_name': file_path.name,
                        'file_path': str(file_path),
                        'content': content,
                        'title': self._extract_title(content, file_path.name),
                        'metadata': self._extract_metadata(content, file_path.name)
                    }
                    
                    documents.append(doc_info)
                    logger.info(f"读取文档: {file_path.name}")
                    
                except Exception as e:
                    logger.error(f"读取文档失败 {file_path}: {e}")
        
        logger.info(f"共读取 {len(documents)} 个文档")
        return documents
    
    def _read_file(self, file_path: Path) -> str:
        """读取文件内容"""
        if file_path.suffix.lower() == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        elif file_path.suffix.lower() == '.pdf':
            # 简单实现，实际项目中可以使用PyPDF2或pdfplumber
            try:
                import PyPDF2
                with open(file_path, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    text = ''
                    for page in pdf_reader.pages:
                        text += page.extract_text()
                    return text
            except ImportError:
                logger.warning("PyPDF2未安装，PDF文件将跳过")
                return ""
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
    
    def _extract_title(self, content: str, file_name: str) -> str:
        """从内容中提取标题"""
        # 尝试从第一行提取标题
        lines = content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and len(line) < 100:  # 标题通常不会太长
                # 移除常见的标题标记
                line = re.sub(r'^#+\s*', '', line)
                line = re.sub(r'^=+\s*$', '', line)
                line = re.sub(r'^-+\s*$', '', line)
                if line:
                    return line
        
        # 如果无法提取，使用文件名（不含扩展名）
        return Path(file_name).stem
    
    def _extract_metadata(self, content: str, file_name: str) -> Dict[str, Any]:
        """从内容中提取元数据"""
        metadata = {
            'source': file_name,
            'chars': len(content),
            'lines': len(content.split('\n'))
        }
        
        # 尝试提取基本信息模式
        patterns = {
            '开放时间': r'开放时间[：:]\s*([^\n]+)',
            '门票价格': r'门票价格[：:]\s*([^\n]+)',
            '建议游览时间': r'建议游览时间[：:]\s*([^\n]+)',
            '最佳游览季节': r'最佳游览季节[：:]\s*([^\n]+)',
        }
        
        for key, pattern in patterns.items():
            match = re.search(pattern, content)
            if match:
                metadata[key] = match.group(1).strip()
        
        return metadata
    
    def split_documents(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        文档分块
        
        Args:
            documents: 原始文档列表
            
        Returns:
            分块后的文档列表
        """
        logger.info("正在对文档进行分块处理...")
        
        splitter_cls = RecursiveCharacterTextSplitter or SimpleRecursiveCharacterTextSplitter
        if RecursiveCharacterTextSplitter is None:
            logger.warning("未检测到 langchain-text-splitters，使用内置文本分块器")

        text_splitter = splitter_cls(
            chunk_size=self.config['chunk_size'],
            chunk_overlap=self.config['chunk_overlap'],
            length_function=len,
            separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]
        )
        
        chunks = []
        chunk_id = 0
        
        for doc in documents:
            # 使用LangChain的分块器
            text_chunks = text_splitter.split_text(doc['content'])
            
            for i, text_chunk in enumerate(text_chunks):
                chunk_info = {
                    'id': f"{doc['id']}_chunk_{i}",
                    'document_id': doc['id'],
                    'chunk_index': i,
                    'content': text_chunk,
                    'title': doc['title'],
                    'metadata': {
                        **doc['metadata'],
                        'chunk_total': len(text_chunks),
                        'chunk_size': len(text_chunk)
                    }
                }
                chunks.append(chunk_info)
                chunk_id += 1
        
        logger.info(f"文档分块完成，共生成 {len(chunks)} 个文本块")
        return chunks
    
    def generate_embeddings(self, chunks: List[Dict[str, Any]]) -> List[np.ndarray]:
        """
        生成文本嵌入向量
        
        Args:
            chunks: 文本块列表
            
        Returns:
            嵌入向量列表
        """
        logger.info("正在生成文本嵌入向量...")
        
        # 提取文本内容
        texts = [chunk['content'] for chunk in chunks]
        
        # 生成嵌入向量
        embeddings = self.embedding_model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            normalize_embeddings=True
        )
        
        logger.info(f"嵌入向量生成完成，形状: {embeddings.shape}")
        return embeddings
    
    def save_to_chromadb(self, chunks: List[Dict[str, Any]], embeddings: List[np.ndarray]):
        """
        保存到ChromaDB
        
        Args:
            chunks: 文本块列表
            embeddings: 嵌入向量列表
        """
        logger.info("正在保存到ChromaDB...")
        
        # 准备数据
        ids = [chunk['id'] for chunk in chunks]
        documents = [chunk['content'] for chunk in chunks]
        metadatas = []
        
        for chunk in chunks:
            metadata = {
                'title': chunk['title'],
                'document_id': chunk['document_id'],
                'chunk_index': chunk['chunk_index'],
                'source': chunk['metadata']['source'],
                'chars': chunk['metadata'].get('chars', 0),
                'lines': chunk['metadata'].get('lines', 0)
            }
            
            # 添加提取的元数据
            for key in ['开放时间', '门票价格', '建议游览时间', '最佳游览季节']:
                if key in chunk['metadata']:
                    metadata[key] = chunk['metadata'][key]
            
            metadatas.append(metadata)
        
        # 添加到集合
        self.collection.add(
            embeddings=embeddings.tolist(),
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
        
        logger.info(f"成功保存 {len(chunks)} 个文本块到ChromaDB")
    
    def save_processed_data(self, chunks: List[Dict[str, Any]]):
        """
        保存处理后的数据到JSON文件
        
        Args:
            chunks: 文本块列表
        """
        logger.info("正在保存处理后的数据...")
        
        output_file = self.processed_dir / 'processed_chunks.json'
        
        # 简化数据以节省空间
        simplified_chunks = []
        for chunk in chunks:
            simplified = {
                'id': chunk['id'],
                'document_id': chunk['document_id'],
                'title': chunk['title'],
                'content_preview': chunk['content'][:200] + '...' if len(chunk['content']) > 200 else chunk['content'],
                'metadata': chunk['metadata']
            }
            simplified_chunks.append(simplified)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(simplified_chunks, f, ensure_ascii=False, indent=2)
        
        logger.info(f"处理后的数据已保存到: {output_file}")
    
    def build(self):
        """构建知识库主流程"""
        logger.info("开始构建知识库...")
        
        try:
            # 1. 加载嵌入模型
            self.load_embedding_model()
            
            # 2. 初始化ChromaDB
            self.init_chromadb()
            
            # 3. 读取原始文档
            documents = self.read_raw_documents()
            if not documents:
                logger.warning("未找到任何文档，知识库构建终止")
                return
            
            # 4. 文档分块
            chunks = self.split_documents(documents)
            
            # 5. 生成嵌入向量
            embeddings = self.generate_embeddings(chunks)
            
            # 6. 保存到ChromaDB
            self.save_to_chromadb(chunks, embeddings)
            
            # 7. 保存处理后的数据
            self.save_processed_data(chunks)
            
            # 8. 统计信息
            self.print_statistics(chunks)
            
            logger.info("知识库构建完成！")
            
        except Exception as e:
            logger.error(f"知识库构建失败: {e}")
            raise
    
    def print_statistics(self, chunks: List[Dict[str, Any]]):
        """打印统计信息"""
        logger.info("=" * 50)
        logger.info("知识库统计信息")
        logger.info("=" * 50)
        
        # 按文档统计
        doc_chunks = {}
        for chunk in chunks:
            doc_id = chunk['document_id']
            doc_chunks[doc_id] = doc_chunks.get(doc_id, 0) + 1
        
        logger.info(f"文档总数: {len(doc_chunks)}")
        logger.info(f"文本块总数: {len(chunks)}")
        
        # 内容长度统计
        content_lengths = [len(chunk['content']) for chunk in chunks]
        if content_lengths:
            logger.info(f"平均文本块长度: {np.mean(content_lengths):.0f} 字符")
            logger.info(f"最小文本块长度: {min(content_lengths)} 字符")
            logger.info(f"最大文本块长度: {max(content_lengths)} 字符")
        
        # 显示每个文档的信息
        logger.info("\n文档详情:")
        for doc_id, count in doc_chunks.items():
            # 查找对应的文档标题
            title = next((chunk['title'] for chunk in chunks if chunk['document_id'] == doc_id), "未知")
            logger.info(f"  - {title}: {count} 个文本块")
        
        logger.info("=" * 50)


def main():
    """主函数"""
    # 配置参数
    config = {
        'raw_data_dir': str(SCRIPT_DIR / 'raw_data'),
        'processed_dir': str(SCRIPT_DIR / 'processed'),
        'chroma_db_dir': str(PROJECT_ROOT / 'backend' / 'chroma_db'),
        'collection_name': 'huili_knowledge_base',
        'chunk_size': 500,      # 文本块大小
        'chunk_overlap': 50,    # 重叠字符数
    }
    
    try:
        # 创建构建器并执行
        builder = KnowledgeBaseBuilder(config)
        builder.build()
        
        print("\n✅ 知识库构建成功！")
        print(f"向量数据库位置: {config['chroma_db_dir']}")
        print(f"集合名称: {config['collection_name']}")
        
    except Exception as e:
        print(f"\n❌ 知识库构建失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
