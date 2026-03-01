"""
LUMON Database Models
PostgreSQL tables definition using SQLAlchemy
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, BigInteger, JSON, ForeignKey
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    """User account for proxy access"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    uuid = Column(String(36), nullable=False, unique=True)  # Xray/VLESS UUID
    hysteria_auth = Column(String(100), nullable=False)      # Hysteria2 auth
    sub_token = Column(String(64), unique=True, nullable=False, index=True)
    ss_user_pass = Column(String(255), nullable=True)        # Shadowsocks 2022 user-specific password

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_seen = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True, nullable=False)
    notes = Column(Text, nullable=True)

    traffic_stats = relationship("TrafficStat", back_populates="user", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.username}>"


class TrafficStat(Base):
    """Aggregated traffic statistics per user per day"""
    __tablename__ = "traffic_stats"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(DateTime, nullable=False, index=True)
    bytes_download = Column(BigInteger, default=0, nullable=False)
    bytes_upload = Column(BigInteger, default=0, nullable=False)
    connections_count = Column(Integer, default=0, nullable=False)

    user = relationship("User", back_populates="traffic_stats")

    def __repr__(self):
        return f"<TrafficStat user_id={self.user_id} date={self.date}>"


class Event(Base):
    """System events log for auditing and notifications"""
    __tablename__ = "events"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    severity = Column(String(20), default="info", index=True)
    message = Column(Text, nullable=False)
    event_data = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="events")

    def __repr__(self):
        return f"<Event {self.severity}:{self.event_type}>"


class Backup(Base):
    """Backup records tracking"""
    __tablename__ = "backups"

    id = Column(Integer, primary_key=True)
    backup_path = Column(String(255), nullable=False)
    backup_type = Column(String(20), nullable=False)
    size_bytes = Column(BigInteger, nullable=True)
    checksum = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<Backup {self.backup_type} at {self.backup_path}>"
