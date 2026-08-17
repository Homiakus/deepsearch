"""Configuration and Settings for Adaptive Web Scraping & Retrieval Platform."""

from enum import Enum
from typing import List
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExecutionMode(str, Enum):
    FAST = "fast"          # HTTP / API only
    BALANCED = "balanced"  # Adaptive HTTP / Browser (default)
    COMPLETE = "complete"  # HTTP + Browser + Network + Files
    RESEARCH = "research"  # Complete + Markdown + Text RAG + PixelRAG
    ARCHIVE = "archive"   # Raw capture all states


class AdaptiveConfig(BaseModel):
    browser_threshold: float = Field(default=0.70, description="JS dependency score threshold for Playwright escalation")
    visual_threshold: float = Field(default=0.65, description="Visual need score threshold for Visual/PixelRAG indexing")
    api_preference: bool = Field(default=True, description="Prefer detected direct JSON API over browser rendering")
    retry_http_before_browser: bool = Field(default=True, description="Retry with HTTP headers before browser escalation")
    browser_navigation_timeout_seconds: float = Field(default=5.0, ge=2.0, le=120.0, description="Bounded browser navigation timeout")
    browser_selector_timeout_seconds: float = Field(default=3.0, ge=1.0, le=30.0, description="Bounded readiness selector timeout")


class RobotsConfig(BaseModel):
    respect: bool = Field(default=True, description="Respect robots.txt rules by default")
    user_agent: str = Field(default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36", description="User agent string")


class RateLimitConfig(BaseModel):
    global_rps: float = Field(default=500.0, description="Global requests per second")
    default_host_rps: float = Field(default=5.0, description="Default requests per second per host")
    max_host_concurrency: int = Field(default=8, description="Maximum concurrent requests per host")
    auto_concurrency: bool = Field(default=True, description="Autoscale concurrency based on system load & host latency")
    per_host_adaptive: bool = Field(default=True, description="Dynamically tune rate limits per host on 429/503/latency spikes")


class SecurityConfig(BaseModel):
    max_response_size_bytes: int = Field(default=100 * 1024 * 1024, description="Maximum response size (100MB)")
    max_decompressed_size_bytes: int = Field(default=500 * 1024 * 1024, description="Maximum decompressed size (500MB)")
    max_redirects: int = Field(default=10, description="Maximum HTTP redirects")
    block_private_ips: bool = Field(default=True, description="Block private IP addresses (SSRF protection)")
    allowed_protocols: List[str] = Field(default_factory=lambda: ["http", "https"])


class BudgetConfig(BaseModel):
    max_pages: int = Field(default=50000, description="Maximum pages to process per job")
    max_depth: int = Field(default=10, description="Maximum crawl depth")
    max_bytes: int = Field(default=10 * 1024 * 1024 * 1024, description="Maximum network bytes (10GB)")
    browser_seconds: int = Field(default=3600, description="Maximum browser execution time in seconds")
    llm_tokens: int = Field(default=1000000, description="Maximum LLM tokens budget")
    visual_pages: int = Field(default=5000, description="Maximum visual pages budget")


class CostWeights(BaseModel):
    cache: float = 0.0
    http: float = 1.0
    api: float = 1.0
    browser: float = 10.0
    llm: float = 30.0
    visual_vlm: float = 50.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore"
    )

    # Core Application Settings
    app_name: str = "DeepSearch Adaptive Scraper"
    app_version: str = "1.0.0"
    mode: ExecutionMode = ExecutionMode.BALANCED
    debug: bool = False

    # Server API & Auth
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    api_key: str = "dev-secret"

    # Database & Storage
    database_url: str = "postgresql+asyncpg://deepsearch:deepsearch@localhost:5432/deepsearch"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    storage_path: str = "./data/storage"

    # Feature Flags & Orchestration (§0, §1, DS-A40, DS-A50)
    orchestration_backend: str = "axiom"  # legacy | axiom
    retrieval_backend: str = "qdrant"     # disabled | qdrant
    visual_retrieval: str = "experimental"  # disabled | experimental
    orchestrator_url: str = "http://localhost:8081"
    orchestrator_token: str = "adgo-dev-token"

    # S3 / MinIO Object Storage CAS Backend
    cas_backend: str = "local"  # local | s3
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket_name: str = "deepsearch-cas"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: str = "minioadmin"
    s3_region: str = "us-east-1"

    # Distributed Queue Settings
    distributed_queue_backend: str = "memory"  # memory | redis
    redis_stream_key: str = "deepsearch:crawl_requests"
    redis_consumer_group: str = "deepsearch_workers"

    # Dynamic Cookie & Auth Session Persistence
    session_vault_key: str = "deepsearch-master-secret-key-32b!"
    session_vault_path: str = "./data/sessions.vault"

    # VLM Visual Embeddings
    vlm_model_name: str = "Qwen/Qwen2-VL-7B-Instruct"
    vlm_embedding_dim: int = 512

    # Operational Sub-configurations (§101 defaults)

    adaptive: AdaptiveConfig = Field(default_factory=AdaptiveConfig)
    robots: RobotsConfig = Field(default_factory=RobotsConfig)
    limits: RateLimitConfig = Field(default_factory=RateLimitConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    cost: CostWeights = Field(default_factory=CostWeights)


settings = Settings()

