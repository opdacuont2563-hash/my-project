"""
Status management service for automatic transitions and business logic.
Handles auto-transitions like recovery -> complete -> discharge.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from sqlalchemy.orm import Session

from ...core.database import (
    get_db,
    get_all_cases,
    get_cases_by_status,
    update_case,
    delete_case,
    SurgeryCaseDB,
)
from ...config import get_settings, STATUS_FLOW
from ...shared.logging_config import get_logger
from ..api.websocket import broadcast_update, broadcast_announcement

logger = get_logger("surgibot.status")


class StatusService:
    """Service for managing status transitions and auto-updates."""

    def __init__(self):
        self.settings = get_settings()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the status management service."""
        if self._running:
            logger.warning("Status service already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Status service started")

    async def stop(self):
        """Stop the status service."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Status service stopped")

    async def _run_loop(self):
        """Main service loop for checking auto-transitions."""
        while self._running:
            try:
                await self.process_auto_transitions()
                await asyncio.sleep(10)  # Check every 10 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in status service loop: {e}", exc_info=True)
                await asyncio.sleep(30)  # Wait longer on error

    async def process_auto_transitions(self):
        """Process all automatic status transitions."""
        db = get_db()
        with db.get_session() as session:
            await self._process_recovery_complete(session)
            await self._process_discharge_ready(session)
            await self._process_auto_delete(session)

    async def _process_recovery_complete(self, session: Session):
        """
        Auto-transition: กำลังพักฟื้น -> พักฟื้นครบแล้ว
        After 1 hour in recovery.
        """
        if not self.settings.enable_auto_transitions:
            return

        cases = get_cases_by_status(session, "กำลังพักฟื้น")
        now = datetime.now()
        recovery_duration = timedelta(hours=self.settings.recovery_duration_hours)

        for case in cases:
            if not case.timestamp:
                continue

            # Check if recovery time elapsed
            elapsed = now - case.timestamp
            if elapsed >= recovery_duration:
                # Transition to recovery complete
                logger.info(
                    f"Auto-transition {case.patient_id}: กำลังพักฟื้น -> พักฟื้นครบแล้ว"
                )

                update_case(
                    session,
                    case.patient_id,
                    status="พักฟื้นครบแล้ว",
                    timestamp=now,
                    auto_to_discharge_at=now
                    + timedelta(minutes=self.settings.auto_discharge_delay_min),
                )

                # Broadcast update
                await broadcast_update(
                    {
                        "action": "status_change",
                        "patient_id": case.patient_id,
                        "status": "พักฟื้นครบแล้ว",
                        "auto": True,
                    }
                )

    async def _process_discharge_ready(self, session: Session):
        """
        Auto-transition: พักฟื้นครบแล้ว -> กำลังส่งกลับตึก
        After configured delay (~3 minutes).
        """
        if not self.settings.enable_auto_transitions:
            return

        cases = get_cases_by_status(session, "พักฟื้นครบแล้ว")
        now = datetime.now()

        for case in cases:
            if not case.auto_to_discharge_at:
                # Set auto discharge time if not set
                update_case(
                    session,
                    case.patient_id,
                    auto_to_discharge_at=now
                    + timedelta(minutes=self.settings.auto_discharge_delay_min),
                )
                continue

            # Check if ready to discharge
            if now >= case.auto_to_discharge_at:
                logger.info(
                    f"Auto-transition {case.patient_id}: พักฟื้นครบแล้ว -> กำลังส่งกลับตึก"
                )

                update_case(
                    session,
                    case.patient_id,
                    status="กำลังส่งกลับตึก",
                    timestamp=now,
                    auto_to_discharge_at=None,
                    auto_delete_at=now
                    + timedelta(minutes=self.settings.auto_delete_after_discharge_min),
                )

                # Broadcast update
                await broadcast_update(
                    {
                        "action": "status_change",
                        "patient_id": case.patient_id,
                        "status": "กำลังส่งกลับตึก",
                        "auto": True,
                    }
                )

    async def _process_auto_delete(self, session: Session):
        """
        Auto-delete: กำลังส่งกลับตึก
        After configured delay (~3 minutes) and if feature enabled.
        """
        if not self.settings.enable_auto_transitions:
            return

        cases = get_cases_by_status(session, "กำลังส่งกลับตึก")
        now = datetime.now()

        for case in cases:
            if not case.auto_delete_at:
                # Set auto delete time if not set
                update_case(
                    session,
                    case.patient_id,
                    auto_delete_at=now
                    + timedelta(minutes=self.settings.auto_delete_after_discharge_min),
                )
                continue

            # Check if ready to delete
            if now >= case.auto_delete_at:
                logger.info(f"Auto-delete {case.patient_id} after discharge")

                delete_case(session, case.patient_id)

                # Broadcast update
                await broadcast_update(
                    {
                        "action": "delete",
                        "patient_id": case.patient_id,
                        "auto": True,
                    }
                )

    def can_transition(self, from_status: str, to_status: str) -> bool:
        """
        Check if status transition is valid.

        Args:
            from_status: Current status
            to_status: Target status

        Returns:
            True if transition is allowed
        """
        if from_status not in STATUS_FLOW or to_status not in STATUS_FLOW:
            return False

        # Allow transition to postponed from any status
        if to_status == "เลื่อนการผ่าตัด":
            return True

        # Allow transition back to waiting from postponed
        if from_status == "เลื่อนการผ่าตัด" and to_status == "รอผ่าตัด":
            return True

        # Check if transition follows the flow
        from_idx = STATUS_FLOW.index(from_status)
        to_idx = STATUS_FLOW.index(to_status)

        # Allow forward transitions only (except special cases above)
        return to_idx > from_idx


# Global service instance
_status_service: Optional[StatusService] = None


def get_status_service() -> StatusService:
    """Get or create global status service instance."""
    global _status_service
    if _status_service is None:
        _status_service = StatusService()
    return _status_service
