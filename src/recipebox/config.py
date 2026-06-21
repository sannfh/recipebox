from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="APP_", extra="ignore")

    secret_key: str
    debug: bool = False
    access_token_expire_minutes: int = 30
    algorithm: str = "HS256"
    database_url: str = ""


settings = Settings()  # type: ignore[call-arg]
