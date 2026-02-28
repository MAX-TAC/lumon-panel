"""
LUMON Database Connection
PostgreSQL connection with SQLAlchemy
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from lumon.config import config

# Database URL builder
def get_db_url() -> str:
    """Build PostgreSQL connection URL from config"""
    password = config.db_password
    if not password:
        raise ValueError("Database password not configured in /etc/lumon/lumon_config.json")
    return f"postgresql://lumon:{password}@localhost/lumon_db"

# SQLAlchemy engine setup
engine = create_engine(
    get_db_url(),
    pool_pre_ping=True,           # Check connection health before use
    pool_recycle=3600,            # Recycle connections every hour
    echo=False,                   # Set True for SQL query debugging
    pool_size=10,                 # Max connections in pool
    max_overflow=20               # Extra connections beyond pool_size
)

# Session factory for database operations
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

# Base class for ORM models
Base = declarative_base()

# Dependency for FastAPI routes (if needed later)
def get_db():
    """Yield database session for FastAPI dependency injection"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Helper for CLI and scripts
def get_session():
    """Get a database session for CLI usage"""
    return SessionLocal()

# Utility: check database connection
def check_connection() -> bool:
    """Test if we can connect to the database"""
    try:
        conn = engine.connect()
        conn.close()
        return True
    except Exception:
        return False
