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
    email_template:str="fill email_template .env.dev"
    admin_email_template:str="fill admin_email_template .env.dev"
    LLM_ADDR:str="fill LLM_ADDR .env.dev"
    # JWT
    secret_key: str = "secret"
    algorithm: str = "HS256"

    class Config:
        env_file = ".env.dev"
        from_attributes = True

class JWTSettings(BaseModel):
    
    # JWT settings
    authjwt_secret_key: str = "your-secure-secret-key"
    authjwt_token_location: set = {"cookies"}
    authjwt_cookie_csrf_protect: bool = False  # Enable this in production!
    
    # Token expiry settings
    authjwt_access_token_expires: int = 300  # 15 seconds
    authjwt_refresh_token_expires: int = 60*30  # 40 seconds
    
    # Cookie settings
    # authjwt_access_cookie_key: str = "access_token_cookie"
    # authjwt_refresh_cookie_key: str = "refresh_token_cookie"
    # authjwt_access_cookie_path: str = "/"
    # authjwt_refresh_cookie_path: str = "/"
    # authjwt_cookie_max_age: int = 40  # Set to the same as refresh token expiry
    # authjwt_cookie_domain: str = None  # Only readable by domain that set it
    # authjwt_cookie_secure: bool = False  # Set to True in production
    # authjwt_cookie_samesite: str = None  # Set to 'lax' in production

async def initiate_database():
    client = AsyncIOMotorClient(Settings().DATABASE_URL)
    await init_beanie(
        database=client.get_default_database(), document_models=models.__all__
    )

