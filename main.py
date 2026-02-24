import logging
import sys
from datetime import datetime

from config import load_sources
from storage import init_db, article_exists, save_article, get_stats
from fetcher import fetch_entries

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def main():
    """主函数：抓取所有RSS源并保存到数据库"""
    logger.info("=" * 50)
    logger.info("RSS Hub 开始运行")

    # 加载配置
    try:
        sources = load_sources()
        logger.info(f"加载了 {len(sources)} 个RSS源")
    except Exception as e:
        logger.error(f"加载配置失败: {e}")
        sys.exit(1)

    # 初始化数据库
    conn = init_db()
    logger.info("数据库连接成功")

    # 统计信息
    stats = {
        'total_processed': 0,
        'total_added': 0,
        'total_skipped': 0,
        'failed_sources': [],
        'by_source': {}
    }

    # 处理每个RSS源
    for source in sources:
        name = source['name']
        url = source['url']

        logger.info(f"处理源: {name}")

        try:
            entries = fetch_entries(name, url)

            if not entries:
                logger.warning(f"  没有获取到文章条目")
                stats['failed_sources'].append(name)
                continue

            stats['by_source'][name] = {'added': 0, 'skipped': 0}

            for entry in entries:
                stats['total_processed'] += 1

                # 检查是否已存在
                if article_exists(conn, entry['url']):
                    stats['total_skipped'] += 1
                    stats['by_source'][name]['skipped'] += 1
                    continue

                # 保存文章
                if save_article(
                    conn,
                    entry['title'],
                    entry['url'],
                    entry['source'],
                    entry['content'],
                    entry.get('published_at')
                ):
                    stats['total_added'] += 1
                    stats['by_source'][name]['added'] += 1
                    logger.info(f"  新增: {entry['title'][:50]}...")

        except Exception as e:
            logger.error(f"  处理失败: {e}")
            stats['failed_sources'].append(name)
            continue

    # 输出统计信息
    logger.info("=" * 50)
    logger.info("运行完成")
    logger.info(f"总处理: {stats['total_processed']} 篇")
    logger.info(f"新增: {stats['total_added']} 篇")
    logger.info(f"跳过: {stats['total_skipped']} 篇")

    if stats['failed_sources']:
        logger.warning(f"失败的源: {', '.join(stats['failed_sources'])}")

    logger.info("\n各源详情:")
    for source, s in stats['by_source'].items():
        logger.info(f"  {source}: +{s['added']} | ⊘{s['skipped']}")

    # 数据库总览
    db_stats = get_stats(conn)
    logger.info(f"\n数据库总文章数: {db_stats['total']}")

    conn.close()
    logger.info("RSS Hub 运行结束")


if __name__ == "__main__":
    main()
