from typing import Optional

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic_settings import BaseSettings
import models as models
from pydantic import BaseModel

class Settings(BaseSettings):
    # database configurations
    DATABASE_URL: Optional[str] = None
    sender_email: str = "fill sender_email .env.dev"
    sender_password:str = "fill sender_password .env.dev"
    # JWT
    secret_key: str = "secret"
    algorithm: str = "HS256"

    class Config:
        env_file = ".env.dev"
        from_attributes = True

class JWTSettings(BaseModel):
    # Your existing DB settings
    DATABASE_URL: str = "postgresql://user:password@localhost/dbname"
    
    # JWT settings
    authjwt_secret_key: str = "your-secure-secret-key"
    authjwt_token_location: set = {"cookies"}
    authjwt_cookie_csrf_protect: bool = True  # Enable this in production!

async def initiate_database():
    client = AsyncIOMotorClient(Settings().DATABASE_URL)
    await init_beanie(
        database=client.get_default_database(), document_models=models.__all__
    )

