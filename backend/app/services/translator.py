"""
翻译核心服务 — 从 md3 项目移植的分块翻译引擎

职责：
- ContentChunker: 将长文本按段落/句子边界拆分为适合 LLM 处理的块
- PartialTranslationAssembler: 将已翻译的块与原文混合组装
- LLMTranslator: 调用 LLM 进行翻译，解析 [dictionary] + [result] 格式
- GoogleTranslator: 调用 Google 翻译 API

设计原则：
- 纯业务逻辑，不依赖 HTTP / ORM
- 异步接口，支持并发翻译
- 统一的提示词模板和输出格式解析
"""

import asyncio
import hashlib
import re
import time
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass

from ..core.logging import get_logger
from ..core.exceptions import ExternalServiceException
from ..domain.entities.translation import TextChunk, TranslationProvider

logger = get_logger("translator")


# ==================== 默认提示词模板 ====================

DEFAULT_PROMPT_TEMPLATE = """You are a professional literary translator. Your task is to translate the following text into {target_language}.

Requirements:
1. Maintain the original paragraph structure
2. Preserve the literary style and tone
3. Translate character names and places consistently using the provided dictionary
4. For new proper nouns, add them to the dictionary

{dictionary_text}

Text to translate:
{text}

Output format:
[dictionary]
ProperNoun -> Translation
[result]
Translated text..."""


# ==================== ContentChunker ====================

class ContentChunker:
    """
    分块翻译器
    
    - 按段落拆分文本
    - 每个 chunk 有最大字符限制
    - 超大段落按句子边界进一步拆分
    - 保持段落索引映射
    """
    
    def __init__(self, max_chars_per_chunk: int = 3000):
        self.max_chars_per_chunk = max_chars_per_chunk
    
    def chunk(self, text: str) -> List[TextChunk]:
        """将文本拆分为多个块"""
        paragraphs = text.split("\n")
        chunks: List[TextChunk] = []
        current_paragraphs: List[Tuple[int, str]] = []
        current_length = 0
        chunk_index = 0
        
        for para_idx, paragraph in enumerate(paragraphs):
            para = paragraph.strip()
            if not para:
                # 空段落直接加入当前块
                current_paragraphs.append((para_idx, paragraph))
                continue
            
            para_len = len(para)
            
            if para_len > self.max_chars_per_chunk:
                # 超大段落：先flush当前块，再拆分该段落
                if current_paragraphs:
                    chunks.append(self._build_chunk(chunk_index, current_paragraphs))
                    chunk_index += 1
                    current_paragraphs = []
                    current_length = 0
                
                # 按句子边界拆分超大段落
                sentence_chunks = self._split_long_paragraph(para_idx, para)
                for sc in sentence_chunks:
                    chunks.append(TextChunk(
                        index=chunk_index,
                        content=sc["content"],
                        paragraph_indices=sc["indices"]
                    ))
                    chunk_index += 1
                continue
            
            if current_length + para_len > self.max_chars_per_chunk and current_paragraphs:
                # 当前块已满，创建新块
                chunks.append(self._build_chunk(chunk_index, current_paragraphs))
                chunk_index += 1
                current_paragraphs = []
                current_length = 0
            
            current_paragraphs.append((para_idx, paragraph))
            current_length += para_len + 1  # +1 for newline
        
        # 处理剩余的段落
        if current_paragraphs:
            chunks.append(self._build_chunk(chunk_index, current_paragraphs))
        
        logger.info(f"[Chunker] 文本分块完成: {len(chunks)} chunks, total_chars={len(text)}")
        return chunks
    
    def _build_chunk(self, index: int, paragraphs: List[Tuple[int, str]]) -> TextChunk:
        content = "\n".join(p[1] for p in paragraphs)
        indices = [p[0] for p in paragraphs]
        return TextChunk(index=index, content=content, paragraph_indices=indices)
    
    def _split_long_paragraph(self, para_idx: int, paragraph: str) -> List[Dict]:
        """按句子边界拆分超长段落"""
        # 句子边界：. ! ? 。！？ 后跟空格或换行
        sentence_pattern = r'(?<=[.!?。！？])\s*'
        sentences = re.split(sentence_pattern, paragraph)
        
        result: List[Dict] = []
        current_sentences: List[str] = []
        current_len = 0
        
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            s_len = len(s)
            
            if s_len > self.max_chars_per_chunk:
                # 单句超过限制，强制按字符切分
                if current_sentences:
                    result.append({
                        "content": " ".join(current_sentences),
                        "indices": [para_idx]
                    })
                    current_sentences = []
                    current_len = 0
                
                for i in range(0, s_len, self.max_chars_per_chunk):
                    part = s[i:i + self.max_chars_per_chunk]
                    result.append({
                        "content": part,
                        "indices": [para_idx]
                    })
                continue
            
            if current_len + s_len > self.max_chars_per_chunk and current_sentences:
                result.append({
                    "content": " ".join(current_sentences),
                    "indices": [para_idx]
                })
                current_sentences = []
                current_len = 0
            
            current_sentences.append(s)
            current_len += s_len + 1
        
        if current_sentences:
            result.append({
                "content": " ".join(current_sentences),
                "indices": [para_idx]
            })
        
        return result
    
    @staticmethod
    def merge(chunks: List[TextChunk]) -> str:
        """将块按原始顺序合并为完整文本"""
        sorted_chunks = sorted(chunks, key=lambda c: c.index)
        return "\n\n".join(c.content for c in sorted_chunks)


# ==================== PartialTranslationAssembler ====================

class PartialTranslationAssembler:
    """
    混合组装器
    
    - 将已翻译的 chunk 替换原文
    - 实时混合显示
    """
    
    @staticmethod
    def assemble(original_chunks: List[TextChunk], translated_map: Dict[int, str]) -> str:
        """
        将已翻译的 chunk 与原文混合组装
        
        Args:
            original_chunks: 原始文本块列表
            translated_map: {chunk_index: translated_text}
        
        Returns:
            组装后的完整文本（已翻译的用译文，未翻译的保留原文）
        """
        sorted_chunks = sorted(original_chunks, key=lambda c: c.index)
        parts: List[str] = []
        
        for chunk in sorted_chunks:
            if chunk.index in translated_map and translated_map[chunk.index]:
                parts.append(translated_map[chunk.index])
            else:
                parts.append(chunk.content)
        
        return "\n\n".join(parts)
    
    @staticmethod
    def has_partial_translation(translated_map: Dict[int, str]) -> bool:
        """是否有部分翻译结果"""
        return bool(translated_map)
    
    @staticmethod
    def progress(translated_map: Dict[int, str], total_chunks: int) -> Tuple[int, int]:
        """返回 (已完成数, 总数)"""
        completed = len(translated_map)
        return completed, total_chunks


# ==================== LLMTranslator ====================

class LLMTranslator:
    """
    LLM 翻译器
    
    - 调用现有的 LLMService.call_llm
    - 解析 [dictionary] 和 [result] 两部分输出
    - 支持重试机制
    """
    
    def __init__(
        self,
        llm_service,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        temperature: float = 1.3,
        max_tokens: int = 4000,
        retry_count: int = 3
    ):
        self.llm_service = llm_service
        self.prompt_template = prompt_template
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.retry_count = retry_count
    
    async def translate(
        self,
        text: str,
        target_language: str = "zh-CN",
        dictionary_text: str = "",
        on_progress: Optional[Callable[[int, int], None]] = None
    ) -> Tuple[str, Dict[str, str]]:
        """
        翻译文本
        
        Returns:
            (translated_text, new_dictionary_entries)
        """
        prompt = self.prompt_template.format(
            target_language=target_language,
            dictionary_text=dictionary_text or "(No dictionary entries yet)",
            text=text
        )
        
        system = "You are a professional literary translator. Follow the output format strictly."
        
        for attempt in range(self.retry_count + 1):
            try:
                logger.info(f"[LLMTranslator] 翻译请求: attempt={attempt + 1}, text_len={len(text)}")
                
                response = await self.llm_service.call_llm(
                    prompt=prompt,
                    system=system,
                    max_tokens=self.max_tokens
                )
                
                translated_text, dictionary_entries = self._parse_response(response)
                
                logger.info(
                    f"[LLMTranslator] 翻译成功: entries={len(dictionary_entries)}",
                    extra={"action": "llm_translate", "entries": len(dictionary_entries)}
                )
                
                return translated_text, dictionary_entries
                
            except ExternalServiceException:
                if attempt < self.retry_count:
                    wait_time = 2 ** attempt  # 指数退避
                    logger.warning(f"[LLMTranslator] 翻译失败，{wait_time}s 后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                logger.error(f"[LLMTranslator] 翻译异常: {type(e).__name__}: {e}", exc_info=True)
                if attempt < self.retry_count:
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise ExternalServiceException(f"LLM 翻译失败: {e}")
        
        raise ExternalServiceException("LLM 翻译全部重试失败")
    
    def _parse_response(self, response: str) -> Tuple[str, Dict[str, str]]:
        """
        解析 LLM 响应，提取 [dictionary] 和 [result] 两部分
        
        Returns:
            (translated_text, dictionary_entries)
        """
        dictionary_entries: Dict[str, str] = {}
        translated_text = response.strip()
        
        # 提取 dictionary 部分
        dict_match = re.search(
            r'\[dictionary\](.*?)\[result\]',
            response,
            re.DOTALL | re.IGNORECASE
        )
        
        if dict_match:
            dict_text = dict_match.group(1).strip()
            translated_text = response[dict_match.end():].strip()
            
            # 解析词典条目：ProperNoun -> Translation
            for line in dict_text.split("\n"):
                line = line.strip()
                if not line or line.startswith("-"):
                    continue
                # 支持 -> 或 : 或 = 分隔
                for sep in ["->", ":", "="]:
                    if sep in line:
                        parts = line.split(sep, 1)
                        if len(parts) == 2:
                            original = parts[0].strip()
                            translated = parts[1].strip()
                            if original and translated:
                                dictionary_entries[original] = translated
                            break
        
        return translated_text, dictionary_entries


# ==================== GoogleTranslator ====================

class GoogleTranslator:
    """
    Google 翻译器
    
    - 使用 aiohttp 调用 translate.googleapis.com
    - 免费、无需 API Key
    """
    
    def __init__(self):
        self.base_url = "https://translate.googleapis.com/translate_a/single"
    
    async def translate(
        self,
        text: str,
        target_language: str = "zh-CN",
        source_language: str = "auto"
    ) -> Tuple[str, Dict[str, str]]:
        """
        调用 Google 翻译
        
        Returns:
            (translated_text, empty_dict)  # Google 翻译不返回词典
        """
        import aiohttp
        
        params = {
            "client": "gtx",
            "sl": source_language,
            "tl": target_language,
            "dt": "t",
            "q": text,
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        logger.info(f"[GoogleTranslator] 请求翻译: text_len={len(text)}, tl={target_language}")
        
        try:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(self.base_url, params=params, headers=headers) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        logger.error(
                            f"[GoogleTranslator] API 错误: HTTP {resp.status}",
                            extra={"action": "google_translate_error", "status_code": resp.status}
                        )
                        raise ExternalServiceException(
                            f"Google 翻译 API 错误: HTTP {resp.status}",
                            details={"status_code": resp.status}
                        )
                    
                    data = await resp.json()
                    
                    # 解析 Google 翻译响应格式
                    # data[0] 是翻译片段列表，每个片段是 [translated, original, ...]
                    translated_parts = []
                    if data and isinstance(data, list) and len(data) > 0:
                        for item in data[0]:
                            if isinstance(item, list) and len(item) > 0:
                                translated_parts.append(item[0])
                    
                    translated_text = "".join(translated_parts)
                    
                    logger.info(
                        f"[GoogleTranslator] 翻译成功: result_len={len(translated_text)}",
                        extra={"action": "google_translate", "result_length": len(translated_text)}
                    )
                    
                    return translated_text, {}
                    
        except ExternalServiceException:
            raise
        except Exception as e:
            logger.error(f"[GoogleTranslator] 翻译异常: {type(e).__name__}: {e}", exc_info=True)
            raise ExternalServiceException(f"Google 翻译服务暂不可用: {e}")


# ==================== TranslationConstants ====================

PROVIDER_GOOGLE = "google"
PROVIDER_LLM = "llm"
DEFAULT_TEMPERATURE = 1.3
DEFAULT_MAX_CHARS_PER_CHUNK = 3000
DEFAULT_CONCURRENT_CHUNKS = 2
DEFAULT_RETRY_COUNT = 3
DEFAULT_TARGET_LANGUAGE = "zh-CN"
