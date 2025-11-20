"""
API routes for SurgiBot.
Handles health checks, patient list retrieval, and status updates.
"""

from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ...core.database import get_db_session, SurgeryCaseDB, get_all_cases, get_case_by_patient_id, create_case, update_case, delete_case
from ...core.models import (
    HealthResponse,
    Snapshot,
    SnapshotItem,
    StatusUpdate,
    ErrorResponse,
)
from ...config import get_settings
from ...shared.security import mask_hn, validate_token
from ...shared.logging_config import get_api_logger
from ...shared.utils import calculate_eta
from .websocket import broadcast_update

logger = get_api_logger()
router = APIRouter()


def create_snapshot_from_cases(
    cases: List[SurgeryCaseDB], include_hn_full: bool = False
) -> Snapshot:
    """
    Create snapshot from database cases.

    Args:
        cases: List of surgery cases
        include_hn_full: Whether to include full HN (requires authorization)

    Returns:
        Snapshot object
    """
    items: List[SnapshotItem] = []
    now = datetime.now()

    for case in cases:
        # Calculate ETA if applicable
        eta_iso = None
        remaining_seconds = None
        if case.timestamp and case.eta_minutes is not None:
            eta_dt, remaining = calculate_eta(case.timestamp, case.eta_minutes)
            eta_iso = eta_dt.isoformat()
            remaining_seconds = remaining

        # Mask HN for display
        masked_hn = mask_hn(case.hn) if case.hn else str(case.id)

        item = SnapshotItem(
            id=masked_hn,
            hn_full=case.hn if include_hn_full else None,
            patient_id=case.patient_id,
            status=case.status,
            timestamp=case.timestamp.isoformat() if case.timestamp else None,
            eta_minutes=case.eta_minutes,
            eta_time=eta_iso,
            eta_remaining_seconds=remaining_seconds,
        )
        items.append(item)

    # Sort by patient_id
    items.sort(key=lambda x: x.patient_id)

    return Snapshot(
        ok=True,
        items=items,
        version=1,  # Will implement versioning later
        updated_at=datetime.utcnow().isoformat() + "Z",
    )


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.
    Returns server status and timestamp.
    """
    settings = get_settings()
    return HealthResponse(
        ok=True,
        timestamp=datetime.utcnow().isoformat() + "Z",
        version="2.0.0",
        features={
            "websocket": True,
            "sheets": settings.enable_sheets,
            "tts": settings.enable_tts,
            "auto_transitions": settings.enable_auto_transitions,
        },
    )


@router.get("/list", response_model=Snapshot)
async def list_cases(
    token: Optional[str] = Query(None),
    db: Session = Depends(get_db_session),
):
    """
    List all surgery cases.
    If valid token provided, includes full HN. Otherwise returns masked data.
    """
    # Check if authorized
    authorized = token and validate_token(token)

    # Get all cases
    cases = get_all_cases(db)

    # Create snapshot
    snapshot = create_snapshot_from_cases(cases, include_hn_full=authorized)

    logger.info(
        f"Listed {len(cases)} cases (authorized={authorized}, include_hn={authorized})"
    )
    return snapshot


@router.get("/list_full", response_model=Snapshot)
async def list_cases_full(
    token: str = Query(...),
    db: Session = Depends(get_db_session),
):
    """
    List all surgery cases with full HN (requires authentication).
    """
    # Validate token
    if not validate_token(token):
        logger.warning("Unauthorized attempt to access full list")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Get all cases
    cases = get_all_cases(db)

    # Create snapshot with full HN
    snapshot = create_snapshot_from_cases(cases, include_hn_full=True)

    logger.info(f"Listed {len(cases)} cases (full access)")
    return snapshot


@router.post("/update")
async def update_status(
    update: StatusUpdate,
    db: Session = Depends(get_db_session),
):
    """
    Update patient status (add, edit, delete).
    Requires authentication token.
    """
    # Validate token
    if not validate_token(update.token):
        logger.warning(f"Unauthorized update attempt: {update.action}")
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Determine patient_id
    patient_id = update.patient_id
    if not patient_id and update.or_room and update.queue:
        patient_id = f"{update.or_room}-{update.queue}"

    if not patient_id:
        raise HTTPException(status_code=400, detail="Missing patient_id or or_room+queue")

    # Validate HN if provided
    if update.hn:
        hn = update.hn.strip()
        if not hn.isdigit() or len(hn) != 9:
            raise HTTPException(status_code=400, detail="HN must be 9 digits")

    # Handle action
    if update.action == "add":
        # Check if already exists
        existing = get_case_by_patient_id(db, patient_id)
        if existing:
            # Update instead
            logger.info(f"Case {patient_id} already exists, updating instead")
            update_data = {}
            if update.status:
                update_data["status"] = update.status.value
                update_data["timestamp"] = datetime.now()
            if update.eta_minutes is not None:
                update_data["eta_minutes"] = update.eta_minutes
            if update.hn:
                update_data["hn"] = update.hn

            case = update_case(db, patient_id, **update_data)
        else:
            # Create new case
            or_room, queue_str = patient_id.split("-", 1)
            case_data = {
                "patient_id": patient_id,
                "or_room": or_room,
                "queue_number": queue_str,
                "status": update.status.value if update.status else "รอผ่าตัด",
                "timestamp": datetime.now(),
            }
            if update.eta_minutes is not None:
                case_data["eta_minutes"] = update.eta_minutes
            if update.hn:
                case_data["hn"] = update.hn

            case = create_case(db, **case_data)
            logger.info(f"Created new case: {patient_id}")

        # Broadcast update via WebSocket
        await broadcast_update({"action": "add", "patient_id": patient_id, "status": case.status})

    elif update.action == "edit":
        # Update existing case
        case = get_case_by_patient_id(db, patient_id)
        if not case:
            raise HTTPException(status_code=404, detail=f"Case {patient_id} not found")

        update_data = {}
        if update.status:
            update_data["status"] = update.status.value
            update_data["timestamp"] = datetime.now()
        if update.eta_minutes is not None:
            update_data["eta_minutes"] = update.eta_minutes
        if update.hn:
            update_data["hn"] = update.hn

        case = update_case(db, patient_id, **update_data)
        logger.info(f"Updated case: {patient_id}")

        # Broadcast update
        await broadcast_update({"action": "edit", "patient_id": patient_id, "status": case.status})

    elif update.action == "delete":
        # Delete case
        deleted = delete_case(db, patient_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Case {patient_id} not found")

        logger.info(f"Deleted case: {patient_id}")

        # Broadcast update
        await broadcast_update({"action": "delete", "patient_id": patient_id})

    else:
        raise HTTPException(status_code=400, detail=f"Invalid action: {update.action}")

    return {"ok": True, "queued": True, "patient_id": patient_id}
