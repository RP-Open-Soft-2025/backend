import time
from datetime import datetime, timedelta, timezone
from typing import Dict
import jwt
from config.config import Settings
from fastapi import HTTPException


def token_response(token: str):
    return {"access_token": token}


secret_key = Settings().secret_key


def sign_jwt(employee_id: str, role: str, email: str) -> Dict[str, str]:
    expiry = datetime.now(timezone.utc) + timedelta(days=15)  # Access token expires in 15 days
    payload = {
        "employee_id": employee_id,
        "email": email,
        "role": role,
        # "account_activated": account_activated,
        "exp": expiry, 
        "iat": datetime.now(timezone.utc)  
    }
    try:
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        return {"access_token": token}
    except Exception as e:
        print(f"Error encoding JWT: {str(e)}")
        raise


def decode_jwt(token: str) -> dict:
    try:
        # Remove 'Bearer ' prefix if present
        if token.startswith("Bearer "):
            token = token.split(" ")[1]

        decoded_token = jwt.decode(token, secret_key, algorithms=["HS256"])
        return decoded_token
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired. Please refresh your token or log in again."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=401,
            detail="Invalid token format or signature."
        )
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Token validation error: {str(e)}"
        )


def refresh_jwt(employee_id: str, email: str):
    expiration = datetime.now(timezone.utc) + timedelta(days=30)  # Refresh token expires in 2 days
    # expiration = datetime.now(timezone.utc) + timedelta(minutes=2)  # Refresh token expires in 2 minutes
    payload = {"employee_id": employee_id, "email": email, "exp": expiration}

    try:
        token = jwt.encode(payload, secret_key, algorithm="HS256")
        print("Generated Refresh Token:", token) 
        return token
    except Exception as e:
        print(f"Error generating refresh token: {str(e)}")
        raise
