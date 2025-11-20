"""
Database layer using SQLAlchemy for ORM and connection management.
Supports SQLite by default with easy migration to PostgreSQL.
"""

import uuid
from datetime import datetime
from typing import Optional, List, Generator
from contextlib import contextmanager

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    DateTime,
    Text,
    JSON,
    Index,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from ..config import get_settings

Base = declarative_base()


class SurgeryCaseDB(Base):
    """
    Database model for surgery cases.
    Matches the schema from registry_patient_connect.py but modernized.
    """

    __tablename__ = "surgery_cases"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)
    uuid = Column(String(36), unique=True, nullable=False, index=True)

    # Patient information
    hn = Column(String(9), nullable=True, index=True)
    patient_name = Column(String(255), nullable=True)
    patient_id = Column(String(50), nullable=False, unique=True, index=True)
    age = Column(Integer, nullable=True)

    # Surgery details
    or_room = Column(String(10), nullable=False, index=True)
    queue_number = Column(Integer, nullable=False)
    department = Column(String(255), nullable=True)
    surgeon = Column(String(255), nullable=True)
    diagnosis = Column(JSON, nullable=True)  # List of diagnoses
    operation = Column(JSON, nullable=True)  # List of operations
    case_size = Column(String(50), nullable=True)
    urgency = Column(String(50), default="Elective")

    # Schedule
    scheduled_date = Column(DateTime, nullable=True)
    scheduled_time = Column(String(10), nullable=True)
    service_window = Column(String(50), nullable=True)

    # Ward and staff
    ward = Column(String(255), nullable=True)
    assist1 = Column(String(255), nullable=True)
    assist2 = Column(String(255), nullable=True)
    scrub_nurse = Column(String(255), nullable=True)
    circulating_nurse = Column(String(255), nullable=True)

    # Status and timing
    status = Column(String(50), nullable=False, default="รอผ่าตัด", index=True)
    timestamp = Column(DateTime, nullable=False, default=datetime.now)
    eta_minutes = Column(Integer, nullable=True)
    time_start = Column(DateTime, nullable=True)
    time_end = Column(DateTime, nullable=True)

    # Auto-transition timestamps
    auto_to_discharge_at = Column(DateTime, nullable=True)
    auto_delete_at = Column(DateTime, nullable=True)

    # Audit fields
    saved_at = Column(DateTime, nullable=False, default=datetime.now)
    updated_at = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # Additional fields
    reason = Column(Text, nullable=True)  # Reason for postponement
    notes = Column(Text, nullable=True)  # Additional notes
    repeat_24h = Column(Integer, default=0)  # Repeat surgery flag

    # Indexes for common queries
    __table_args__ = (
        Index("idx_or_status", "or_room", "status"),
        Index("idx_scheduled", "scheduled_date", "or_room"),
        Index("idx_timestamp", "timestamp"),
    )

    def __repr__(self) -> str:
        return f"<SurgeryCase(id={self.id}, patient_id={self.patient_id}, status={self.status})>"


class Database:
    """Database connection and session management."""

    def __init__(self, database_url: Optional[str] = None, echo: bool = False):
        """
        Initialize database connection.

        Args:
            database_url: SQLAlchemy database URL. If None, uses settings.
            echo: Whether to echo SQL statements (for debugging)
        """
        settings = get_settings()
        self.database_url = database_url or settings.database_url
        self.echo = echo if echo is not None else settings.database_echo

        # Special handling for SQLite in-memory databases
        if self.database_url.startswith("sqlite:///:memory:"):
            self.engine = create_engine(
                self.database_url,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
                echo=self.echo,
            )
        elif self.database_url.startswith("sqlite:///"):
            self.engine = create_engine(
                self.database_url,
                connect_args={"check_same_thread": False},
                echo=self.echo,
            )
        else:
            self.engine = create_engine(self.database_url, echo=self.echo)

        self.SessionLocal = sessionmaker(
            autocommit=False, autoflush=False, bind=self.engine
        )

    def create_tables(self) -> None:
        """Create all tables if they don't exist."""
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self) -> None:
        """Drop all tables (use with caution!)."""
        Base.metadata.drop_all(bind=self.engine)

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        Get a database session using context manager.

        Usage:
            with db.get_session() as session:
                # use session
                pass
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_db_session(self) -> Session:
        """
        Get a database session (for FastAPI dependency injection).

        Usage:
            @app.get("/")
            def endpoint(db: Session = Depends(get_db)):
                # use db
                pass
        """
        return self.SessionLocal()


# Global database instance
_db_instance: Optional[Database] = None


def get_db() -> Database:
    """Get or create global database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
        _db_instance.create_tables()
    return _db_instance


def get_db_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency for getting database sessions.

    Usage:
        @app.get("/endpoint")
        def my_endpoint(db: Session = Depends(get_db_session)):
            # use db
            pass
    """
    db = get_db()
    session = db.get_db_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# CRUD operations helper functions
def create_case(session: Session, **kwargs) -> SurgeryCaseDB:
    """Create a new surgery case."""
    if "uuid" not in kwargs:
        kwargs["uuid"] = str(uuid.uuid4())
    if "patient_id" not in kwargs and "or_room" in kwargs and "queue_number" in kwargs:
        kwargs["patient_id"] = f"{kwargs['or_room']}-{kwargs['queue_number']}"

    case = SurgeryCaseDB(**kwargs)
    session.add(case)
    session.flush()
    return case


def get_case_by_id(session: Session, case_id: int) -> Optional[SurgeryCaseDB]:
    """Get case by ID."""
    return session.query(SurgeryCaseDB).filter(SurgeryCaseDB.id == case_id).first()


def get_case_by_patient_id(
    session: Session, patient_id: str
) -> Optional[SurgeryCaseDB]:
    """Get case by patient_id."""
    return (
        session.query(SurgeryCaseDB)
        .filter(SurgeryCaseDB.patient_id == patient_id)
        .first()
    )


def get_case_by_uuid(session: Session, case_uuid: str) -> Optional[SurgeryCaseDB]:
    """Get case by UUID."""
    return session.query(SurgeryCaseDB).filter(SurgeryCaseDB.uuid == case_uuid).first()


def get_all_cases(session: Session) -> List[SurgeryCaseDB]:
    """Get all surgery cases ordered by OR room and queue."""
    return (
        session.query(SurgeryCaseDB)
        .order_by(SurgeryCaseDB.or_room, SurgeryCaseDB.queue_number)
        .all()
    )


def get_cases_by_or_room(session: Session, or_room: str) -> List[SurgeryCaseDB]:
    """Get all cases for specific OR room."""
    return (
        session.query(SurgeryCaseDB)
        .filter(SurgeryCaseDB.or_room == or_room)
        .order_by(SurgeryCaseDB.queue_number)
        .all()
    )


def get_cases_by_status(session: Session, status: str) -> List[SurgeryCaseDB]:
    """Get all cases with specific status."""
    return session.query(SurgeryCaseDB).filter(SurgeryCaseDB.status == status).all()


def update_case(
    session: Session, patient_id: str, **updates
) -> Optional[SurgeryCaseDB]:
    """Update case by patient_id."""
    case = get_case_by_patient_id(session, patient_id)
    if case:
        for key, value in updates.items():
            if hasattr(case, key):
                setattr(case, key, value)
        case.updated_at = datetime.now()
        session.flush()
    return case


def delete_case(session: Session, patient_id: str) -> bool:
    """Delete case by patient_id."""
    case = get_case_by_patient_id(session, patient_id)
    if case:
        session.delete(case)
        session.flush()
        return True
    return False
