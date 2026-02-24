from pathlib import Path
from typing import List, Dict
import yaml

DEFAULT_CONFIG_PATH = Path(__file__).parent / "sources.yaml"
DEFAULT_DB_PATH = Path(__file__).parent / "rss.db"


def load_sources(config_path: Path = DEFAULT_CONFIG_PATH) -> List[Dict[str, str]]:
    """加载RSS源配置文件"""
    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return data.get("sources", [])


def get_db_path(db_path: Path = DEFAULT_DB_PATH) -> Path:
    """获取数据库文件路径"""
    return db_path
