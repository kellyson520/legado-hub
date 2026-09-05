"""
URL 处理工具模块

功能：
- URL 模板填充（{{key}} 变量、{{$.field}} JSONPath）
- 相对路径转绝对路径
- URL 编码 / 解码
- QueryMap 格式解析（Legado 特有）
- URL 合法性校验
"""

import re
import json
from urllib.parse import (
    urljoin,
    quote,
    unquote,
    urlparse,
    parse_qs,
    urlencode,
    urlunparse,
)
from typing import Any, Dict, List, Optional, Tuple

from .jsonpath_ext import JsonPathExt


class UrlUtils:
    """URL 处理工具集"""

    # 默认搜索变量映射
    SEARCH_VAR_ALIASES = {
        'key': 'keyword',
        'searchKey': 'keyword',
        'searchkey': 'keyword',
        'search': 'keyword',
        'wd': 'keyword',
        'query': 'keyword',
        'q': 'keyword',
        'k': 'keyword',
        'keyword': 'keyword',
    }

    @classmethod
    def fill_template(
        cls,
        template: str,
        variables: Dict[str, Any] = None,
        data: Any = None,
        encode: bool = False,
    ) -> str:
        """
        填充 URL 模板

        支持:
        - {{key}}                    变量替换
        - {{$.field}}                JSONPath 变量
        - {{$.field.sub}}            嵌套字段
        - {{page - 1}}               简单算术
        - {{key|urlEncode}}          管道编码

        Args:
            template: URL 模板字符串
            variables: 变量字典
            data: JSON 数据（用于 {{$.xxx}} 形式）
            encode: 是否对变量值进行 URL 编码

        Returns:
            填充后的 URL
        """
        if not template:
            return ''

        variables = variables or {}

        def replace(match):
            expr = match.group(1).strip()

            # 处理管道（| 分隔的函数）
            pipes = []
            if '|' in expr:
                parts = expr.split('|')
                expr = parts[0].strip()
                pipes = [p.strip() for p in parts[1:]]

            value = cls._resolve_variable(expr, variables, data)

            # 应用管道
            for pipe in pipes:
                value = cls._apply_pipe(value, pipe)

            # URL 编码
            if encode and value is not None:
                try:
                    value = quote(str(value))
                except Exception:
                    pass

            return str(value) if value is not None else ''

        return re.sub(r'\{\{(.+?)\}\}', replace, template)

    @classmethod
    def _resolve_variable(
        cls,
        expr: str,
        variables: Dict[str, Any],
        data: Any,
    ) -> Any:
        """解析单个变量表达式"""
        expr = expr.strip()

        # JSONPath 形式
        if expr.startswith('$'):
            result = JsonPathExt.query(data or {}, expr)
            if result is not None:
                return result
            return ''

        # 直接变量名
        if expr in variables:
            return variables[expr]

        # 别名查找（搜索相关）
        if expr in cls.SEARCH_VAR_ALIASES:
            alias_key = cls.SEARCH_VAR_ALIASES[expr]
            if alias_key in variables:
                return variables[alias_key]
            if alias_key != expr:
                # 反向查
                for k, v in cls.SEARCH_VAR_ALIASES.items():
                    if v == expr and k in variables:
                        return variables[k]

        # 简单算术表达式：page-1, page+1, start+20
        result = cls._eval_simple_math(expr, variables)
        if result is not None:
            return result

        # 没找到，返回空字符串
        return ''

    @staticmethod
    def _eval_simple_math(expr: str, variables: Dict[str, Any]) -> Optional[int]:
        """
        计算简单的算术表达式（Legado 常见模式）

        支持:
        - page-1 / page+1 / page-10
        - start+20
        """
        # 匹配：变量名 + 运算符 + 数字
        m = re.match(r'^(\w+)\s*([+\-])\s*(\d+)$', expr)
        if not m:
            return None

        var_name = m.group(1)
        op = m.group(2)
        num = int(m.group(3))

        if var_name not in variables:
            return None

        try:
            val = int(variables[var_name])
            if op == '+':
                return val + num
            else:
                return val - num
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _apply_pipe(value: Any, pipe: str) -> Any:
        """应用管道函数"""
        if value is None:
            return value

        pipe_lower = pipe.lower()

        if pipe_lower in ('urlencode', 'encode'):
            try:
                return quote(str(value))
            except Exception:
                return value

        if pipe_lower in ('urldecode', 'decode'):
            try:
                return unquote(str(value))
            except Exception:
                return value

        if pipe_lower == 'trim':
            return str(value).strip()

        if pipe_lower == 'upper':
            return str(value).upper()

        if pipe_lower == 'lower':
            return str(value).lower()

        if pipe_lower == 'int':
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0

        if pipe_lower == 'string' or pipe_lower == 'str':
            return str(value)

        return value

    @staticmethod
    def resolve_relative(url: str, base_url: str) -> str:
        """
        相对 URL 转绝对 URL

        Args:
            url: 可能是相对路径的 URL
            base_url: 基础 URL

        Returns:
            绝对 URL
        """
        if not url:
            return ''
        if url.startswith(('http://', 'https://', 'data:', 'ftp://')):
            return url

        try:
            if not base_url:
                return url
            # 确保 base_url 以 / 结尾（如果是路径形式）
            if not base_url.endswith('/') and '.' not in base_url.rsplit('/', 1)[-1]:
                base_url = base_url + '/'
            return urljoin(base_url, url)
        except Exception:
            return url

    @staticmethod
    def parse_search_url(url_template: str) -> Tuple[str, str, Optional[str]]:
        """
        解析 Legado 搜索 URL 格式

        Legado 格式:
        - 简单 GET:  /search?q={{key}}
        - POST:      /api/search::POST
        - POST+body: /api/search::POST\n{"keyword":"{{key}}"}
        - 带配置:    /search,{"charset": "gbk", "method": "POST", "body": "..."}

        Returns:
            (url, method, body_template)
        """
        if not url_template:
            return '', 'GET', None

        method = 'GET'
        body = None
        url = url_template.strip()

        # 处理逗号分隔的配置（Legado 格式）
        # 形如: /search,{"charset": "gbk", "method": "POST", "body": "..."}
        if ',' in url:
            # 尝试找逗号后的 JSON 配置
            comma_idx = url.find(',')
            after_comma = url[comma_idx + 1:].strip()
            if after_comma.startswith('{'):
                url = url[:comma_idx].strip()
                try:
                    config = json.loads(after_comma)
                    if isinstance(config, dict):
                        if config.get('method', '').upper() == 'POST':
                            method = 'POST'
                        if config.get('body'):
                            body = config['body']
                except (json.JSONDecodeError, TypeError):
                    pass

        # 处理 ::POST 格式
        if '::POST' in url:
            parts = url.split('::POST', 1)
            url = parts[0].strip()
            method = 'POST'
            if parts[1].strip():
                body = parts[1].strip()

        # 处理换行分隔的 body
        if '\n' in url:
            lines = url.split('\n', 1)
            url = lines[0].strip()
            if method == 'POST' and lines[1].strip():
                body = lines[1].strip()

        return url, method, body

    @staticmethod
    def parse_url_config(url_template: str) -> Dict[str, Any]:
        """
        从 URL 模板中解析配置（charset/method/body/headers 等）

        返回配置字典
        """
        config = {}
        if not url_template:
            return config

        url = url_template.strip()

        # 解析逗号后的 JSON 配置
        if ',' in url:
            comma_idx = url.find(',')
            after_comma = url[comma_idx + 1:].strip()
            if after_comma.startswith('{'):
                try:
                    json_config = json.loads(after_comma)
                    if isinstance(json_config, dict):
                        config.update(json_config)
                except (json.JSONDecodeError, TypeError):
                    pass

        # 解析 ::POST
        if '::POST' in url_template:
            config['method'] = 'POST'

        return config

    @staticmethod
    def parse_headers(header_data: Any) -> Dict[str, str]:
        """
        解析 Legado 书源的 header 字段

        header 可以是:
        - JSON 字符串
        - dict 对象
        - 多行 key:value 格式

        Returns:
            请求头字典
        """
        headers = {}

        if not header_data:
            return headers

        if isinstance(header_data, dict):
            return {str(k): str(v) for k, v in header_data.items()}

        if isinstance(header_data, str):
            header_str = header_data.strip()
            if not header_str:
                return headers

            # 尝试 JSON 解析
            try:
                data = json.loads(header_str)
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
            except (json.JSONDecodeError, TypeError):
                pass

            # 尝试多行 key:value 格式
            lines = header_str.strip().split('\n')
            for line in lines:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                # 只按第一个冒号分割
                idx = line.index(':')
                key = line[:idx].strip()
                value = line[idx + 1:].strip()
                if key:
                    headers[key] = value

        return headers

    @staticmethod
    def is_valid_url(url: str) -> bool:
        """检查是否为有效 URL"""
        if not url or not isinstance(url, str):
            return False
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except Exception:
            return False

    @staticmethod
    def add_query_params(url: str, params: Dict[str, Any]) -> str:
        """添加查询参数到 URL"""
        if not url:
            return url

        try:
            parsed = urlparse(url)
            query = parse_qs(parsed.query, keep_blank_values=True)

            # 合并参数
            for k, v in params.items():
                if isinstance(v, list):
                    query[k] = [str(x) for x in v]
                else:
                    query[k] = [str(v)]

            new_query = urlencode(query, doseq=True)
            return urlunparse(parsed._replace(query=new_query))
        except Exception:
            return url

    @staticmethod
    def get_base_url(book_source_url: str) -> str:
        """
        从书源 URL 提取基础 URL

        书源 URL 可能带有路径和 # 锚点，需要提取域名部分
        """
        if not book_source_url:
            return ''

        # 去掉 # 后面的内容（Legado 常用于分类）
        url = book_source_url.split('#')[0]

        try:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return url
