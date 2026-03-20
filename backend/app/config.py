from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'AIGC Classroom Platform'
    app_host: str = '0.0.0.0'
    app_port: int = 8000
    debug: bool = True

    mysql_host: str = '127.0.0.1'
    mysql_port: int = 3306
    mysql_user: str = 'root'
    mysql_password: str = '123456'
    mysql_db: str = 'aigc_platform'

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
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


