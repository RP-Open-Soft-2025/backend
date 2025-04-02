from beanie import Document
from datetime import datetime, UTC, timedelta
from typing import Optional
import uuid

class ResetToken(Document):
    token: str
    email: str
    timestamp: datetime
    is_first_login: bool = False
    is_admin: bool = False
    used: bool = False
    
    class Settings:
        name = "reset_tokens"
        
    @classmethod
    async def create_token(cls, email: str, is_first_login: bool = False, is_admin: bool = False):
        token = await cls(
            token=str(uuid.uuid4()),
            email=email,
            timestamp=datetime.now(UTC),
            is_first_login=is_first_login,
            is_admin=is_admin
        ).insert()
        return token
    
    @classmethod
    async def get_token(cls, token: str):
        return await cls.find_one({"token": token, "used": False})
    
    @classmethod
    async def get_admin_token(cls, token: str):
        return await cls.find_one({"token": token, "used": False, "is_admin": True})
    
    @classmethod
    async def get_employee_token(cls, token: str):
        return await cls.find_one({"token": token, "used": False, "is_admin": False})
    
    @classmethod
    async def mark_as_used(cls, token: str):
        token_doc = await cls.find_one({"token": token})
        if token_doc:
            token_doc.used = True
            await token_doc.save()
        return token_doc
    
    @classmethod
    async def delete_token(cls, token: str):
        """Delete a token from the database."""
        token_doc = await cls.find_one({"token": token})
        if token_doc:
            await token_doc.delete()
        return token_doc
    
    @classmethod
    async def cleanup_expired_tokens(cls, max_age_minutes: int = 5):
        """Delete all expired tokens from the database."""
        cutoff_time = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
        result = await cls.find({"timestamp": {"$lt": cutoff_time}}).delete()
        return result
    
    @classmethod
    async def has_recent_request(cls, email: str, cooldown_minutes: int = 2):
        """Check if there was a recent reset request for this email."""
        cutoff_time = datetime.now(UTC) - timedelta(minutes=cooldown_minutes)
        recent_token = await cls.find_one({
            "email": email,
            "timestamp": {"$gt": cutoff_time}
        })
        return recent_token is not None 