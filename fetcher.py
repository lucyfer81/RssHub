import html
import logging
import random
import time
from typing import Optional, Dict, Any
import httpx
import feedparser
import trafilatura

logger = logging.getLogger(__name__)


def _iterative_unescape(text: str, max_iterations: int = 5) -> str:
    """迭代解码 HTML 实体，直到内容稳定（处理双重编码）

    Args:
        text: 要解码的文本
        max_iterations: 最大迭代次数，防止无限循环

    Returns:
        解码后的文本
    """
    if not text:
        return text

    result = text
    for _ in range(max_iterations):
        unescaped = html.unescape(result)
        if unescaped == result:
            # 内容稳定，不再变化
            break
        result = unescaped

    return result


def fetch_full_text(url: str, timeout: int = 30) -> Optional[str]:
    """抓取网页正文并转换为Markdown格式，带指数退避重试

    返回值:
    - 成功时返回Markdown格式的文章内容
    - 403错误时返回None，表示需要使用RSS的summary作为回退
    - 其他错误时返回空字符串，表示完全失败
    """
    max_retries = 5
    base_delay = 2  # 基础延迟2秒

    for attempt in range(max_retries):
        try:
            # 每次重试前添加指数退避延迟和随机抖动
            if attempt > 0:
                jitter = random.uniform(0.5, 1.5)
                delay = base_delay * (2 ** (attempt - 1)) * jitter
                logger.info(f"  重试 {attempt + 1}/{max_retries}，等待{delay:.1f}秒...")
                time.sleep(delay)

            # 使用更真实的User-Agent
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            }

            # trust_env=True 会自动从环境变量读取代理设置
            with httpx.Client(timeout=timeout, trust_env=True, follow_redirects=True) as client:
                response = client.get(url, headers=headers)

                # 处理429速率限制
                if response.status_code == 429:
                    logger.warning(f"  遇到429速率限制")
                    if attempt < max_retries - 1:
                        continue
                    else:
                        logger.error(f"  达到最大重试次数，跳过")
                        return None

                # 处理403错误 - 访问被拒绝（不重试，直接使用RSS摘要）
                if response.status_code == 403:
                    logger.debug(f"  遇到403错误，访问被拒绝，将使用RSS摘要")
                    # 返回None，表示403错误，应该使用RSS summary作为回退
                    return None

                response.raise_for_status()
                downloaded = response.text

            if not downloaded:
                return ""

            # 使用trafilatura提取正文并转为Markdown
            content = trafilatura.extract(
                downloaded,
                output_format="markdown",
                include_comments=False,
                include_tables=True
            )
            return content

        except httpx.HTTPStatusError as e:
            # 处理403错误（不重试，直接使用RSS摘要）
            if e.response.status_code == 403:
                logger.debug(f"  遇到403错误，将使用RSS摘要")
                # 返回None，表示403错误，应该使用RSS summary作为回退
                return None

            # 处理429速率限制（继续重试）
            if e.response.status_code == 429 and attempt < max_retries - 1:
                continue

            logger.warning(f"  抓取网页失败 {url}: {e}")
            return ""
        except Exception as e:
            if attempt == max_retries - 1:
                logger.warning(f"  抓取网页失败 {url}: {e}")
                return ""

    return ""


def parse_feed(source_url: str, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """解析RSS feed"""
    try:
        # 使用httpx获取feed内容，设置User-Agent
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; RSS-Hub/0.1.0; +https://github.com/rss-hub)"
        }

        # trust_env=True 会自动从环境变量读取代理设置
        with httpx.Client(timeout=timeout, trust_env=True) as client:
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
    method: 'rss_content', 'rss_summary', 'rss_summary_403', 'fetched', 'failed'

    说明:
    - 'rss_content': 直接使用RSS中的content字段
    - 'rss_summary': 使用RSS中的summary字段
    - 'rss_summary_403': 403错误回退，使用RSS summary并保存URL
    - 'fetched': 成功抓取全文
    - 'failed': 完全失败，无内容
    """
    url = getattr(entry, 'link', '')

    # 1. 优先使用RSS中的content
    if hasattr(entry, 'content') and entry.content:
        content = entry.content[0].value
        # 使用迭代解码 HTML 实体（处理双重编码）
        decoded_content = _iterative_unescape(content)
        return decoded_content, 'rss_content'

    # 2. 其次使用summary，并尝试抓取全文
    if hasattr(entry, 'summary') and entry.summary:
        # 使用迭代解码 HTML 实体（处理双重编码）
        summary = _iterative_unescape(entry.summary)

        # 尝试抓取全文作为补充
        if url:
            full_text = fetch_full_text(url)
            if full_text:
                # 成功抓取到全文
                return full_text, 'fetched'
            elif full_text is None:
                # 403错误：使用summary作为回退，并保存URL
                # 在summary后面添加原文链接
                fallback_content = f"{summary}\n\n---\n**原文链接**: {url}"
                return fallback_content, 'rss_summary_403'

        # 没有链接或抓取失败，直接使用summary
        return summary, 'rss_summary'

    # 3. 如果只有链接，尝试抓取
    if url:
        full_text = fetch_full_text(url)
        if full_text:
            return full_text, 'fetched'
        elif full_text is None:
            # 403错误：但没有summary，只保存URL
            fallback_content = f"**无法获取内容，访问被拒绝 (403)**\n\n**原文链接**: {url}"
            return fallback_content, 'rss_summary_403'

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
