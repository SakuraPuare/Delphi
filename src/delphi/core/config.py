from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DELPHI_", env_file=".env")

    # API server
    host: str = "0.0.0.0"
    port: int = 8888
    debug: bool = False
    api_key: str = ""

    # External services
    vllm_url: str = "http://localhost:8000"
    qdrant_url: str = "http://localhost:6333"
    embedding_url: str = "http://localhost:8001"
    reranker_url: str = "http://localhost:8002"

    # LLM
    llm_api_key: str = ""
    llm_model: str = "Qwen/Qwen3.5-27B"
    embedding_api_key: str = ""
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"
    embedding_backend: str = "tei"  # "tei" | "ollama" | "openai" | "cloudflare"

    # RAG
    chunk_top_k: int = 5
    query_rewrite_enabled: bool = True
    reranker_enabled: bool = True
    reranker_top_k: int = 5
    retrieve_top_k: int = 15

    # OpenTelemetry
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"
    otel_service_name: str = "delphi"


settings = Settings()
