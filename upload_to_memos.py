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
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import parse_qsl, urlsplit, urlunsplit, urlencode

import httpx
from dotenv import load_dotenv
from log_utils import setup_daily_file_logging

# 加载 .env 文件
load_dotenv()

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_API_URL = "https://memos.aizhi.app"
DEFAULT_BATCH_SIZE = 20
UPLOAD_TRACKER_DB = Path(__file__).parent / ".upload_tracker.db"
RSS_LIFECYCLE_INBOX = "inbox"
RSS_LIFECYCLE_READING = "reading"
RSS_LIFECYCLE_ARCHIVED = "archived"
RSS_LIFECYCLE_DELETED = "deleted"
RSS_LIFECYCLE_STATES = {
    RSS_LIFECYCLE_INBOX,
    RSS_LIFECYCLE_READING,
    RSS_LIFECYCLE_ARCHIVED,
    RSS_LIFECYCLE_DELETED,
}


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
    token = (os.environ.get("RSS_INGEST_TOKEN") or "").strip()
    if not token:
        logger.error("未设置 RSS_INGEST_TOKEN 环境变量")
        sys.exit(1)
    return token


def get_optional_ingest_token() -> Optional[str]:
    """获取可选的 RSS Ingest Token（未配置时返回 None）"""
    token = (os.environ.get("RSS_INGEST_TOKEN") or "").strip()
    return token or None


def normalize_optional_external_id(value: Any) -> Optional[str]:
    """规范化 external_id（与 Worker 逻辑对齐）"""
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    return normalized[:512]


def normalize_rss_lifecycle_state(value: Any) -> str:
    """规范化 RSS 生命周期状态"""
    normalized = str(value or "").strip().lower()
    if normalized in RSS_LIFECYCLE_STATES:
        return normalized
    return RSS_LIFECYCLE_INBOX


def extract_lifecycle_state_from_reason(reason: str) -> Optional[str]:
    """从 Worker 返回的 reason 字段提取 lifecycle 状态"""
    if not reason:
        return None
    match = re.search(r"lifecycle:([a-z_]+)", reason.strip().lower())
    if not match:
        return None
    lifecycle_state = normalize_rss_lifecycle_state(match.group(1))
    if lifecycle_state == RSS_LIFECYCLE_INBOX:
        return None
    return lifecycle_state


def normalize_canonical_url(value: Any) -> str:
    """规范化 URL（尽量对齐 Worker 的 canonical 逻辑）"""
    raw = str(value or "").strip()
    if not raw:
        return ""

    tracking_keys = {"fbclid", "gclid", "igshid", "mc_cid", "mc_eid", "ref", "spm"}

    def _normalize_with_url(input_url: str) -> str:
        parsed = urlsplit(input_url)
        if not parsed.scheme:
            raise ValueError("missing scheme")

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ValueError("missing hostname")

        port = parsed.port
        scheme = parsed.scheme.lower()
        if (scheme == "https" and port == 443) or (scheme == "http" and port == 80):
            port = None

        netloc = hostname
        if port is not None:
            netloc = f"{netloc}:{port}"

        path = parsed.path or "/"
        if len(path) > 1:
            path = re.sub(r"/+$", "", path)

        params = []
        for key, param_value in parse_qsl(parsed.query, keep_blank_values=True):
            lowered = key.lower()
            if lowered.startswith("utm_"):
                continue
            if lowered in tracking_keys:
                continue
            params.append((key, param_value))
        params.sort(key=lambda kv: kv[0])
        query = urlencode(params, doseq=True)

        return urlunsplit((scheme, netloc, path, query, ""))

    try:
        return _normalize_with_url(raw)
    except Exception:
        try:
            return _normalize_with_url(f"https://{raw}")
        except Exception:
            return raw


def resolve_item_identity(item: Dict[str, Any]) -> Tuple[Optional[str], str]:
    """解析上传项的身份键：优先 external_id，再 canonical_url"""
    external_id = normalize_optional_external_id(
        item.get("external_id") or item.get("guid") or item.get("id")
    )
    canonical_url = normalize_canonical_url(
        item.get("canonical_url") or item.get("url") or item.get("link")
    )
    return external_id, canonical_url


def _ensure_tracker_columns(conn: sqlite3.Connection):
    """为旧版 tracker 表补齐新增字段"""
    existing_columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(uploaded_memos)").fetchall()
    }
    required_columns = [
        ("external_id", "TEXT"),
        ("canonical_url", "TEXT"),
        ("published_at", "TEXT"),
        ("last_status", "TEXT"),
        ("last_reason", "TEXT"),
        ("lifecycle_state", "TEXT DEFAULT 'inbox' NOT NULL"),
        ("suppressed", "INTEGER DEFAULT 0 NOT NULL"),
        ("retry_count", "INTEGER DEFAULT 0 NOT NULL"),
        ("last_seen_at", "TIMESTAMP"),
        ("last_synced_at", "TIMESTAMP"),
    ]

    for column_name, column_def in required_columns:
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE uploaded_memos ADD COLUMN {column_name} {column_def}")

    conn.execute(
        "UPDATE uploaded_memos SET lifecycle_state = ? "
        "WHERE lifecycle_state IS NULL OR TRIM(lifecycle_state) = ''",
        (RSS_LIFECYCLE_INBOX,)
    )
    conn.execute(
        "UPDATE uploaded_memos SET suppressed = 0 WHERE suppressed IS NULL"
    )
    conn.execute(
        "UPDATE uploaded_memos SET retry_count = 0 WHERE retry_count IS NULL"
    )


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
            external_id TEXT,
            canonical_url TEXT,
            published_at TEXT,
            title TEXT,
            content_hash TEXT,
            memo_id INTEGER,
            last_status TEXT,
            last_reason TEXT,
            lifecycle_state TEXT DEFAULT 'inbox' NOT NULL,
            suppressed INTEGER DEFAULT 0 NOT NULL,
            retry_count INTEGER DEFAULT 0 NOT NULL,
            last_seen_at TIMESTAMP,
            last_synced_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, url)
        )
    """)

    _ensure_tracker_columns(conn)

    # 创建索引
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracker_source ON uploaded_memos(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracker_uploaded ON uploaded_memos(updated_at)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tracker_source_external ON uploaded_memos(source, external_id)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracker_canonical ON uploaded_memos(canonical_url)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tracker_source_title_pub "
        "ON uploaded_memos(source, title, published_at)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracker_lifecycle ON uploaded_memos(lifecycle_state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tracker_suppressed ON uploaded_memos(suppressed)")

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


def compute_legacy_item_hash(item: Dict[str, Any]) -> str:
    """兼容旧版哈希（包含身份字段）"""
    import hashlib
    import json

    hash_data = {
        "title": item.get("title", ""),
        "summary": item.get("summary", ""),
        "published_at": item.get("published_at", ""),
        "external_id": normalize_optional_external_id(item.get("external_id") or item.get("guid") or ""),
        "canonical_url": normalize_canonical_url(item.get("canonical_url") or item.get("url") or ""),
    }
    hash_str = json.dumps(hash_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(hash_str.encode("utf-8")).hexdigest()[:16]


def compute_item_hash(item: Dict[str, Any]) -> str:
    """计算文章内容哈希（不包含 URL 身份键，避免同文不同链重复上传）

    Args:
        item: memos API 格式的文章项

    Returns:
        哈希值
    """
    import hashlib
    import json

    # 仅使用“内容语义”字段
    hash_data = {
        "title": item.get("title", ""),
        "summary": item.get("summary", ""),
        "published_at": item.get("published_at", ""),
    }

    # 使用 JSON 确保顺序一致
    hash_str = json.dumps(hash_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(hash_str.encode('utf-8')).hexdigest()[:16]


def find_tracker_record(
    tracker_conn: sqlite3.Connection,
    source: str,
    url: str,
    memos_item: Dict[str, Any]
) -> Optional[sqlite3.Row]:
    """按身份键查找 tracker 记录：source+external_id -> canonical_url -> source+url"""
    external_id, canonical_url = resolve_item_identity(memos_item)
    title = str(memos_item.get("title") or "").strip()
    published_at = str(memos_item.get("published_at") or "").strip()

    if external_id:
        cursor = tracker_conn.execute(
            "SELECT * FROM uploaded_memos WHERE source = ? AND external_id = ? LIMIT 1",
            (source, external_id)
        )
        record = cursor.fetchone()
        if record:
            return record

    if canonical_url:
        cursor = tracker_conn.execute(
            "SELECT * FROM uploaded_memos WHERE canonical_url = ? LIMIT 1",
            (canonical_url,)
        )
        record = cursor.fetchone()
        if record:
            return record

    cursor = tracker_conn.execute(
        "SELECT * FROM uploaded_memos WHERE source = ? AND url = ? LIMIT 1",
        (source, url)
    )
    record = cursor.fetchone()
    if record:
        return record

    # 最后的保底：同源 + 同标题 + 同发布时间，兜住 URL 漂移导致的同文重复上传
    if title and published_at:
        cursor = tracker_conn.execute(
            "SELECT * FROM uploaded_memos WHERE source = ? AND title = ? AND published_at = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (source, title, published_at)
        )
        return cursor.fetchone()

    return None


def should_upload_article(
    tracker_conn: sqlite3.Connection,
    source: str,
    url: str,
    memos_item: Dict[str, Any]
) -> Tuple[bool, str, Optional[sqlite3.Row]]:
    """本地判定是否需要上传"""
    record = find_tracker_record(tracker_conn, source, url, memos_item)
    if not record:
        return True, "new", None

    lifecycle_state = normalize_rss_lifecycle_state(record["lifecycle_state"])
    suppressed = int(record["suppressed"] or 0) == 1
    if suppressed and lifecycle_state != RSS_LIFECYCLE_INBOX:
        return False, f"suppressed:{lifecycle_state}", record

    # inbox 下比较内容哈希
    current_hash = compute_item_hash(memos_item)
    legacy_hash = compute_legacy_item_hash(memos_item)
    record_hash = str(record["content_hash"] or "")
    if lifecycle_state == RSS_LIFECYCLE_INBOX and record_hash in {current_hash, legacy_hash}:
        return False, "unchanged", record

    return True, "updated", record


def upsert_tracker_record(
    tracker_conn: sqlite3.Connection,
    source: str,
    url: str,
    title: str,
    memos_item: Dict[str, Any],
    status: Optional[str] = None,
    reason: Optional[str] = None,
    lifecycle_state: Optional[str] = None,
    suppressed: Optional[int] = None,
    memo_id: Optional[int] = None,
    increment_retry: bool = False,
):
    """写入/更新 tracker 状态记录"""
    now = datetime.now().isoformat()
    content_hash = compute_item_hash(memos_item)
    external_id, canonical_url = resolve_item_identity(memos_item)
    published_at = memos_item.get("published_at")
    existing = find_tracker_record(tracker_conn, source, url, memos_item)

    if existing:
        merged_source = existing["source"] or source
        merged_external_id = existing["external_id"] or external_id
        next_lifecycle = normalize_rss_lifecycle_state(
            lifecycle_state if lifecycle_state is not None else existing["lifecycle_state"]
        )
        next_suppressed = int(
            suppressed if suppressed is not None else (existing["suppressed"] or 0)
        )
        next_retry_count = int(existing["retry_count"] or 0)
        if increment_retry:
            next_retry_count += 1
        elif status is not None:
            next_retry_count = 0

        next_memo_id = memo_id if memo_id is not None else existing["memo_id"]
        next_status = status if status is not None else existing["last_status"]
        next_reason = reason if reason is not None else existing["last_reason"]
        next_last_synced_at = now if status is not None else existing["last_synced_at"]

        tracker_conn.execute("""
            UPDATE uploaded_memos
            SET source = ?, url = ?, external_id = ?, canonical_url = ?, published_at = ?, title = ?,
                content_hash = ?, memo_id = ?, last_status = ?, last_reason = ?,
                lifecycle_state = ?, suppressed = ?, retry_count = ?,
                last_seen_at = ?, last_synced_at = ?, updated_at = ?
            WHERE id = ?
        """, (
            merged_source,
            url,
            merged_external_id,
            canonical_url,
            published_at,
            title,
            content_hash,
            next_memo_id,
            next_status,
            next_reason,
            next_lifecycle,
            next_suppressed,
            next_retry_count,
            now,
            next_last_synced_at,
            now,
            existing["id"],
        ))
    else:
        next_lifecycle = normalize_rss_lifecycle_state(lifecycle_state)
        next_suppressed = int(suppressed or 0)
        next_retry_count = 1 if increment_retry else 0
        tracker_conn.execute("""
            INSERT INTO uploaded_memos (
                source, url, external_id, canonical_url, published_at, title, content_hash, memo_id,
                last_status, last_reason, lifecycle_state, suppressed, retry_count,
                last_seen_at, last_synced_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source,
            url,
            external_id,
            canonical_url,
            published_at,
            title,
            content_hash,
            memo_id,
            status,
            reason,
            next_lifecycle,
            next_suppressed,
            next_retry_count,
            now,
            now if status is not None else None,
            now,
        ))

    tracker_conn.commit()


def update_tracker_lifecycle_from_remote(
    tracker_conn: sqlite3.Connection,
    record_id: int,
    lifecycle_state: str,
    suppressed: int,
    memo_id: Optional[int] = None,
    reason: Optional[str] = None,
):
    """仅更新 lifecycle 同步结果，不改 content_hash"""
    now = datetime.now().isoformat()
    tracker_conn.execute("""
        UPDATE uploaded_memos
        SET lifecycle_state = ?, suppressed = ?, memo_id = COALESCE(?, memo_id),
            last_status = ?, last_reason = ?, retry_count = 0,
            last_synced_at = ?, updated_at = ?
        WHERE id = ?
    """, (
        normalize_rss_lifecycle_state(lifecycle_state),
        int(suppressed),
        memo_id,
        "synced",
        reason,
        now,
        now,
        record_id,
    ))


def get_suppressed_archived_records_by_source(
    tracker_conn: sqlite3.Connection,
    sources: List[str]
) -> Dict[str, List[sqlite3.Row]]:
    """获取当前范围内被 lifecycle 抑制的 archived 记录"""
    source_list = sorted({str(s).strip() for s in sources if str(s).strip()})
    if not source_list:
        return {}

    placeholders = ",".join(["?"] * len(source_list))
    query = f"""
        SELECT *
        FROM uploaded_memos
        WHERE suppressed = 1
          AND lifecycle_state = ?
          AND source IN ({placeholders})
    """
    params: List[Any] = [RSS_LIFECYCLE_ARCHIVED, *source_list]
    rows = tracker_conn.execute(query, params).fetchall()

    grouped: Dict[str, List[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(row["source"], []).append(row)
    return grouped


def sync_remote_lifecycle_hints(
    tracker_conn: sqlite3.Connection,
    api_url: str,
    token: str,
    sources: List[str],
    page_limit: int = 100,
    max_pages_per_source: int = 20,
) -> Dict[str, int]:
    """轻量远端同步：仅回填 suppressed 记录的 lifecycle 状态"""
    stats = {
        "source_candidates": 0,
        "suppressed_candidates": 0,
        "sources_synced": 0,
        "pages_fetched": 0,
        "reactivated": 0,
        "confirmed_archived": 0,
        "errors": 0,
    }

    suppressed_by_source = get_suppressed_archived_records_by_source(tracker_conn, sources)
    stats["source_candidates"] = len(suppressed_by_source)
    stats["suppressed_candidates"] = sum(len(rows) for rows in suppressed_by_source.values())
    if not suppressed_by_source:
        return stats

    endpoint = f"{api_url}/api/rss/items"
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(timeout=20.0) as client:
        for source_name, rows in suppressed_by_source.items():
            pending_ids = {int(row["id"]) for row in rows}
            by_external: Dict[str, sqlite3.Row] = {}
            by_canonical: Dict[str, sqlite3.Row] = {}
            for row in rows:
                external_id = normalize_optional_external_id(row["external_id"])
                canonical_url = normalize_canonical_url(row["canonical_url"] or row["url"])
                if external_id:
                    by_external[external_id] = row
                if canonical_url:
                    by_canonical[canonical_url] = row

            if not pending_ids:
                continue

            stats["sources_synced"] += 1
            page = 1
            while page <= max_pages_per_source and pending_ids:
                try:
                    response = client.get(
                        endpoint,
                        headers=headers,
                        params={
                            "source": source_name,
                            "state": "all",
                            "archived": "all",
                            "page": page,
                            "limit": page_limit,
                        },
                    )
                except Exception as e:
                    logger.warning(f"远端生命周期同步失败（source={source_name}, page={page}）: {e}")
                    stats["errors"] += 1
                    break

                if response.status_code != 200:
                    logger.warning(
                        f"远端生命周期同步失败（source={source_name}, page={page}）: "
                        f"HTTP {response.status_code}"
                    )
                    stats["errors"] += 1
                    break

                try:
                    payload = response.json()
                except Exception:
                    logger.warning(
                        f"远端生命周期同步失败（source={source_name}, page={page}）: 无法解析 JSON"
                    )
                    stats["errors"] += 1
                    break

                stats["pages_fetched"] += 1
                items = payload.get("items", [])
                for remote_item in items:
                    remote_external_id = normalize_optional_external_id(remote_item.get("external_id"))
                    remote_canonical_url = normalize_canonical_url(remote_item.get("canonical_url"))

                    matched = None
                    if remote_external_id and remote_external_id in by_external:
                        matched = by_external[remote_external_id]
                    elif remote_canonical_url and remote_canonical_url in by_canonical:
                        matched = by_canonical[remote_canonical_url]

                    if not matched:
                        continue

                    record_id = int(matched["id"])
                    lifecycle_state = normalize_rss_lifecycle_state(remote_item.get("lifecycle_state"))
                    note_id = remote_item.get("note_id")

                    if lifecycle_state == RSS_LIFECYCLE_INBOX:
                        update_tracker_lifecycle_from_remote(
                            tracker_conn=tracker_conn,
                            record_id=record_id,
                            lifecycle_state=RSS_LIFECYCLE_INBOX,
                            suppressed=0,
                            memo_id=note_id,
                            reason="remote_sync:lifecycle:inbox",
                        )
                        stats["reactivated"] += 1
                    else:
                        update_tracker_lifecycle_from_remote(
                            tracker_conn=tracker_conn,
                            record_id=record_id,
                            lifecycle_state=lifecycle_state,
                            suppressed=1,
                            memo_id=note_id,
                            reason=f"remote_sync:lifecycle:{lifecycle_state}",
                        )
                        if lifecycle_state == RSS_LIFECYCLE_ARCHIVED:
                            stats["confirmed_archived"] += 1

                    pending_ids.discard(record_id)

                has_more = bool(payload.get("hasMore"))
                if not has_more:
                    break
                page += 1

            tracker_conn.commit()

    return stats


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
    canonical_url = normalize_canonical_url(article["url"])
    external_id = normalize_optional_external_id(guid)

    # 直接传递原始 published_at，让 Worker 处理解析
    # 如果数据库中没有值，则为 None
    published_at = article["published_at"] or None

    # 构建内容：只使用正文，不拼接标题（Worker 模板已有标题）
    content = article["content"] if article["content"] else ""

    return {
        "source": article["source"],
        "guid": guid,
        "external_id": external_id,
        "canonical_url": canonical_url,
        "url": article["url"],
        "title": article["title"],
        "published_at": published_at,
        "summary": content
    }


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

                # 回写 tracker 状态：created/updated/recreated/skipped/error 都记录
                raw_results = result.get("results", [])
                result_by_index = {}
                for res in raw_results:
                    index = res.get("index")
                    if isinstance(index, int):
                        result_by_index[index] = res

                for batch_index, item_data in enumerate(batch):
                    res = result_by_index.get(batch_index)
                    if not res:
                        continue

                    status = str(res.get("status") or "").lower()
                    reason = str(res.get("reason") or "")
                    lifecycle_state = extract_lifecycle_state_from_reason(reason)
                    note_id = res.get("note_id")

                    if status in ["created", "updated", "recreated"]:
                        upsert_tracker_record(
                            tracker_conn=tracker_conn,
                            source=item_data["source"],
                            url=item_data["url"],
                            title=item_data.get("title", ""),
                            memos_item=item_data,
                            status=status,
                            reason=reason,
                            lifecycle_state=RSS_LIFECYCLE_INBOX,
                            suppressed=0,
                            memo_id=note_id,
                        )
                    elif status == "skipped":
                        if lifecycle_state:
                            upsert_tracker_record(
                                tracker_conn=tracker_conn,
                                source=item_data["source"],
                                url=item_data["url"],
                                title=item_data.get("title", ""),
                                memos_item=item_data,
                                status=status,
                                reason=reason,
                                lifecycle_state=lifecycle_state,
                                suppressed=1,
                                memo_id=note_id,
                            )
                        else:
                            upsert_tracker_record(
                                tracker_conn=tracker_conn,
                                source=item_data["source"],
                                url=item_data["url"],
                                title=item_data.get("title", ""),
                                memos_item=item_data,
                                status=status,
                                reason=reason,
                                lifecycle_state=RSS_LIFECYCLE_INBOX,
                                suppressed=0,
                                memo_id=note_id,
                            )
                    elif status == "error":
                        upsert_tracker_record(
                            tracker_conn=tracker_conn,
                            source=item_data["source"],
                            url=item_data["url"],
                            title=item_data.get("title", ""),
                            memos_item=item_data,
                            status=status,
                            reason=reason,
                            increment_retry=True,
                        )

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
    log_file = setup_daily_file_logging(__file__, "upload")

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
    parser.add_argument(
        "--skip-remote-sync",
        action="store_true",
        help="跳过上传前的远端 lifecycle 轻量同步"
    )

    args = parser.parse_args()

    # 打印配置信息
    logger.info("=" * 50)
    logger.info("RSS → Memos 上传工具 v2 (混合去重)")
    logger.info("=" * 50)
    logger.info(f"上传日志: {log_file}")
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
    logger.info(f"远端同步: {'关闭' if args.skip_remote_sync else '开启'}")
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

    # 上传前轻量远端同步（只同步被 lifecycle 抑制的记录）
    if not args.skip_remote_sync:
        logger.info("执行远端生命周期轻量同步...")
        optional_token = get_optional_ingest_token()
        if optional_token:
            source_scope = sorted({str(article["source"]) for article in all_articles})
            sync_stats = sync_remote_lifecycle_hints(
                tracker_conn=tracker_conn,
                api_url=get_api_url(),
                token=optional_token,
                sources=source_scope,
            )
            logger.info(
                "  同步结果: source候选 %s | 抑制候选 %s | 扫描源 %s | 拉取页数 %s | "
                "恢复inbox %s | 仍归档 %s | 错误 %s",
                sync_stats["source_candidates"],
                sync_stats["suppressed_candidates"],
                sync_stats["sources_synced"],
                sync_stats["pages_fetched"],
                sync_stats["reactivated"],
                sync_stats["confirmed_archived"],
                sync_stats["errors"],
            )
        else:
            logger.info("  未配置 RSS_INGEST_TOKEN，跳过远端同步")

    # 本地去重过滤
    logger.info("检查本地上传记录...")
    items_to_upload = []
    stats = {
        "new": 0,
        "unchanged": 0,
        "updated": 0,
        "suppressed": 0,
    }

    for article in all_articles:
        # 先转换为 memos 格式
        item = article_to_memos_format(article)

        should_upload, status, _record = should_upload_article(
            tracker_conn,
            article["source"],
            article["url"],
            item
        )

        if not should_upload and status == "unchanged":
            stats["unchanged"] += 1
            if _record:
                upsert_tracker_record(
                    tracker_conn=tracker_conn,
                    source=article["source"],
                    url=article["url"],
                    title=item.get("title", ""),
                    memos_item=item,
                )
        elif not should_upload and status.startswith("suppressed:"):
            stats["suppressed"] += 1
            if _record:
                upsert_tracker_record(
                    tracker_conn=tracker_conn,
                    source=article["source"],
                    url=article["url"],
                    title=item.get("title", ""),
                    memos_item=item,
                )
        else:
            if status == "new":
                stats["new"] += 1
            elif status == "updated":
                stats["updated"] += 1

            items_to_upload.append(item)

    logger.info(f"  新文章: {stats['new']}")
    logger.info(f"  已更新: {stats['updated']}")
    logger.info(f"  未变化（已过滤）: {stats['unchanged']}")
    logger.info(f"  生命周期抑制（已过滤）: {stats['suppressed']}")
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
    logger.info(f"数据库总数: {stats['new'] + stats['updated'] + stats['unchanged'] + stats['suppressed']}")
    logger.info(f"本地过滤: {stats['unchanged'] + stats['suppressed']} 篇")
    logger.info(f"需要上传: {len(items_to_upload)} 篇")
    logger.info(f"上传成功: {upload_stats['success']}")
    logger.info(f"API 跳过: {upload_stats['skipped']}")
    logger.info(f"上传失败: {upload_stats['failed']}")

    rss_conn.close()
    tracker_conn.close()


if __name__ == "__main__":
    main()
