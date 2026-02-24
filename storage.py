import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any

from config import get_db_path


def init_db(db_path: Path = None) -> sqlite3.Connection:
    """初始化数据库，创建表"""
    if db_path is None:
        db_path = get_db_path()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            source TEXT NOT NULL,
            content TEXT,
            published_at TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON articles(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_published ON articles(published_at)")

    conn.commit()
    return conn


def article_exists(conn: sqlite3.Connection, url: str) -> bool:
    """检查文章URL是否已存在"""
    cursor = conn.execute("SELECT 1 FROM articles WHERE url = ? LIMIT 1", (url,))
    return cursor.fetchone() is not None


def save_article(
    conn: sqlite3.Connection,
    title: str,
    url: str,
    source: str,
    content: str,
    published_at: Optional[str] = None
) -> bool:
    """保存文章到数据库，返回是否成功插入"""
    try:
        conn.execute(
            """
            INSERT INTO articles (title, url, source, content, published_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (title, url, source, content, published_at)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def get_stats(conn: sqlite3.Connection) -> Dict[str, int]:
    """获取数据库统计信息"""
    cursor = conn.execute("SELECT COUNT(*) FROM articles")
    total = cursor.fetchone()[0]

    cursor = conn.execute("SELECT source, COUNT(*) as cnt FROM articles GROUP BY source")
    by_source = {row[0]: row[1] for row in cursor.fetchall()}

    return {"total": total, "by_source": by_source}
