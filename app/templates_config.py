from fastapi.templating import Jinja2Templates
import markdown as md_lib


def markdown_filter(text: str) -> str:
    """Jinja2 过滤器：将 Markdown 转换为 HTML"""
    if not text:
        return ""
    return md_lib.markdown(text, extensions=['fenced_code', 'tables'])


# 模板配置
templates = Jinja2Templates(directory="app/templates")
templates.env.filters['markdown'] = markdown_filter
