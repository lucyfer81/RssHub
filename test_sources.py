#!/usr/bin/env python3
"""快速测试 sources.yaml 中的所有RSS源是否可访问"""

import yaml
import httpx
import feedparser
from pathlib import Path

def test_rss_source(source_name: str, source_url: str, timeout: int = 30) -> dict:
    """测试单个RSS源

    返回测试结果字典
    """
    result = {
        'name': source_name,
        'url': source_url,
        'accessible': False,
        'error': None,
        'entry_count': 0,
        'has_content': False,
        'has_summary': False
    }

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; RSS-Hub/0.1.0; +https://github.com/rss-hub)"
        }

        with httpx.Client(timeout=timeout, trust_env=True) as client:
            response = client.get(source_url, headers=headers)
            response.raise_for_status()
            feed_content = response.content

        # 解析feed
        feed = feedparser.parse(feed_content)

        if feed.bozo and feed.bozo_exception:
            result['error'] = f"RSS解析警告: {feed.bozo_exception}"
            # 即使有警告也继续检查

        # 检查是否有entries
        if hasattr(feed, 'entries') and feed.entries:
            result['accessible'] = True
            result['entry_count'] = len(feed.entries)

            # 检查前几个条目的内容情况
            for entry in feed.entries[:3]:  # 只检查前3个
                if hasattr(entry, 'content') and entry.content:
                    result['has_content'] = True
                    break
                if hasattr(entry, 'summary') and entry.summary:
                    result['has_summary'] = True
        else:
            result['error'] = "RSS源没有找到任何文章条目"

    except httpx.HTTPStatusError as e:
        result['error'] = f"HTTP错误 {e.response.status_code}"
    except httpx.TimeoutException:
        result['error'] = "请求超时"
    except Exception as e:
        result['error'] = str(e)

    return result


def main():
    # 读取sources.yaml
    sources_file = Path(__file__).parent / "sources.yaml"
    with open(sources_file, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)

    sources = config.get('sources', [])

    print(f"开始测试 {len(sources)} 个RSS源...\n")
    print("=" * 80)

    results = []
    success_count = 0
    fail_count = 0

    for source in sources:
        name = source.get('name', 'Unknown')
        url = source.get('url', '')

        print(f"\n测试: {name}")
        print(f"URL: {url}")

        result = test_rss_source(name, url)
        results.append(result)

        if result['accessible']:
            success_count += 1
            status = "✓ 可访问"
            print(f"状态: {status}")
            print(f"文章数量: {result['entry_count']}")
            print(f"内容字段: {'有' if result['has_content'] else '无'}")
            print(f"摘要字段: {'有' if result['has_summary'] else '无'}")
            if result['error']:
                print(f"警告: {result['error']}")
        else:
            fail_count += 1
            status = "✗ 不可访问"
            print(f"状态: {status}")
            print(f"错误: {result['error']}")

        print("-" * 80)

    # 打印总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)
    print(f"总计: {len(sources)} 个源")
    print(f"成功: {success_count} 个")
    print(f"失败: {fail_count} 个")
    print(f"成功率: {success_count/len(sources)*100:.1f}%")

    # 列出有问题的源
    if fail_count > 0:
        print("\n有问题的源:")
        for result in results:
            if not result['accessible']:
                print(f"  - {result['name']}: {result['error']}")


if __name__ == "__main__":
    main()
