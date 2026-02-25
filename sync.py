#!/usr/bin/env python3
"""
RSS Hub 一键同步脚本

顺序执行：
1. 抓取 RSS 源并保存到数据库
2. 上传到 memos

用法:
    python sync.py [--skip-upload] [--skip-fetch]
"""

import argparse
import logging
import subprocess
import sys
from datetime import datetime

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def run_step(name: str, cmd: list, dry_run: bool = False) -> bool:
    """执行一个步骤

    Args:
        name: 步骤名称
        cmd: 命令列表
        dry_run: 是否为试运行

    Returns:
        是否成功
    """
    logger.info("")
    logger.info("=" * 50)
    logger.info(f"步骤: {name}")
    logger.info("=" * 50)

    if dry_run:
        logger.info(f"[DRY-RUN] 将执行: {' '.join(cmd)}")
        return True

    try:
        result = subprocess.run(
            cmd,
            check=True,
            capture_output=False,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ {name} 失败 (退出码: {e.returncode})")
        return False
    except FileNotFoundError:
        logger.error(f"❌ 找不到命令: {cmd[0]}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="RSS Hub 一键同步",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="跳过抓取步骤"
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="跳过上传步骤"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="试运行模式，不实际执行"
    )
    parser.add_argument(
        "--reset-tracker",
        action="store_true",
        help="上传前重置上传记录"
    )

    args = parser.parse_args()

    logger.info("=" * 50)
    logger.info("RSS Hub 一键同步")
    logger.info("=" * 50)
    logger.info(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if args.dry_run:
        logger.info("⚠️  DRY-RUN 模式 - 不会实际执行")

    success = True

    # 步骤 1: 抓取 RSS
    if not args.skip_fetch:
        fetch_cmd = ["./.venv/bin/python", "main.py"]
        if not run_step("抓取 RSS 源", fetch_cmd, args.dry_run):
            logger.error("抓取失败，终止流程")
            sys.exit(1)
    else:
        logger.info("⏭️  跳过抓取步骤")

    # 步骤 2: 上传到 memos
    if not args.skip_upload:
        upload_cmd = ["./.venv/bin/python", "upload_to_memos.py"]
        if args.reset_tracker:
            upload_cmd.append("--reset-tracker")
        if not run_step("上传到 Memos", upload_cmd, args.dry_run):
            logger.error("上传失败")
            sys.exit(1)
    else:
        logger.info("⏭️  跳过上传步骤")

    logger.info("")
    logger.info("=" * 50)
    logger.info("✅ 同步完成")
    logger.info("=" * 50)
    logger.info(f"结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
