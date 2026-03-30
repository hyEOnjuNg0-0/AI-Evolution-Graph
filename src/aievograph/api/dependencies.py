"""
Dependency injection factories for FastAPI route handlers.
Each function constructs and returns the appropriate domain service
wired to its infrastructure adapters.
"""
from functools import lru_cache

from neo4j import GraphDatabase

from aievograph.config.settings import AppSettings, get_settings
from aievograph.domain.services.breakthrough_detection_service import BreakthroughDetectionService
from aievograph.domain.services.evolution_path_service import EvolutionPathService
from aievograph.domain.services.hybrid_retrieval_service import HybridRetrievalService
from aievograph.domain.services.trend_momentum_service import TrendMomentumService
from aievograph.domain.services.vector_retrieval_service import VectorRetrievalService
from aievograph.infrastructure.neo4j_citation_time_series_repository import (
    Neo4jCitationTimeSeriesRepository,
)
from aievograph.infrastructure.neo4j_graph_repository import Neo4jGraphRepository
from aievograph.infrastructure.neo4j_method_evolution_repository import (
    Neo4jMethodEvolutionRepository,
)
from aievograph.infrastructure.neo4j_method_trend_repository import Neo4jMethodTrendRepository
from aievograph.infrastructure.neo4j_vector_repository import Neo4jVectorRepository
from aievograph.infrastructure.openai_embedding_client import OpenAIEmbeddingClient


@lru_cache(maxsize=1)
def _get_driver(settings: AppSettings):
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )


def get_hybrid_retrieval_service() -> HybridRetrievalService:
    settings = get_settings()
    driver = _get_driver(settings)
    embedding_client = OpenAIEmbeddingClient(settings.openai_api_key)
    vector_repo = Neo4jVectorRepository(driver)
    graph_repo = Neo4jGraphRepository(driver)
    vector_svc = VectorRetrievalService(embedding_client, vector_repo)
    return HybridRetrievalService(vector_svc, graph_repo)


def get_graph_repository() -> Neo4jGraphRepository:
    settings = get_settings()
    driver = _get_driver(settings)
    return Neo4jGraphRepository(driver)


def get_breakthrough_service() -> BreakthroughDetectionService:
    settings = get_settings()
    driver = _get_driver(settings)
    time_series_repo = Neo4jCitationTimeSeriesRepository(driver)
    return BreakthroughDetectionService(time_series_repo)


def get_trend_service() -> TrendMomentumService:
    settings = get_settings()
    driver = _get_driver(settings)
    trend_repo = Neo4jMethodTrendRepository(driver)
    return TrendMomentumService(trend_repo)


def get_evolution_path_service() -> EvolutionPathService:
    settings = get_settings()
    driver = _get_driver(settings)
    evolution_repo = Neo4jMethodEvolutionRepository(driver)
    return EvolutionPathService(evolution_repo)
