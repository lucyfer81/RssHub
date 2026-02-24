import logging
from typing import Optional, Dict, Any
import httpx
import feedparser
import trafilatura

logger = logging.getLogger(__name__)


def fetch_full_text(url: str, timeout: int = 10) -> Optional[str]:
    """抓取网页正文并转换为Markdown格式"""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None

        # 使用trafilatura提取正文并转为Markdown
        content = trafilatura.extract(
            downloaded,
            output_format="markdown",
            include_comments=False,
            include_tables=True
        )
        return content
    except Exception as e:
        logger.warning(f"抓取网页失败 {url}: {e}")
        return None


def parse_feed(source_url: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
    """解析RSS feed"""
    try:
        # 使用httpx获取feed内容，设置User-Agent
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; RSS-Hub/0.1.0; +https://github.com/rss-hub)"
        }

        with httpx.Client(timeout=timeout) as client:
            response = client.get(source_url, headers=headers)
            response.raise_for_status()
            feed_content = response.content

        feed = feedparser.parse(feed_content)

        if feed.bozo and feed.bozo_exception:
            logger.warning(f"RSS解析警告 {source_url}: {feed.bozo_exception}")

        return feed

    except Exception as e:
        logger.error(f"抓取RSS失败 {source_url}: {e}")
        return None


def extract_article_content(entry: Dict[str, Any], feed_url: str) -> tuple[str, str]:
    """从RSS条目中提取或抓取文章内容

    返回: (content, method) 元组
    method: 'rss_content', 'rss_summary', 'fetched', 'failed'
    """
    # 1. 优先使用RSS中的content
    if hasattr(entry, 'content') and entry.content:
        content = entry.content[0].value
        return content, 'rss_content'

    # 2. 其次使用summary
    if hasattr(entry, 'summary') and entry.summary:
        summary = entry.summary
        # 尝试抓取全文作为补充
        if hasattr(entry, 'link') and entry.link:
            full_text = fetch_full_text(entry.link)
            if full_text:
                return full_text, 'fetched'
        return summary, 'rss_summary'

    # 3. 如果只有链接，尝试抓取
    if hasattr(entry, 'link') and entry.link:
        full_text = fetch_full_text(entry.link)
        if full_text:
            return full_text, 'fetched'

    return "", 'failed'


def fetch_entries(source_name: str, source_url: str) -> list[Dict[str, Any]]:
    """获取单个RSS源的所有文章条目"""
    feed = parse_feed(source_url)
    if not feed or not hasattr(feed, 'entries'):
        return []

    entries = []
    for entry in feed.entries:
        title = getattr(entry, 'title', '无标题')
        url = getattr(entry, 'link', '')
        published = getattr(entry, 'published', getattr(entry, 'updated', None))

        content, method = extract_article_content(entry, source_url)

        entries.append({
            'title': title,
            'url': url,
            'source': source_name,
            'content': content,
            'published_at': published,
            'fetch_method': method
        })

    return entries
