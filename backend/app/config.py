from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    POSTGRES_DB: str = "kombain"
    POSTGRES_USER: str = "kombain"
    POSTGRES_PASSWORD: str = "kombain"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"
    SENTRY_DSN: str | None = None

    @property
    def database_url(self) -> str:
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    class Config:
        env_file = ".env"


settings = Settings()
