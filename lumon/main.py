"""
LUMON Panel API
FastAPI application for subscription endpoints
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import PlainTextResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
import base64
import json

from lumon.database import SessionLocal, engine, Base
from lumon.models import User, TrafficStat, Event
from lumon.config import config
from lumon.subscription import generate_subscription_list, generate_html_page

# Create FastAPI app
app = FastAPI(
    title="LUMON Panel API",
    description="Minimalistic proxy subscription API",
    version="1.0.0"
)

# CORS middleware (if needed for web clients)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================
# Health Check Endpoint
# ============================================
@app.get("/health")
async def health_check():
    """Health check for monitoring"""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

# ============================================
# Subscription Endpoint
# ============================================
@app.get("/sub/{uuid}/{token}")
async def get_subscription(uuid: str, token: str, request: Request):
    """
    Generate subscription config for user

    Returns:
    - Base64-encoded subscription list for clients (Hiddify, v2rayNG)
    - HTML page with individual configs when opened in browser
    """
    db = SessionLocal()
    client_ip = request.client.host

    try:
        # Find user by UUID and token
        user = db.query(User).filter(
            User.uuid == uuid,
            User.sub_token == token,
            User.is_active == True
        ).first()

        if not user:
            # Log failed attempt
            log_event(db, None, "subscription_failed", "warning",
                     f"Invalid subscription attempt",
                     {"uuid": uuid, "ip": client_ip})

            # Return 404 (not 403 to avoid revealing info)
            raise HTTPException(status_code=404, detail="Not found")

        # Update last_seen
        user.last_seen = datetime.utcnow()
        db.commit()

        # Log successful access
        if config.enable_ip_logging:
            log_event(db, user.id, "subscription_accessed", "info",
                     f"Subscription accessed",
                     {"ip": client_ip})

        # Check if browser or client
        accept_header = request.headers.get("accept", "")

        if "text/html" in accept_header:
            # Return HTML page for browser
            html_content = generate_html_page(user, config.subscription_domain)
            return HTMLResponse(content=html_content)
        else:
            # Return Base64 subscription for clients
            sub_lines = generate_subscription_list(user, config.subscription_domain)
            b64_content = base64.b64encode("\n".join(sub_lines).encode()).decode()

            return PlainTextResponse(
                content=b64_content,
                headers={
                    "Content-Type": "text/plain; charset=utf-8",
                    "Profile-Update-Interval": "6",  # Hours
                    "Profile-Title": f"LUMON-{user.username}"
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_event(db, None, "subscription_error", "error",
                 f"Subscription error: {str(e)}",
                 {"uuid": uuid})
        raise HTTPException(status_code=500, detail="Internal error")
    finally:
        db.close()

# ============================================
# Helper Functions
# ============================================
def log_event(db: Session, user_id: int, event_type: str, severity: str,
              message: str, metadata: dict = None):
    """Log event to database"""
    try:
        event = Event(
            user_id=user_id,
            event_type=event_type,
            severity=severity,
            message=message,
            event_data=metadata
        )
        db.add(event)
        db.commit()
    except Exception as e:
        print(f"⚠️  Failed to log event: {e}")
        db.rollback()

# ============================================
# Startup Event
# ============================================
@app.on_event("startup")
async def startup_event():
    """Log API startup"""
    print("🚀 LUMON API starting...")
    print(f"📡 Subscription domain: {config.subscription_domain}")
    print(f"🎭 Decoy domain: {config.decoy_domain}")
