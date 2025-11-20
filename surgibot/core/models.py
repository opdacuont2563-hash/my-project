"""
Data models using Pydantic for validation and serialization.
These models are used throughout the application for type safety and validation.
"""

from datetime import datetime, date, time
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator


class SurgeryStatus(str, Enum):
    """Valid surgery status values."""

    WAITING = "รอผ่าตัด"
    IN_SURGERY = "กำลังผ่าตัด"
    IN_RECOVERY = "กำลังพักฟื้น"
    RECOVERY_COMPLETE = "พักฟื้นครบแล้ว"
    RETURNING = "กำลังส่งกลับตึก"
    POSTPONED = "เลื่อนการผ่าตัด"


class UrgencyLevel(str, Enum):
    """Surgery urgency levels."""

    ELECTIVE = "Elective"
    URGENT = "Urgent"
    EMERGENCY = "Emergency"


class CaseSize(str, Enum):
    """Surgery case size classification."""

    SMALL = "Small"
    MEDIUM = "Medium"
    LARGE = "Large"
    EXTRA_LARGE = "Extra Large"


class PatientCaseBase(BaseModel):
    """Base model for patient case data."""

    or_room: str = Field(..., description="Operating room identifier")
    queue: int = Field(..., ge=1, description="Queue number in OR")
    hn: Optional[str] = Field(None, description="Hospital Number (9 digits)")
    patient_name: Optional[str] = Field(None, description="Patient name")
    age: Optional[int] = Field(None, ge=0, le=150, description="Patient age")
    department: Optional[str] = Field(None, description="Department name")
    surgeon: Optional[str] = Field(None, description="Surgeon name")
    diagnosis: Optional[List[str]] = Field(
        default_factory=list, description="List of diagnoses"
    )
    operation: Optional[List[str]] = Field(
        default_factory=list, description="List of operations"
    )
    ward: Optional[str] = Field(None, description="Ward name")
    case_size: Optional[CaseSize] = Field(None, description="Case size classification")
    urgency: UrgencyLevel = Field(
        default=UrgencyLevel.ELECTIVE, description="Urgency level"
    )
    assist1: Optional[str] = Field(None, description="First assistant")
    assist2: Optional[str] = Field(None, description="Second assistant")
    scrub_nurse: Optional[str] = Field(None, description="Scrub nurse")
    circulating_nurse: Optional[str] = Field(None, description="Circulating nurse")

    @field_validator("hn")
    @classmethod
    def validate_hn(cls, v: Optional[str]) -> Optional[str]:
        """Validate Hospital Number format."""
        if v is None or v == "":
            return None
        v = v.strip()
        if not v.isdigit() or len(v) != 9:
            raise ValueError("HN must be exactly 9 digits")
        return v


class PatientCaseCreate(PatientCaseBase):
    """Model for creating a new patient case."""

    status: SurgeryStatus = Field(
        default=SurgeryStatus.WAITING, description="Initial surgery status"
    )
    scheduled_date: Optional[date] = Field(None, description="Scheduled surgery date")
    scheduled_time: Optional[time] = Field(None, description="Scheduled surgery time")


class PatientCaseUpdate(BaseModel):
    """Model for updating an existing patient case."""

    status: Optional[SurgeryStatus] = None
    eta_minutes: Optional[int] = Field(None, ge=0, description="Estimated time arrival")
    time_start: Optional[datetime] = None
    time_end: Optional[datetime] = None
    notes: Optional[str] = None


class PatientCase(PatientCaseBase):
    """Complete patient case model with all fields."""

    id: int = Field(..., description="Unique identifier")
    uuid: str = Field(..., description="UUID for external reference")
    patient_id: str = Field(..., description="Patient identifier (OR-Queue)")
    status: SurgeryStatus = Field(..., description="Current surgery status")
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Status timestamp"
    )
    eta_minutes: Optional[int] = Field(
        None, ge=0, description="Estimated time to completion (minutes)"
    )
    time_start: Optional[datetime] = Field(None, description="Surgery start time")
    time_end: Optional[datetime] = Field(None, description="Surgery end time")
    scheduled_date: Optional[date] = Field(None, description="Scheduled date")
    scheduled_time: Optional[time] = Field(None, description="Scheduled time")
    auto_to_discharge_at: Optional[datetime] = Field(
        None, description="Auto transition to discharge time"
    )
    auto_delete_at: Optional[datetime] = Field(
        None, description="Auto delete timestamp"
    )
    saved_at: datetime = Field(
        default_factory=datetime.now, description="Record creation time"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, description="Last update time"
    )

    class Config:
        """Pydantic configuration."""

        from_attributes = True
        json_encoders = {datetime: lambda v: v.isoformat() if v else None}


class StatusUpdate(BaseModel):
    """Model for status update requests."""

    action: str = Field(..., description="Action: add, edit, delete")
    patient_id: Optional[str] = Field(None, description="Patient identifier")
    or_room: Optional[str] = Field(None, description="Operating room")
    queue: Optional[str] = Field(None, description="Queue number")
    status: Optional[SurgeryStatus] = Field(None, description="New status")
    eta_minutes: Optional[int] = Field(
        None, ge=0, description="Estimated time (minutes)"
    )
    hn: Optional[str] = Field(None, description="Hospital Number")
    token: str = Field(..., description="Authentication token")

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        """Validate action value."""
        v = v.lower().strip()
        if v not in ("add", "edit", "delete"):
            raise ValueError("Action must be: add, edit, or delete")
        return v


class SnapshotItem(BaseModel):
    """Model for snapshot items sent to clients."""

    id: str = Field(..., description="Masked HN or ID")
    hn_full: Optional[str] = Field(None, description="Full HN (authorized only)")
    patient_id: str = Field(..., description="Patient identifier")
    status: str = Field(..., description="Current status")
    timestamp: Optional[str] = Field(None, description="Status timestamp ISO")
    eta_minutes: Optional[int] = Field(None, description="ETA in minutes")
    eta_time: Optional[str] = Field(None, description="ETA datetime ISO")
    eta_remaining_seconds: Optional[int] = Field(
        None, description="Remaining seconds to ETA"
    )


class Snapshot(BaseModel):
    """Model for complete snapshot response."""

    ok: bool = True
    items: List[SnapshotItem] = Field(default_factory=list)
    version: int = Field(default=0, description="Snapshot version number")
    updated_at: str = Field(..., description="Update timestamp ISO")


class HealthResponse(BaseModel):
    """Health check response model."""

    ok: bool = True
    timestamp: str = Field(..., description="Server timestamp ISO")
    version: str = Field(default="2.0.0", description="API version")
    features: Dict[str, bool] = Field(
        default_factory=dict, description="Enabled features"
    )


class ErrorResponse(BaseModel):
    """Error response model."""

    ok: bool = False
    error: str = Field(..., description="Error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional details")
