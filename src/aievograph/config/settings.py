from datetime import datetime
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Semantic Scholar venue names for target conferences.
# Used as the `venue` parameter in the bulk search API.
TARGET_VENUES: list[str] = [
    # ML general
    "NeurIPS",
    "ICML",
    "ICLR",
    # NLP
    "ACL",
    "EMNLP",
    "NAACL",
    # CV
    "CVPR",
    "ICCV",
    "ECCV",
    # AI general
    "AAAI",
    "IJCAI",
    # Data / IR
    "KDD",
    "SIGIR",
    # Others
    "ICRA",
    "AISTATS",
]


class AppSettings(BaseSettings):
    """Environment-variable-based application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    neo4j_uri: str = Field("bolt://localhost:7687", alias="NEO4J_URI")
    neo4j_user: str = Field("neo4j", alias="NEO4J_USER")
    neo4j_password: str = Field(..., alias="NEO4J_PASSWORD")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    s2_base_url: str = Field(
        "https://api.semanticscholar.org/graph/v1",
        alias="S2_BASE_URL",
    )
    s2_api_key: str = Field("", alias="S2_API_KEY")
    collect_year_start: int = Field(
        default_factory=lambda: datetime.now().year - 15,
        alias="COLLECT_YEAR_START",
    )
    collect_year_end: int = Field(
        default_factory=lambda: datetime.now().year - 1,
        alias="COLLECT_YEAR_END",
    )
    citation_top_percent: float = Field(0.20, alias="CITATION_TOP_PERCENT")
    cache_dir: str = Field(".cache/semantic_scholar", alias="CACHE_DIR")


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()
