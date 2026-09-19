from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = 'NavosEdge Intelligence Server'
    APP_VERSION: str = '0.1.0'
    HOST: str = '0.0.0.0'
    PORT: int = 8420
    LOG_LEVEL: str = 'INFO'
    DATA_DIR: Path = Path('./data')
    ARTIFACTS_DIR: Path = Path('./artifacts')
    MAX_PAYLOAD_BYTES: int = 65536
    SSE_HEARTBEAT_INTERVAL_S: float = 15.0
    STORAGE_MAX_FILE_SIZE_MB: float = 50.0
    STORAGE_MAX_FILES_PER_NODE: int = 30
    MODEL_WEIGHTS_FILE: str = 'gasnet.pt'
    MODEL_PREPROCESS_FILE: str = 'preprocess.pkl'

    model_config = SettingsConfigDict(
        env_prefix='NAVOS_',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
