from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field

class Settings(BaseSettings):
    DATABASE_URL: SecretStr = Field(..., validation_alias="DATABASE_URL")
    SECRET_KEY: SecretStr = Field(..., validation_alias="SECRET_KEY")
    GOOGLE_API_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()