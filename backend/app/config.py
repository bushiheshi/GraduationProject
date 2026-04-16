from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'AIGC Classroom Platform'
    app_host: str = '0.0.0.0'
    app_port: int = 18080
    debug: bool = True

    database_url: str | None = None
    postgres_host: str = '127.0.0.1'
    postgres_port: int = 5432
    postgres_user: str = 'postgres'
    postgres_password: str = '123456'
    postgres_db: str = 'aigc_platform'
    postgres_sslmode: str | None = None

    jwt_secret_key: str = 'change_me_to_a_long_random_string'
    jwt_algorithm: str = 'HS256'
    jwt_access_token_expire_minutes: int = 120

    qwen_api_key: str = ''
    qwen_base_url: str = 'https://dashscope.aliyuncs.com'
    qwen_model: str = 'qwen-coder-turbo-0919'

    deepseek_api_key: str = ''
    deepseek_base_url: str = 'https://api.deepseek.com'
    deepseek_model: str = 'deepseek-chat'

    chat_timeout_seconds: int = 90
    chat_conversation_turn_limit: int = 5

    @property
    def sqlalchemy_database_uri(self) -> str:
        if self.database_url:
            return self.database_url

        return URL.create(
            drivername='postgresql+psycopg',
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
            query={'sslmode': self.postgres_sslmode} if self.postgres_sslmode else None,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
