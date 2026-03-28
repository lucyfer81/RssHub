from fastapi.templating import Jinja2Templates
import markdown as md_lib
import json as json_lib


def markdown_filter(text: str) -> str:
    """Jinja2 过滤器：将 Markdown 转换为 HTML"""
    if not text:
        return ""
    return md_lib.markdown(text, extensions=['fenced_code', 'tables'])


def from_json_filter(text: str):
    """Jinja2 过滤器：将 JSON 字符串解析为 Python 对象"""
    if not text:
        return []
    try:
        return json_lib.loads(text)
    except (json_lib.JSONDecodeError, TypeError):
        return []


# 模板配置
templates = Jinja2Templates(directory="app/templates")
templates.env.filters['markdown'] = markdown_filter
templates.env.filters['from_json'] = from_json_filter
