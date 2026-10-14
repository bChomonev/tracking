from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORRIDOR_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://corridor:corridor@localhost:5433/corridor"

    # OpenAI-compatible endpoint for the written analysis (see corridor.analyst).
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "discretestack-max"
    llm_critic_model: str | None = None  # claim checker; defaults to llm_model


settings = Settings()
