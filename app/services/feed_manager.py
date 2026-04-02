import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.models import Feed


@dataclass
class YamlFeed:
    name: str
    url: str
    enabled: bool = True


class FeedManager:
    def __init__(self, yaml_path: str = "sources.yaml"):
        self.yaml_path = Path(yaml_path)
        self._lock = asyncio.Lock()

    def read_yaml(self) -> list[YamlFeed]:
        """Read sources.yaml, return list. If file doesn't exist, return empty list."""
        if not self.yaml_path.exists():
            return []

        with open(self.yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data or "sources" not in data:
            return []

        feeds = []
        for entry in data["sources"]:
            feeds.append(
                YamlFeed(
                    name=entry["name"],
                    url=entry["url"],
                    enabled=entry.get("enabled", True),
                )
            )
        return feeds

    def write_yaml(self, feeds: list[YamlFeed]) -> None:
        """Atomic write: write to .tmp file, then os.replace() to final path."""
        sources = []
        for feed in feeds:
            entry = {"name": feed.name, "url": feed.url}
            if not feed.enabled:
                entry["enabled"] = False
            sources.append(entry)

        data = {"sources": sources}

        tmp_path = str(self.yaml_path) + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

        os.replace(tmp_path, str(self.yaml_path))

    async def add_to_yaml(self, name: str, url: str, enabled: bool = True) -> None:
        """Append entry. Raise ValueError if URL already exists."""
        async with self._lock:
            feeds = self.read_yaml()
            if any(f.url == url for f in feeds):
                raise ValueError(f"URL already exists: {url}")
            feeds.append(YamlFeed(name=name, url=url, enabled=enabled))
            self.write_yaml(feeds)

    async def update_in_yaml(
        self, url: str, name: str | None = None, enabled: bool | None = None
    ) -> None:
        """Update by URL key."""
        async with self._lock:
            feeds = self.read_yaml()
            for feed in feeds:
                if feed.url == url:
                    if name is not None:
                        feed.name = name
                    if enabled is not None:
                        feed.enabled = enabled
                    break
            self.write_yaml(feeds)

    async def remove_from_yaml(self, url: str) -> None:
        """Remove by URL."""
        async with self._lock:
            feeds = self.read_yaml()
            feeds = [f for f in feeds if f.url != url]
            self.write_yaml(feeds)

    async def sync_yaml_to_db(self, session) -> tuple[int, int, int]:
        """Returns (created, updated, disabled).

        - YAML feeds not in DB (by URL): create new Feed rows
        - DB feeds not in YAML: set enabled=False (don't delete)
        - DB feeds in YAML: update name and enabled from YAML
        """
        from sqlalchemy import select

        yaml_feeds = self.read_yaml()

        result = await session.execute(select(Feed))
        db_feeds = result.scalars().all()

        # Build lookup maps
        yaml_by_url = {f.url: f for f in yaml_feeds}
        db_by_url = {f.url: f for f in db_feeds}

        created = 0
        updated = 0
        disabled = 0

        # YAML feeds not in DB: create new
        for yaml_feed in yaml_feeds:
            if yaml_feed.url not in db_by_url:
                new_feed = Feed(
                    name=yaml_feed.name,
                    url=yaml_feed.url,
                    enabled=yaml_feed.enabled,
                )
                session.add(new_feed)
                created += 1

        # DB feeds not in YAML: disable
        for db_feed in db_feeds:
            if db_feed.url not in yaml_by_url:
                if db_feed.enabled:
                    db_feed.enabled = False
                    disabled += 1

        # DB feeds in YAML: update name and enabled
        for db_feed in db_feeds:
            if db_feed.url in yaml_by_url:
                yaml_feed = yaml_by_url[db_feed.url]
                changed = False
                if db_feed.name != yaml_feed.name:
                    db_feed.name = yaml_feed.name
                    changed = True
                if db_feed.enabled != yaml_feed.enabled:
                    db_feed.enabled = yaml_feed.enabled
                    changed = True
                if changed:
                    updated += 1

        await session.commit()

        return (created, updated, disabled)


_feed_manager: FeedManager | None = None


def get_feed_manager() -> FeedManager:
    global _feed_manager
    if _feed_manager is None:
        from app.config import get_settings

        settings = get_settings()
        _feed_manager = FeedManager(settings.sources_yaml_path)
    return _feed_manager
