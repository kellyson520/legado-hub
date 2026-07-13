"""
测试翻译模块: app.services.translator 和 app.domain.entities.translation

测试范围:
- ContentChunker: 文本分块、合并、超大段落拆分
- PartialTranslationAssembler: 混合组装、进度计算
- LLMTranslator: LLM 响应解析、重试机制
- GoogleTranslator: Google 翻译 API 调用、错误处理
- TranslationJob: 状态流转、进度计算
- TranslationChunk: 标记翻译/失败
- TranslationDictionary: 词典条目管理、上限控制
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch, PropertyMock

from app.services.translator import (
    ContentChunker,
    PartialTranslationAssembler,
    LLMTranslator,
    GoogleTranslator,
    DEFAULT_PROMPT_TEMPLATE,
)
from app.domain.entities.translation import (
    TextChunk,
    TranslationChunk,
    TranslationDictionary,
    TranslationJob,
    TranslationStatus,
    TranslationProvider,
)
from app.core.exceptions import ExternalServiceException


# ==================== ContentChunker ====================

class TestContentChunkerChunk:
    """测试 ContentChunker.chunk() 方法"""

    def test_多段落正常分块(self):
        """多个短段落应被合并为一个 chunk"""
        chunker = ContentChunker(max_chars_per_chunk=3000)
        text = "第一段内容。\n第二段内容。\n第三段内容。"
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].paragraph_indices == [0, 1, 2]

    def test_空字符串返回包含空内容的chunk(self):
        """空字符串经 split("\\n") 产生一个空段落，被放入一个 chunk"""
        chunker = ContentChunker()
        chunks = chunker.chunk("")
        assert len(chunks) == 1
        assert chunks[0].content == ""

    def test_单段落(self):
        """单个段落应产生一个 chunk"""
        chunker = ContentChunker()
        text = "这是一段话。"
        chunks = chunker.chunk(text)
        assert len(chunks) == 1
        assert chunks[0].content == text
        assert chunks[0].paragraph_indices == [0]

    def test_段落超过max_chars按句子拆分(self):
        """单个段落超过 max_chars 时应按句子边界拆分"""
        chunker = ContentChunker(max_chars_per_chunk=20)
        text = "Hello world. How are you? I am fine. Good bye."
        chunks = chunker.chunk(text)
        # 应该被拆分成多个 chunk，每个 chunk 包含同一 paragraph_index
        assert len(chunks) >= 2
        # 所有 chunk 的 paragraph_indices 都应包含原始段落的索引
        for c in chunks:
            assert all(idx == 0 for idx in c.paragraph_indices)

    def test_单句超过max_chars强制字符切分(self):
        """单个句子超过 max_chars 时应强制按字符切分"""
        chunker = ContentChunker(max_chars_per_chunk=20)
        # 一个没有句子边界的超长字符串
        text = "A" * 100
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2
        # 每个 chunk 不超过 max_chars
        for c in chunks:
            assert len(c.content) <= 20

    def test_多段落超出单块容量分多块(self):
        """多个段落总量超过单块容量时，应自动分配到多个 chunk"""
        chunker = ContentChunker(max_chars_per_chunk=30)
        text = "段落一短文本。\n段落二也短文本。\n段落三还是短文本。\n段落四最后了。"
        chunks = chunker.chunk(text)
        assert len(chunks) >= 2
        # 验证合并后的完整文本可以通过 merge 还原
        merged = ContentChunker.merge(chunks)
        assert "段落一短文本。" in merged
        assert "段落四最后了。" in merged

    def test_包含空行的文本(self):
        """包含空行的文本应正常处理"""
        chunker = ContentChunker()
        text = "第一段。\n\n第二段。\n\n第三段。"
        chunks = chunker.chunk(text)
        # 空行也被视为段落，包含在同一 chunk 中
        assert len(chunks) >= 1
        merged = ContentChunker.merge(chunks)
        assert merged == text


class TestContentChunkerBuildChunk:
    """测试 ContentChunker._build_chunk() 方法"""

    def test_构建chunk内容正确(self):
        """_build_chunk 应正确合并段落内容"""
        chunker = ContentChunker()
        paragraphs = [(0, "第一行"), (1, "第二行"), (2, "第三行")]
        chunk = chunker._build_chunk(0, paragraphs)
        assert chunk.index == 0
        assert chunk.content == "第一行\n第二行\n第三行"
        assert chunk.paragraph_indices == [0, 1, 2]

    def test_空段落列表产生空内容(self):
        """空段落列表应产生空内容 chunk"""
        chunker = ContentChunker()
        chunk = chunker._build_chunk(0, [])
        assert chunk.content == ""
        assert chunk.paragraph_indices == []


class TestContentChunkerSplitLongParagraph:
    """测试 ContentChunker._split_long_paragraph() 方法"""

    def test_按句子边界拆分(self):
        """正常长段落按句子边界拆分"""
        chunker = ContentChunker(max_chars_per_chunk=30)
        paragraph = "Hello world. How are you? I am fine today."
        result = chunker._split_long_paragraph(0, paragraph)
        assert len(result) >= 2
        for r in result:
            assert len(r["content"]) <= 30
            assert r["indices"] == [0]

    def test_强制字符切分超长句(self):
        """超长无标点句子强制按字符切分"""
        chunker = ContentChunker(max_chars_per_chunk=10)
        paragraph = "ABCDEFGHIJ" * 5  # 50 字符，无标点
        result = chunker._split_long_paragraph(0, paragraph)
        assert len(result) == 5
        for r in result:
            assert len(r["content"]) <= 10


class TestContentChunkerMerge:
    """测试 ContentChunker.merge() 方法"""

    def test_合并还原原始顺序(self):
        """merge 应按 index 排序后合并"""
        chunker = ContentChunker()
        chunks = [
            TextChunk(index=2, content="第三部分", paragraph_indices=[4, 5]),
            TextChunk(index=0, content="第一部分", paragraph_indices=[0, 1]),
            TextChunk(index=1, content="第二部分", paragraph_indices=[2, 3]),
        ]
        merged = ContentChunker.merge(chunks)
        assert merged == "第一部分\n\n第二部分\n\n第三部分"

    def test_空列表合并(self):
        """空列表应返回空字符串"""
        assert ContentChunker.merge([]) == ""

    def test_单个chunk合并(self):
        """单个 chunk 应直接返回其内容"""
        chunk = TextChunk(index=0, content="只有一段", paragraph_indices=[0])
        assert ContentChunker.merge([chunk]) == "只有一段"


# ==================== PartialTranslationAssembler ====================

class TestPartialTranslationAssemblerAssemble:
    """测试 PartialTranslationAssembler.assemble() 方法"""

    def test_全部翻译完成(self):
        """所有 chunk 都有翻译时应全部使用译文"""
        chunks = [
            TextChunk(index=0, content="原文一", paragraph_indices=[0]),
            TextChunk(index=1, content="原文二", paragraph_indices=[1]),
        ]
        translated_map = {0: "译文一", 1: "译文二"}
        result = PartialTranslationAssembler.assemble(chunks, translated_map)
        assert result == "译文一\n\n译文二"

    def test_部分翻译混合组装(self):
        """部分 chunk 翻译时应混合使用译文和原文"""
        chunks = [
            TextChunk(index=0, content="原文一", paragraph_indices=[0]),
            TextChunk(index=1, content="原文二", paragraph_indices=[1]),
            TextChunk(index=2, content="原文三", paragraph_indices=[2]),
        ]
        translated_map = {0: "译文一", 2: "译文三"}
        result = PartialTranslationAssembler.assemble(chunks, translated_map)
        assert result == "译文一\n\n原文二\n\n译文三"

    def test_空翻译映射全部保留原文(self):
        """空翻译映射应全部保留原文"""
        chunks = [
            TextChunk(index=0, content="原文一", paragraph_indices=[0]),
            TextChunk(index=1, content="原文二", paragraph_indices=[1]),
        ]
        result = PartialTranslationAssembler.assemble(chunks, {})
        assert result == "原文一\n\n原文二"

    def test_翻译值为空字符串视为未翻译(self):
        """翻译值为空字符串时应视为未翻译，保留原文"""
        chunks = [
            TextChunk(index=0, content="原文一", paragraph_indices=[0]),
        ]
        translated_map = {0: ""}
        result = PartialTranslationAssembler.assemble(chunks, translated_map)
        assert result == "原文一"


class TestPartialTranslationAssemblerHasPartial:
    """测试 PartialTranslationAssembler.has_partial_translation() 方法"""

    def test_有翻译返回True(self):
        assert PartialTranslationAssembler.has_partial_translation({0: "译文"}) is True

    def test_空字典返回False(self):
        assert PartialTranslationAssembler.has_partial_translation({}) is False


class TestPartialTranslationAssemblerProgress:
    """测试 PartialTranslationAssembler.progress() 方法"""

    def test_进度返回正确(self):
        completed, total = PartialTranslationAssembler.progress({0: "x", 1: "y"}, 5)
        assert completed == 2
        assert total == 5

    def test_空进度(self):
        completed, total = PartialTranslationAssembler.progress({}, 3)
        assert completed == 0
        assert total == 3

    def test_全部完成(self):
        completed, total = PartialTranslationAssembler.progress({0: "a", 1: "b", 2: "c"}, 3)
        assert completed == 3
        assert total == 3


# ==================== LLMTranslator ====================

class TestLLMTranslatorParseResponse:
    """测试 LLMTranslator._parse_response() 方法"""

    def _make_translator(self):
        """创建 LLMTranslator 实例（不依赖真实 llm_service）"""
        llm_service = MagicMock()
        return LLMTranslator(llm_service=llm_service)

    def test_标准格式解析(self):
        """标准 [dictionary]...[result]... 格式应正确解析"""
        translator = self._make_translator()
        response = """[dictionary]
Alice -> 爱丽丝
Bob -> 鲍勃
[result]
爱丽丝走向了鲍勃。"""
        translated_text, entries = translator._parse_response(response)
        assert "爱丽丝走向了鲍勃。" in translated_text
        assert entries["Alice"] == "爱丽丝"
        assert entries["Bob"] == "鲍勃"

    def test_多种分隔符(self):
        """支持 -> 和 : 两种分隔符"""
        translator = self._make_translator()
        response = """[dictionary]
Alice -> 爱丽丝
Bob: 鲍勃
[result]
译文内容"""
        translated_text, entries = translator._parse_response(response)
        assert entries["Alice"] == "爱丽丝"
        assert entries["Bob"] == "鲍勃"

    def test_无dictionary部分(self):
        """无 [dictionary] 段时应返回整个响应作为译文"""
        translator = self._make_translator()
        response = "这是一段没有词典格式的直接译文。"
        translated_text, entries = translator._parse_response(response)
        assert translated_text == "这是一段没有词典格式的直接译文。"
        assert entries == {}

    def test_词典中包含破折号的行被跳过(self):
        """以破折号开头的词典行应被跳过"""
        translator = self._make_translator()
        response = """[dictionary]
Alice -> 爱丽丝
--- separator ---
Bob -> 鲍勃
[result]
译文"""
        translated_text, entries = translator._parse_response(response)
        assert entries["Alice"] == "爱丽丝"
        assert entries["Bob"] == "鲍勃"
        # 破折号行不应出现在词典中
        assert "--- separator ---" not in entries

    def test_空响应(self):
        """空响应应返回空译文和空词典"""
        translator = self._make_translator()
        translated_text, entries = translator._parse_response("")
        assert translated_text == ""
        assert entries == {}

    def test_等号分隔符(self):
        """支持 = 分隔符"""
        translator = self._make_translator()
        response = """[dictionary]
Alice = 爱丽丝
[result]
译文"""
        translated_text, entries = translator._parse_response(response)
        assert entries["Alice"] == "爱丽丝"

    def test_词典条目值含分隔符(self):
        """分隔符只应 split 一次，保留值中的分隔符"""
        translator = self._make_translator()
        response = """[dictionary]
Note -> See: reference
[result]
译文"""
        translated_text, entries = translator._parse_response(response)
        # 使用 -> 分隔，只 split 一次，值中保留 :
        assert entries["Note"] == "See: reference"
        assert "reference" not in entries

    def test_忽略空原始词和空译文(self):
        """空原始词或空译文不应加入词典"""
        translator = self._make_translator()
        response = """[dictionary]
Alice -> 
-> 爱丽丝
Bob -> 鲍勃
[result]
译文"""
        translated_text, entries = translator._parse_response(response)
        assert len(entries) == 1
        assert entries["Bob"] == "鲍勃"

    def test_忽略只有分隔符的行(self):
        """只有分隔符的行不应产生条目"""
        translator = self._make_translator()
        response = """[dictionary]
->
Alice -> 爱丽丝
[result]
译文"""
        translated_text, entries = translator._parse_response(response)
        assert len(entries) == 1
        assert entries["Alice"] == "爱丽丝"


class TestLLMTranslatorRetry:
    """测试 LLMTranslator 的重试机制"""

    async def test_重试成功(self):
        """首次失败后重试成功应最终返回正确结果"""
        llm_service = MagicMock()
        call_count = 0
        responses = [
            ExternalServiceException("首次调用失败"),
            "ok",
        ]

        async def fake_call(**kwargs):
            nonlocal call_count
            val = responses[call_count]
            call_count += 1
            if isinstance(val, Exception):
                raise val
            return val

        llm_service.call_llm = AsyncMock(side_effect=fake_call)
        translator = LLMTranslator(llm_service=llm_service, retry_count=3)

        with patch.object(translator, "_parse_response", return_value=("译文", {})):
            result_text, result_dict = await translator.translate("测试文本")

        assert result_text == "译文"
        assert call_count == 2

    async def test_全部重试耗尽后抛异常(self):
        """全部重试耗尽后应抛出异常"""
        llm_service = MagicMock()
        llm_service.call_llm = AsyncMock(
            side_effect=ExternalServiceException("始终失败")
        )
        translator = LLMTranslator(llm_service=llm_service, retry_count=2)

        with pytest.raises(ExternalServiceException):
            await translator.translate("测试文本")

    async def test_非ExternalServiceException最终包装后抛出(self):
        """非 ExternalServiceException 在重试耗尽后应包装为 ExternalServiceException"""
        llm_service = MagicMock()
        llm_service.call_llm = AsyncMock(
            side_effect=ValueError("参数错误")
        )
        translator = LLMTranslator(llm_service=llm_service, retry_count=1)

        with pytest.raises(ExternalServiceException, match="LLM 翻译失败"):
            await translator.translate("测试文本")

    async def test_指数退避延迟(self):
        """重试应有指数退避延迟"""
        llm_service = MagicMock()
        call_count = 0

        async def fake_call(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise ExternalServiceException("fail")
            return "ok"

        llm_service.call_llm = AsyncMock(side_effect=fake_call)
        translator = LLMTranslator(llm_service=llm_service, retry_count=3)

        with patch.object(translator, "_parse_response", return_value=("译文", {})):
            with patch("app.services.translator.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result_text, result_dict = await translator.translate("文本")

        # 第一次重试 sleep(2^0=1), 第二次 sleep(2^1=2)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    async def test_成功时不重试(self):
        """首次调用成功时不应有任何延迟"""
        llm_service = MagicMock()
        llm_service.call_llm = AsyncMock(return_value="ok response")
        translator = LLMTranslator(llm_service=llm_service, retry_count=3)

        with patch.object(translator, "_parse_response", return_value=("译文", {})):
            with patch("app.services.translator.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result_text, result_dict = await translator.translate("文本")

        assert mock_sleep.call_count == 0
        assert result_text == "译文"


# ==================== GoogleTranslator ====================

class TestGoogleTranslator:
    """测试 GoogleTranslator"""

    async def test_成功翻译(self):
        """成功调用 Google 翻译 API 应返回译文"""
        translator = GoogleTranslator()

        mock_json_data = [
            [["译文片段一", "原文片段一"], ["译文片段二", "原文片段二"]]
        ]

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="error text")
        mock_response.json = AsyncMock(return_value=mock_json_data)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch("aiohttp.ClientTimeout", return_value=MagicMock()):
                result_text, result_dict = await translator.translate("Hello", target_language="zh-CN")

        assert result_text == "译文片段一译文片段二"
        assert result_dict == {}

    async def test_非200状态码抛异常(self):
        """Google API 返回非 200 状态码应抛出 ExternalServiceException"""
        translator = GoogleTranslator()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.text = AsyncMock(return_value="Internal Server Error")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch("aiohttp.ClientTimeout", return_value=MagicMock()):
                with pytest.raises(ExternalServiceException, match="HTTP 500"):
                    await translator.translate("Hello", target_language="zh-CN")

    async def test_超时处理(self):
        """网络超时应抛出 ExternalServiceException"""
        translator = GoogleTranslator()

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=asyncio.TimeoutError("timeout"))
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch("aiohttp.ClientTimeout", return_value=MagicMock()):
                with pytest.raises(ExternalServiceException, match="Google 翻译服务暂不可用"):
                    await translator.translate("Hello", target_language="zh-CN")

    async def test_空响应数据处理(self):
        """Google API 返回空数据列表时应返回空字符串"""
        translator = GoogleTranslator()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[[]])
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch("aiohttp.ClientTimeout", return_value=MagicMock()):
                result_text, result_dict = await translator.translate("Hello")

        assert result_text == ""
        assert result_dict == {}

    async def test_异常响应格式处理(self):
        """Google API 返回非列表响应时不应崩溃"""
        translator = GoogleTranslator()

        # 字符串的 data[0] 返回单个字符，isinstance(char, list) 为 False
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value="unexpected")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("aiohttp.ClientSession", return_value=mock_session):
            with patch("aiohttp.ClientTimeout", return_value=MagicMock()):
                result_text, result_dict = await translator.translate("Hello")

        # 遍历字符串字符，没有一个是 list，translated_parts 为空
        assert result_text == ""
        assert result_dict == {}


# ==================== TranslationJob ====================

class TestTranslationJobStateTransitions:
    """测试 TranslationJob 状态流转"""

    def test_mark_started_状态变为running(self):
        job = TranslationJob()
        assert job.status == TranslationStatus.PENDING
        job.mark_started()
        assert job.status == TranslationStatus.RUNNING

    def test_mark_completed_设置译文和状态(self):
        job = TranslationJob()
        job.mark_started()
        job.mark_completed("完整译文内容")
        assert job.status == TranslationStatus.COMPLETED
        assert job.translated_text == "完整译文内容"

    def test_mark_failed_设置错误信息(self):
        job = TranslationJob()
        job.mark_started()
        job.mark_failed("翻译服务超时")
        assert job.status == TranslationStatus.FAILED
        assert job.error_msg == "翻译服务超时"


class TestTranslationJobProgress:
    """测试 TranslationJob 进度计算"""

    def test_progress_零chunk返回0(self):
        """total_chunks 为 0 时进度应为 0"""
        job = TranslationJob(total_chunks=0, completed_chunks=0)
        assert job.progress == 0.0

    def test_progress_部分完成(self):
        """部分完成时进度百分比正确"""
        job = TranslationJob(total_chunks=10, completed_chunks=3)
        assert job.progress == 30.0

    def test_progress_全部完成(self):
        """全部完成时进度应为 100"""
        job = TranslationJob(total_chunks=5, completed_chunks=5)
        assert job.progress == 100.0

    def test_progress_小数精度(self):
        """进度应保留两位小数"""
        job = TranslationJob(total_chunks=3, completed_chunks=1)
        assert job.progress == pytest.approx(33.33, abs=0.01)


class TestTranslationJobIsDone:
    """测试 TranslationJob.is_done 属性"""

    def test_pending未完成(self):
        job = TranslationJob(status=TranslationStatus.PENDING)
        assert job.is_done is False

    def test_running未完成(self):
        job = TranslationJob(status=TranslationStatus.RUNNING)
        assert job.is_done is False

    def test_completed已完成(self):
        job = TranslationJob(status=TranslationStatus.COMPLETED)
        assert job.is_done is True

    def test_failed已完成(self):
        job = TranslationJob(status=TranslationStatus.FAILED)
        assert job.is_done is True

    def test_partial未完成(self):
        """PARTIAL 状态不属于 done"""
        job = TranslationJob(status=TranslationStatus.PARTIAL)
        assert job.is_done is False


class TestTranslationJobUpdateProgress:
    """测试 TranslationJob.update_progress() 自动状态变更"""

    def test_全部成功自动标记completed(self):
        job = TranslationJob(total_chunks=5)
        job.update_progress(completed=5, failed=0)
        assert job.status == TranslationStatus.COMPLETED

    def test_全部失败自动标记failed(self):
        job = TranslationJob(total_chunks=5)
        job.update_progress(completed=0, failed=5)
        assert job.status == TranslationStatus.FAILED

    def test_部分成功部分失败自动标记partial(self):
        job = TranslationJob(total_chunks=5)
        job.update_progress(completed=3, failed=2)
        assert job.status == TranslationStatus.PARTIAL

    def test_进度未满不改变状态(self):
        """进度未满时不应自动改变状态"""
        job = TranslationJob(total_chunks=5, status=TranslationStatus.RUNNING)
        job.update_progress(completed=2, failed=0)
        assert job.status == TranslationStatus.RUNNING

    def test_刚好等于total_chunks(self):
        """completed + failed 刚好等于 total_chunks"""
        job = TranslationJob(total_chunks=5)
        job.update_progress(completed=4, failed=1)
        assert job.status == TranslationStatus.PARTIAL

    def test_超过total_chunks也触发状态变更(self):
        """completed + failed 超过 total_chunks 也应触发"""
        job = TranslationJob(total_chunks=3)
        job.update_progress(completed=5, failed=0)
        assert job.status == TranslationStatus.COMPLETED


# ==================== TranslationChunk ====================

class TestTranslationChunk:
    """测试 TranslationChunk 实体"""

    def test_mark_translated_设置译文和状态(self):
        chunk = TranslationChunk(index=0, original="原文")
        chunk.mark_translated("译文内容")
        assert chunk.translated == "译文内容"
        assert chunk.status == TranslationStatus.COMPLETED
        assert chunk.updated_at > chunk.created_at

    def test_mark_failed_设置错误信息和状态(self):
        chunk = TranslationChunk(index=0, original="原文")
        chunk.mark_failed("网络超时")
        assert chunk.status == TranslationStatus.FAILED
        assert chunk.error_msg == "网络超时"
        assert chunk.updated_at > chunk.created_at

    def test_初始状态为pending(self):
        chunk = TranslationChunk(index=0, original="原文")
        assert chunk.status == TranslationStatus.PENDING
        assert chunk.translated == ""
        assert chunk.error_msg is None

    def test_mark_translated覆盖之前译文(self):
        """mark_translated 应能覆盖之前的译文"""
        chunk = TranslationChunk(index=0, original="原文")
        chunk.mark_translated("初版译文")
        chunk.mark_translated("修订译文")
        assert chunk.translated == "修订译文"


# ==================== TranslationDictionary ====================

class TestTranslationDictionaryAddEntry:
    """测试 TranslationDictionary.add_entry()"""

    def test_正常添加条目(self):
        d = TranslationDictionary(max_entries=5)
        assert d.add_entry("Alice", "爱丽丝") is True
        assert d.entries["Alice"] == "爱丽丝"

    def test_重复更新条目(self):
        """已存在的条目应能更新，不受 max_entries 限制"""
        d = TranslationDictionary(max_entries=2)
        d.add_entry("Alice", "爱丽丝")
        d.add_entry("Bob", "鲍勃")
        # 已满，但更新已有条目应成功
        assert d.add_entry("Alice", "新译文") is True
        assert d.entries["Alice"] == "新译文"

    def test_超过上限返回False(self):
        """超过 max_entries 时添加新条目应返回 False"""
        d = TranslationDictionary(max_entries=2)
        d.add_entry("Alice", "爱丽丝")
        d.add_entry("Bob", "鲍勃")
        assert d.add_entry("Charlie", "查理") is False
        assert "Charlie" not in d.entries

    def test_添加条目更新时间戳(self):
        """添加条目后 updated_at 应更新"""
        d = TranslationDictionary()
        old_updated = d.updated_at
        d.add_entry("Alice", "爱丽丝")
        assert d.updated_at >= old_updated


class TestTranslationDictionaryMergeEntries:
    """测试 TranslationDictionary.merge_entries()"""

    def test_合并多个条目(self):
        d = TranslationDictionary(max_entries=10)
        new_entries = {"Alice": "爱丽丝", "Bob": "鲍勃", "Charlie": "查理"}
        added = d.merge_entries(new_entries)
        assert added == 3
        assert len(d.entries) == 3

    def test_合并时部分因上限被拒绝(self):
        d = TranslationDictionary(max_entries=2)
        new_entries = {"Alice": "爱丽丝", "Bob": "鲍勃", "Charlie": "查理"}
        added = d.merge_entries(new_entries)
        assert added == 2
        assert len(d.entries) == 2
        assert "Alice" in d.entries
        assert "Bob" in d.entries
        assert "Charlie" not in d.entries

    def test_合并已有条目不计入新增(self):
        """合并时更新已有条目不应计入新增数量"""
        d = TranslationDictionary(max_entries=5)
        d.add_entry("Alice", "爱丽丝")
        new_entries = {"Alice": "新爱丽丝", "Bob": "鲍勃"}
        added = d.merge_entries(new_entries)
        # Bob 是新的，Alice 是更新的
        assert added == 2
        assert d.entries["Alice"] == "新爱丽丝"
        assert d.entries["Bob"] == "鲍勃"


class TestTranslationDictionaryToPromptText:
    """测试 TranslationDictionary.to_prompt_text()"""

    def test_空词典返回空字符串(self):
        d = TranslationDictionary()
        assert d.to_prompt_text() == ""

    def test_格式正确(self):
        """to_prompt_text 应返回 'original -> translated' 格式"""
        d = TranslationDictionary()
        d.add_entry("Alice", "爱丽丝")
        d.add_entry("Bob", "鲍勃")
        text = d.to_prompt_text()
        lines = text.strip().split("\n")
        assert len(lines) == 2
        assert "Alice -> 爱丽丝" in lines
        assert "Bob -> 鲍勃" in lines

    def test_单个条目(self):
        d = TranslationDictionary()
        d.add_entry("Test", "测试")
        text = d.to_prompt_text()
        assert text == "Test -> 测试"


# ==================== TextChunk ====================

class TestTextChunk:
    """测试 TextChunk 数据类"""

    def test_length属性(self):
        chunk = TextChunk(index=0, content="Hello World")
        assert chunk.length == 11

    def test_length为空内容(self):
        chunk = TextChunk(index=0, content="")
        assert chunk.length == 0

    def test_paragraph_indices默认为空列表(self):
        chunk = TextChunk(index=0, content="text")
        assert chunk.paragraph_indices == []

    def test_paragraph_indices可自定义(self):
        chunk = TextChunk(index=0, content="text", paragraph_indices=[1, 2, 3])
        assert chunk.paragraph_indices == [1, 2, 3]
