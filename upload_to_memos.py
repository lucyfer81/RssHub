#!/usr/bin/env python3
"""
将本地 RSS 数据库中的文章上传到 memos-worker（混合去重方案）

本地维护上传记录表，只上传新文章或已更新的文章。
API 层仍然有去重保护，确保幂等性。

用法:
    python upload_to_memos_v2.py [--source SOURCE_NAME] [--batch-size N] [--dry-run]

环境变量:
    MEMOS_API_URL: memos-worker 的 API 地址 (默认: https://memos.aizhi.app)
    RSS_INGEST_TOKEN: RSS Ingest API 的认证令牌
"""

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import httpx
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_API_URL = "https://memos.aizhi.app"
DEFAULT_BATCH_SIZE = 20
UPLOAD_TRACKER_DB = Path(__file__).parent / ".upload_tracker.db"


def get_rss_db_path(db_path: Path = None) -> Path:
    """获取 RSS 数据库文件路径"""
    if db_path is None:
        db_path = Path(__file__).parent / "rss.db"
    return db_path


def get_tracker_db_path() -> Path:
    """获取上传记录数据库路径"""
    return UPLOAD_TRACKER_DB


def get_api_url() -> str:
    """从环境变量获取 API URL"""
    return os.environ.get("MEMOS_API_URL", DEFAULT_API_URL)


def get_ingest_token() -> str:
    """从环境变量获取 RSS Ingest Token"""
    token = os.environ.get("RSS_INGEST_TOKEN")
    if not token:
        logger.error("未设置 RSS_INGEST_TOKEN 环境变量")
        sys.exit(1)
    return token


def init_tracker_db() -> sqlite3.Connection:
    """初始化上传记录数据库"""
    conn = sqlite3.connect(get_tracker_db_path())
    conn.row_factory = sqlite3.Row

    # 创建上传记录表
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_memos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            url TEXT NOT NULL,
            title TEXT,
            content_hash TEXT,
            memo_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, url)
        )
    """)

    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracker_source ON uploaded_memos(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracker_uploaded ON uploaded_memos(updated_at)")

    conn.commit()
    return conn


def init_rss_db(db_path: Path = None) -> sqlite3.Connection:
    """初始化 RSS 数据库连接"""
    if db_path is None:
        db_path = get_rss_db_path()

    if not db_path.exists():
        logger.error(f"数据库文件不存在: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def compute_item_hash(item: Dict[str, Any]) -> str:
    """计算文章项的哈希，包含所有可能变化的字段

    Args:
        item: memos API 格式的文章项

    Returns:
        哈希值
    """
    import hashlib
    import json

    # 使用所有可能变化的字段计算哈希
    hash_data = {
        "title": item.get("title", ""),
        "summary": item.get("summary", ""),
        "published_at": item.get("published_at", ""),
        "url": item.get("url", ""),
    }

    # 使用 JSON 确保顺序一致
    hash_str = json.dumps(hash_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(hash_str.encode('utf-8')).hexdigest()[:16]


def is_article_uploaded(
    tracker_conn: sqlite3.Connection,
    source: str,
    url: str,
    memos_item: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """检查文章是否已上传

    Returns:
        (is_uploaded, status)
        status: 'new', 'unchanged', 'updated'
    """
    cursor = tracker_conn.execute(
        "SELECT * FROM uploaded_memos WHERE source = ? AND url = ?",
        (source, url)
    )
    record = cursor.fetchone()

    if not record:
        return False, 'new'

    # 检查是否变化（使用所有可能变化的字段）
    current_hash = compute_item_hash(memos_item)
    if record['content_hash'] == current_hash:
        return True, 'unchanged'
    else:
        return False, 'updated'


def get_articles(
    conn: sqlite3.Connection,
    source: Optional[str] = None,
    limit: Optional[int] = None
) -> List[sqlite3.Row]:
    """从数据库获取文章

    Args:
        conn: 数据库连接
        source: 可选的源名称过滤
        limit: 可选的数量限制

    Returns:
        文章列表
    """
    query = "SELECT * FROM articles WHERE 1=1"
    params = []

    if source:
        query += " AND source = ?"
        params.append(source)

    query += " ORDER BY published_at DESC"

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(query, params)
    return cursor.fetchall()


def article_to_memos_format(article: sqlite3.Row) -> Dict[str, Any]:
    """将数据库文章转换为 memos API 格式

    Args:
        article: 数据库文章行

    Returns:
        符合 memos RSS Ingest API 格式的字典
    """
    # 生成 guid: 使用 URL 作为唯一标识
    guid = article["url"]

    # 直接传递原始 published_at，让 Worker 处理解析
    # 如果数据库中没有值，则为 None
    published_at = article["published_at"] or None

    # 构建内容：只使用正文，不拼接标题（Worker 模板已有标题）
    content = article["content"] if article["content"] else ""

    return {
        "source": article["source"],
        "guid": guid,
        "url": article["url"],
        "title": article["title"],
        "published_at": published_at,
        "summary": content
    }


def record_upload(
    tracker_conn: sqlite3.Connection,
    source: str,
    url: str,
    title: str,
    memos_item: Dict[str, Any],
    memo_id: Optional[int] = None
):
    """记录上传成功"""
    # 使用所有可能变化的字段计算哈希
    content_hash = compute_item_hash(memos_item)
    now = datetime.now().isoformat()

    tracker_conn.execute("""
        INSERT OR REPLACE INTO uploaded_memos
        (source, url, title, content_hash, memo_id, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (source, url, title, content_hash, memo_id, now))
    tracker_conn.commit()


def upload_to_memos(
    tracker_conn: sqlite3.Connection,
    items: List[Dict[str, Any]],
    api_url: str,
    token: str,
    batch_size: int = DEFAULT_BATCH_SIZE,
    dry_run: bool = False
) -> Dict[str, int]:
    """批量上传文章到 memos

    Args:
        tracker_conn: 上传记录数据库连接
        items: 文章列表 (memos 格式，包含原始 article 数据)
        api_url: memos API 地址
        token: RSS Ingest Token
        batch_size: 每批上传的数量
        dry_run: 是否为试运行（不实际上传）

    Returns:
        统计信息字典
    """
    stats = {
        "total": len(items),
        "filtered": 0,  # 本地过滤掉（未变化）
        "success": 0,
        "failed": 0,
        "skipped": 0
    }

    endpoint = f"{api_url}/api/rss/ingest"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    # 分批上传
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(items) + batch_size - 1) // batch_size

        logger.info(f"处理批次 {batch_num}/{total_batches} ({len(batch)} 篇文章)...")

        if dry_run:
            logger.info(f"  [DRY-RUN] 跳过上传: {batch[0].get('title', 'N/A')[:50]}...")
            stats["filtered"] += len(batch)
            continue

        try:
            response = httpx.post(
                endpoint,
                headers=headers,
                json={"items": batch},
                timeout=30.0
            )

            if response.status_code == 200:
                result = response.json()
                summary = result.get("summary", {})
                created = summary.get("created", 0)
                updated = summary.get("updated", 0)
                skipped = summary.get("skipped", 0)
                failed = summary.get("failed", 0)

                stats["success"] += created + updated
                stats["skipped"] += skipped
                stats["failed"] += failed

                logger.info(f"  ✓ 批次完成: 新增 {created} | 更新 {updated} | 跳过 {skipped} | 失败 {failed}")

                # 只记录成功的上传，lifecycle skipped 不写入 tracker
                # 这样文章回到 inbox 后能被重新检测到并更新
                results = result.get("results", [])
                for item_data, res in zip(batch, results):
                    status = res.get("status")
                    reason = str(res.get("reason") or "").lower()

                    if status in ["created", "updated"]:
                        # 成功创建或更新，记录到 tracker
                        record_upload(
                            tracker_conn,
                            source=item_data["source"],
                            url=item_data["url"],
                            title=item_data.get("title", ""),
                            memos_item=item_data,
                            memo_id=res.get("note_id")
                        )
                    elif status == "skipped" and "lifecycle" in reason:
                        # lifecycle 导致的 skipped，不记录到 tracker
                        # 这样文章回到 inbox 后可以再次尝试更新
                        logger.debug(f"  lifecycle skipped (未记录): {item_data.get('title', 'N/A')[:50]}")

            else:
                logger.error(f"  ✗ 上传失败: HTTP {response.status_code}")
                logger.error(f"    响应: {response.text[:200]}")
                stats["failed"] += len(batch)

        except httpx.TimeoutException:
            logger.error(f"  ✗ 请求超时")
            stats["failed"] += len(batch)
        except Exception as e:
            logger.error(f"  ✗ 上传异常: {e}")
            stats["failed"] += len(batch)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="将本地 RSS 文章上传到 memos-worker（混合去重方案）",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--source", "-s",
        help="指定要上传的 RSS 源名称 (不指定则上传所有)"
    )
    parser.add_argument(
        "--batch-size", "-b",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"每批上传的数量 (默认: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--limit", "-l",
        type=int,
        help="限制上传的文章数量"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="试运行模式，不实际上传"
    )
    parser.add_argument(
        "--db",
        type=Path,
        help="指定数据库文件路径"
    )
    parser.add_argument(
        "--reset-tracker",
        action="store_true",
        help="重置上传记录（强制重新上传所有文章）"
    )

    args = parser.parse_args()

    # 打印配置信息
    logger.info("=" * 50)
    logger.info("RSS → Memos 上传工具 v2 (混合去重)")
    logger.info("=" * 50)
    logger.info(f"API 地址: {get_api_url()}")
    logger.info(f"RSS 数据库: {get_rss_db_path(args.db)}")
    logger.info(f"上传记录: {get_tracker_db_path()}")
    logger.info(f"批次大小: {args.batch_size}")
    if args.source:
        logger.info(f"过滤源: {args.source}")
    if args.limit:
        logger.info(f"数量限制: {args.limit}")
    if args.dry_run:
        logger.info("⚠️  DRY-RUN 模式 - 不会实际上传")
    logger.info("")

    # 重置上传记录
    if args.reset_tracker:
        if get_tracker_db_path().exists():
            get_tracker_db_path().unlink()
            logger.info("✓ 已重置上传记录")
        else:
            logger.info("上传记录不存在，无需重置")
        logger.info("")

    # 初始化数据库连接
    tracker_conn = init_tracker_db()
    rss_conn = init_rss_db(args.db)

    # 获取文章
    logger.info("从数据库读取文章...")
    all_articles = get_articles(rss_conn, source=args.source, limit=args.limit)
    logger.info(f"找到 {len(all_articles)} 篇文章")

    if not all_articles:
        logger.info("没有文章需要上传")
        rss_conn.close()
        tracker_conn.close()
        return

    # 本地去重过滤
    logger.info("检查本地上传记录...")
    items_to_upload = []
    stats = {
        "new": 0,
        "unchanged": 0,
        "updated": 0
    }

    for article in all_articles:
        # 先转换为 memos 格式
        item = article_to_memos_format(article)

        is_uploaded, status = is_article_uploaded(
            tracker_conn,
            article["source"],
            article["url"],
            item
        )

        if status == "unchanged":
            stats["unchanged"] += 1
        else:
            if status == "new":
                stats["new"] += 1
            elif status == "updated":
                stats["updated"] += 1

            items_to_upload.append(item)

    logger.info(f"  新文章: {stats['new']}")
    logger.info(f"  已更新: {stats['updated']}")
    logger.info(f"  未变化（已过滤）: {stats['unchanged']}")
    logger.info(f"  需要上传: {len(items_to_upload)} 篇")

    if not items_to_upload:
        logger.info("")
        logger.info("✓ 所有文章都是最新的，无需上传")
        rss_conn.close()
        tracker_conn.close()
        return

    # 上传
    logger.info("")
    logger.info("开始上传...")
    upload_stats = upload_to_memos(
        tracker_conn=tracker_conn,
        items=items_to_upload,
        api_url=get_api_url(),
        token=get_ingest_token(),
        batch_size=args.batch_size,
        dry_run=args.dry_run
    )

    # 输出统计
    logger.info("")
    logger.info("=" * 50)
    logger.info("上传完成")
    logger.info("=" * 50)
    logger.info(f"数据库总数: {stats['new'] + stats['updated'] + stats['unchanged']}")
    logger.info(f"本地过滤: {stats['unchanged']} 篇")
    logger.info(f"需要上传: {len(items_to_upload)} 篇")
    logger.info(f"上传成功: {upload_stats['success']}")
    logger.info(f"API 跳过: {upload_stats['skipped']}")
    logger.info(f"上传失败: {upload_stats['failed']}")

    rss_conn.close()
    tracker_conn.close()


if __name__ == "__main__":
    main()
