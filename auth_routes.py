from fastapi import APIRouter, HTTPException, Depends, Response, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from auth import oauth2_handler, get_current_user
from database import engine  # Import engine, not RDBMS class
from sqlalchemy.orm import sessionmaker
from models import User, Job
from typing import Dict, Any, Optional
from datetime import datetime
import os

# Plan Limits (Keep in sync with main.py)
PLAN_LIMITS = {
    'free': 5,
    'pro': 25,
    'enterprise': 1000
}

router = APIRouter(prefix="/auth", tags=["authentication"])
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class GoogleTokenRequest(BaseModel):
    token: str

class LoginResponse(BaseModel):
    user: Dict[str, Any]
    message: str = "Login successful"

@router.post("/google/login", response_model=LoginResponse)
async def google_login(request: GoogleTokenRequest, response: Response):
    """Login with Google OAuth2 token and set secure session cookie."""
    # Verify Google token
    user_info = oauth2_handler.verify_google_token(request.token)
    if not user_info:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    
    # Use SQLAlchemy ORM directly
    session = SessionLocal()
    
    # Try to find existing user
    db_user = session.query(User).filter(User.google_id == user_info['user_id']).first()
    
    if db_user:
        # Update existing user
        db_user.email = user_info['email']
        db_user.name = user_info['name']
        db_user.picture_url = user_info['picture']
        db_user.updated_at = datetime.utcnow()  # type: ignore
    else:
        # Create new user
        db_user = User(
            google_id=user_info['user_id'],
            email=user_info['email'],
            name=user_info['name'],
            picture_url=user_info['picture'],
            plan_type="free"
        )
        session.add(db_user)
    
    session.commit()
    session.refresh(db_user)
    session.close()
    
    # Convert to dict
    user_dict = {c.name: getattr(db_user, c.name) for c in db_user.__table__.columns}
    
    # Generate JWT access token and set as HTTP-only cookie
    access_token = oauth2_handler.create_access_token(user_info)
    
    # Determine if we are in production
    is_production = os.getenv("ENVIRONMENT", "development") == "production"
    
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,      # Not accessible from JavaScript
        secure=is_production, # Only sent over HTTPS in production
        samesite="lax",     # CSRF protection
        max_age=86400       # 24 hours
    )
    
    return LoginResponse(
        user=user_dict,
        message="Login successful"
    )

@router.get("/google/callback")
async def google_callback(request: Request, code: str, state: Optional[str] = None):
    """Handle Google OAuth2 callback."""
    # Dynamically construct redirect_uri based on the request host
    # This ensures it matches what the frontend used (window.location.origin)
    base_url = str(request.base_url).rstrip('/')
    redirect_uri = f"{base_url}/auth/google/callback"
    
    # Fallback to env var if needed (though dynamic is better for localhost/127.0.0.1 support)
    # redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")
    
    # Exchange code for tokens
    token_data = oauth2_handler.exchange_code(code, redirect_uri)
    if not token_data or 'id_token' not in token_data:
        raise HTTPException(status_code=400, detail="Failed to exchange code for tokens")
    
    # Verify ID token
    user_info = oauth2_handler.verify_google_token(token_data['id_token'])
    if not user_info:
        raise HTTPException(status_code=400, detail="Invalid ID token")
        
    # Create/Update user
    session = SessionLocal()
    db_user = session.query(User).filter(User.google_id == user_info['user_id']).first()
    
    if db_user:
        db_user.email = user_info['email']
        db_user.name = user_info['name']
        db_user.picture_url = user_info['picture']
        db_user.updated_at = datetime.utcnow()  # type: ignore
    else:
        db_user = User(
            google_id=user_info['user_id'],
            email=user_info['email'],
            name=user_info['name'],
            picture_url=user_info['picture'],
            plan_type="free"
        )
        session.add(db_user)
    
    session.commit()
    session.refresh(db_user)
    session.close()
    
    # Generate JWT and set cookie
    access_token = oauth2_handler.create_access_token(user_info)
    
    # Determine if we are in production
    is_production = os.getenv("ENVIRONMENT", "development") == "production"
    
    response = RedirectResponse(url="/dashboard")
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_production,
        samesite="lax",
        max_age=86400
    )
    
    return response

@router.get("/me")
async def get_current_user_info(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get current user information with plan usage."""
    session = SessionLocal()
    db_user = session.query(User).filter(User.google_id == current_user['user_id']).first()
    
    if not db_user:
        session.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    # Calculate usage
    plan_type = str(db_user.plan_type) if db_user.plan_type else 'free'
    limit = PLAN_LIMITS.get(plan_type, 5)
    
    start_date = None
    if plan_type != 'free':
        # Start of current month
        now = datetime.utcnow()
        start_date = datetime(now.year, now.month, 1)
    
    query = session.query(Job).filter(Job.user_id == db_user.id)
    if start_date:
        query = query.filter(Job.created_at >= start_date)
    usage = query.count()
    
    session.close()
    
    user_dict = {c.name: getattr(db_user, c.name) for c in db_user.__table__.columns}
    
    return {
        "user": user_dict,
        "plan": {
            "type": plan_type,
            "usage": usage,
            "limit": limit,
            "reset_date": "Monthly" if plan_type != 'free' else "Never"
        }
    }

@router.post("/test-login")
async def test_login(response: Response):
    """Development-only test login endpoint that sets secure session cookie."""
    # Security: Disable in production
    if os.getenv("ENVIRONMENT", "development") == "production":
        raise HTTPException(status_code=403, detail="Test login disabled in production")

    test_user_data = {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "name": "Test User"
    }
    
    try:
        # Create or update test user in database
        session = SessionLocal()
        db_user = session.query(User).filter(User.google_id == "test-user-123").first()
        
        if not db_user:
            db_user = User(
                google_id="test-user-123",
                email="test@example.com",
                name="Test User"
            )
            session.add(db_user)
        
        session.commit()
        session.refresh(db_user)
        session.close()
        
        # Convert to dict
        user_dict = {c.name: getattr(db_user, c.name) for c in db_user.__table__.columns}
        
        # Generate JWT token and set as HTTP-only cookie
        access_token = oauth2_handler.create_access_token(test_user_data)
        response.set_cookie(
            key="access_token",
            value=access_token,
            httponly=True,
            secure=True,
            samesite="lax",
            max_age=86400
        )
        
        return LoginResponse(
            user=user_dict,
            message="Test login successful"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Test login failed: {str(e)}")

@router.post("/logout")
async def logout(response: Response):
    """Logout by clearing session cookie."""
    response.delete_cookie(
        key="access_token",
        secure=True,
        samesite="lax"
    )
    return {"message": "Logged out successfully"}

@router.get("/status")
async def auth_status():
    """Check authentication system status."""
    return {
        "status": "active",
        "google_oauth_enabled": bool(oauth2_handler.client_id),
        "jwt_enabled": True
    }

class UpdatePlanRequest(BaseModel):
    plan_type: str

@router.post("/update-plan")
async def update_plan(request: UpdatePlanRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update current user's plan type."""
    session = SessionLocal()
    db_user = session.query(User).filter(User.google_id == current_user['user_id']).first()
    
    if not db_user:
        session.close()
        raise HTTPException(status_code=404, detail="User not found")
    
    db_user.plan_type = request.plan_type  # type: ignore
    db_user.updated_at = datetime.utcnow()  # type: ignore
    
    session.commit()
    session.refresh(db_user)
    session.close()
    
    return {"message": f"Plan updated to {request.plan_type}", "plan_type": request.plan_type}