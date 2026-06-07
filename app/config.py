from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql://hypo_user:hypo_pass@db/hypo_db"
    openai_api_key: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
