import time
from datetime import datetime,timedelta
from typing import Dict

import jwt

from config.config import Settings


def token_response(token: str):
    return {"access_token": token}


secret_key = Settings().secret_key


def sign_jwt(user_id: str, role: str, email: str) -> Dict[str, str]:
    expiry = datetime.utcnow() + timedelta(seconds=5)  
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expiry, 
        "iat": datetime.utcnow()  
    }
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return {"access_token": token}

def decode_jwt(token: str) -> dict:
    try:
        decoded_token = jwt.decode(token, secret_key, algorithm="HS256")
        return decoded_token
    except jwt.ExpiredSignatureError:
        return {"error": "Token has expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}


def refresh_jwt(employee_id: str, email: str):
    expiration = datetime.utcnow() + timedelta(seconds=60)  
    payload = {"sub": employee_id, "email": email, "exp": expiration}
    
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    print("Generated Refresh Token:", token) 
    
    return token


