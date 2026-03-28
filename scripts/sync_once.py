#!/usr/bin/env python3
import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.scheduler import Scheduler

async def main():
    scheduler = Scheduler()
    await scheduler.sync_feeds()

if __name__ == "__main__":
    asyncio.run(main())
