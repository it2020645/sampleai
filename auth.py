import os
import json
import base64
import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import HTTPException, Depends, Request, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from google.auth.transport import requests
from google.oauth2 import id_token
import logging

# Minimal JWT fallback (HS256 only) to avoid external dependency installs
class ExpiredSignatureError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = '=' * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _ensure_ts(value):
    if isinstance(value, datetime):
        return int(value.timestamp())
    return value


def _jwt_encode(payload: Dict[str, Any], secret: str, algorithm: str = "HS256") -> str:
    if algorithm != "HS256":
        raise InvalidTokenError("Unsupported algorithm")
    header = {"alg": "HS256", "typ": "JWT"}
    safe_payload = {k: _ensure_ts(v) for k, v in payload.items()}
    header_b64 = _b64url_encode(json.dumps(header, separators=(',', ':')).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(safe_payload, separators=(',', ':')).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    signature_b64 = _b64url_encode(signature)
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def _jwt_decode(token: str, secret: str, algorithms: Optional[list] = None) -> Dict[str, Any]:
    if algorithms and "HS256" not in algorithms:
        raise InvalidTokenError("Unsupported algorithm")
    parts = token.split('.')
    if len(parts) != 3:
        raise InvalidTokenError("Invalid token format")
    header_b64, payload_b64, signature_b64 = parts
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    try:
        provided_sig = _b64url_decode(signature_b64)
    except Exception as exc:  # pragma: no cover - defensive
        raise InvalidTokenError(f"Bad signature: {exc}")
    if not hmac.compare_digest(expected_sig, provided_sig):
        raise InvalidTokenError("Signature verification failed")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception as exc:  # pragma: no cover - defensive
        raise InvalidTokenError(f"Bad payload: {exc}")
    exp = payload.get("exp")
    if exp is not None and time.time() > exp:
        raise ExpiredSignatureError("Token expired")
    return payload


try:  # Prefer real PyJWT if installed
    import jwt as pyjwt  # type: ignore
    jwt = pyjwt
except ImportError:  # Fallback minimal implementation
    class _MiniJWT:
        ExpiredSignatureError = ExpiredSignatureError
        InvalidTokenError = InvalidTokenError

        @staticmethod
        def encode(payload: Dict[str, Any], secret: str, algorithm: str = "HS256") -> str:
            return _jwt_encode(payload, secret, algorithm)

        @staticmethod
        def decode(token: str, secret: str, algorithms: Optional[list] = None, options: Optional[dict] = None) -> Dict[str, Any]:
            return _jwt_decode(token, secret, algorithms)

    jwt = _MiniJWT()

logger = logging.getLogger(__name__)

class GoogleOAuth2:
    def __init__(self):
        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.jwt_secret = os.getenv("JWT_SECRET_KEY", "your-super-secret-jwt-key-change-in-production")
        
        if not self.client_id:
            raise ValueError("GOOGLE_CLIENT_ID environment variable is required")
    
    def verify_google_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify Google OAuth2 token and return user info."""
        try:
            # Verify the token with Google
            idinfo = id_token.verify_oauth2_token(
                token, requests.Request(), self.client_id
            )
            
            # Additional validation
            if idinfo.get('iss') not in ['accounts.google.com', 'https://accounts.google.com']:
                raise ValueError('Wrong issuer.')
            
            return {
                'user_id': idinfo['sub'],
                'email': idinfo['email'],
                'name': idinfo.get('name', ''),
                'picture': idinfo.get('picture', ''),
                'verified_email': idinfo.get('email_verified', False)
            }
        except ValueError as e:
            logger.error(f"Google token verification failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during token verification: {e}")
            return None
    
    def create_access_token(self, user_info: Dict[str, Any], expires_hours: int = 24) -> str:
        """Create a JWT access token for the user."""
        now = datetime.utcnow()
        exp_ts = int((now + timedelta(hours=expires_hours)).timestamp())
        payload = {
            'user_id': user_info['user_id'],
            'email': user_info['email'],
            'name': user_info['name'],
            'exp': exp_ts,
            'iat': int(now.timestamp()),
            'type': 'access_token'
        }
        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')
    
    def verify_access_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT access token and return user info."""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Access token expired")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Invalid access token")
            return None
    def exchange_code(self, code: str, redirect_uri: str) -> Optional[Dict[str, Any]]:
        """Exchange authorization code for tokens."""
        import requests
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            'code': code,
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code'
        }
        try:
            response = requests.post(token_url, data=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Token exchange failed: {e}")
            return None

# Global auth instance
oauth2_handler = GoogleOAuth2()
security = HTTPBearer()

async def get_current_user(request: Request) -> Dict[str, Any]:
    """Get current user from session cookie, raise error if not authenticated."""
    
    try:
        # Extract token from session cookie
        token = request.cookies.get("access_token")
        logger.info(f"Checking auth token. Cookies: {request.cookies.keys()}")
        
        if not token:
            logger.warning("No access_token found in cookies")
            raise HTTPException(status_code=401, detail="Not authenticated. Please sign in.")
        
        # Check if this looks like a JWT token
        if token.count('.') != 2:
            raise HTTPException(status_code=401, detail="Invalid session. Please sign in again.")
        
        # Decode JWT token using the oauth2_handler instance
        try:
            payload = jwt.decode(token, oauth2_handler.jwt_secret, algorithms=['HS256'])
            user_id = payload.get('user_id')
            
            if not user_id:
                raise HTTPException(status_code=401, detail="Invalid token payload")
            
            return {
                'user_id': user_id,
                'email': payload.get('email'),
                'name': payload.get('name')
            }
            
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid session. Please sign in again.")
            
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Unexpected error in get_current_user: {e}")
        raise HTTPException(status_code=500, detail="Authentication error")

async def get_current_user_optional(request: Request) -> Optional[Dict[str, Any]]:
    """Get current user from session cookie, return None if not authenticated."""
    
    try:
        # Extract token from session cookie
        token = request.cookies.get("access_token")
        
        if not token:
            return None
        
        # Check if this looks like a JWT token (has 3 parts separated by dots)
        if token.count('.') != 2:
            logger.warning("Invalid token format: not a JWT token")
            return None
        
        # Decode JWT token using the oauth2_handler instance
        try:
            payload = jwt.decode(token, oauth2_handler.jwt_secret, algorithms=['HS256'])
            user_id = payload.get('user_id')
            
            if not user_id:
                logger.warning("No user_id in JWT token")
                return None
            
            return {
                'user_id': user_id,
                'email': payload.get('email'),
                'name': payload.get('name')
            }
            
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None
            
    except Exception as e:
        logger.error(f"Unexpected error in get_current_user_optional: {e}")
        return None