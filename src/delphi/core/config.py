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
    llm_model: str = "Qwen/Qwen2.5-Coder-7B-Instruct"
    embedding_model: str = "BAAI/bge-m3"
    reranker_model: str = "BAAI/bge-reranker-v2-m3"

    # RAG
    chunk_top_k: int = 5
    query_rewrite_enabled: bool = True
    reranker_enabled: bool = True
    reranker_top_k: int = 5
    retrieve_top_k: int = 15


settings = Settings()
