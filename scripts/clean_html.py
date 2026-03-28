"""清洗数据库中现有的 HTML 内容，转换为 Markdown"""

import asyncio
import sqlite3
from pathlib import Path
import re
from markdownify import markdownify as md


def clean_html_to_markdown(html: str) -> str:
    """将 HTML 转换为 Markdown 并清理多余空白"""
    if not html:
        return ""

    text = md(html, strip=['script', 'style'])
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    return text


def main():
    db_path = Path(__file__).parent.parent / "data" / "rss.db"

    if not db_path.exists():
        print(f"数据库不存在: {db_path}")
        return

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 需要清洗的字段列表
    fields = ["summary", "summary_zh", "title_zh", "content", "content_zh"]
    total_updated = 0

    for field in fields:
        cursor.execute(f"SELECT id, {field} FROM items WHERE {field} LIKE '%<%'")
        rows = cursor.fetchall()

        if rows:
            print(f"清洗字段 {field}: 找到 {len(rows)} 条记录")
            for item_id, content in rows:
                if content and '<' in content:
                    cleaned = clean_html_to_markdown(content)
                    cursor.execute(f"UPDATE items SET {field} = ? WHERE id = ?", (cleaned, item_id))
                    total_updated += 1

    conn.commit()
    conn.close()

    print(f"完成！共更新 {total_updated} 条记录")


if __name__ == "__main__":
    main()
