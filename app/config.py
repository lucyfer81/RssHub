from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # 数据库
    database_url: str = "sqlite:///./data/rss.db"
    chroma_persist_dir: str = "./chroma_db"

    # LLM API
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    # Embedding API
    embedding_base_url: str
    embedding_api_key: str
    embedding_model: str

    # 定时任务
    scheduler_enabled: bool = True
    sync_interval_hours: int = 1
    preference_update_interval_hours: int = 24

    # RSS 抓取
    max_items_per_feed: int = 50
    fetch_timeout: int = 30
    sources_yaml_path: str = "sources.yaml"

    # Jina.ai
    jina_rate_limit_seconds: int = 2

    # 分享
    share_base_url: str

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
