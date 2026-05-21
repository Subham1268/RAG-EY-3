"""
config/settings.py
──────────────────
Centralised application configuration using pydantic-settings.
All values are read from environment variables (or .env file).
"""
from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── OpenAI ─────────────────────────────────────────────
    openai_api_key: str
    openai_embedding_model: str = "text-embedding-3-large"
    openai_chat_model: str = "gpt-4o"
    openai_vision_model: str = "gpt-4o"

    # ── Pinecone ───────────────────────────────────────────
    pinecone_api_key: str
    pinecone_environment: str = "us-east-1-aws"
    pinecone_index_name: str = "ey-me-knowledge"
    pinecone_namespace_text: str = "text-chunks"
    pinecone_namespace_image: str = "image-chunks"

    # ── PostgreSQL ─────────────────────────────────────────
    database_url: str

    # ── Cohere ─────────────────────────────────────────────
    cohere_api_key: str
    cohere_rerank_model: str = "rerank-english-v3.0"

    # ── Azure AD ───────────────────────────────────────────
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    azure_ad_audience: str = "api://ey-rag-agent"

    # ── Teams Bot ──────────────────────────────────────────
    microsoft_app_id: str
    microsoft_app_password: str

    # ── LangSmith ─────────────────────────────────────────
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "ey-me-agentic-rag"

    # ── RAG Tuning ────────────────────────────────────────
    max_retrieval_k: int = 20
    rerank_top_n: int = 5
    chunk_size: int = 800
    chunk_overlap: int = 150
    max_reflection_loops: int = 2
    cache_ttl_seconds: int = 3600

    # ── App ───────────────────────────────────────────────
    app_env: str = "development"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
