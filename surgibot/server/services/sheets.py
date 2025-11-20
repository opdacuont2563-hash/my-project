"""
Google Sheets integration service.
Syncs surgery data to Google Sheets with graceful fallback.
"""

import json
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

import gspread
from google.oauth2 import service_account

from ...core.database import get_db, get_all_cases, SurgeryCaseDB
from ...config import get_settings
from ...shared.logging_config import get_logger
from ...shared.security import mask_hn

logger = get_logger("surgibot.sheets")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _normalize_sa_info(raw: str | dict) -> dict:
    """
    Normalize Service Account JSON to proper format.

    Args:
        raw: Service account JSON string or dict

    Returns:
        Normalized service account dict
    """
    if isinstance(raw, str):
        data = json.loads(raw)
    else:
        data = dict(raw)

    # Fix private_key format
    pk = data.get("private_key", "")
    if "\\n" in pk and "-----BEGIN" in pk:
        pk = pk.replace("\\n", "\n")
    pk = pk.strip()

    # Ensure proper PEM format
    if pk.startswith("-----BEGIN PRIVATE KEY-----") and not pk.endswith(
        "-----END PRIVATE KEY-----"
    ):
        if "-----END PRIVATE KEY-----" in pk:
            pk = pk.split("-----END PRIVATE KEY-----")[0] + "-----END PRIVATE KEY-----"

    data["private_key"] = pk
    return data


def _load_service_account_credentials() -> service_account.Credentials:
    """
    Load service account credentials from environment.

    Returns:
        Service account credentials

    Raises:
        RuntimeError: If credentials not found or invalid
    """
    settings = get_settings()

    # Try loading from different sources
    sa_info = None

    if settings.gcp_credentials_json:
        sa_info = _normalize_sa_info(settings.gcp_credentials_json)
    elif settings.gcp_credentials_file:
        path = Path(settings.gcp_credentials_file)
        if path.exists():
            sa_info = _normalize_sa_info(path.read_text(encoding="utf-8"))
    elif settings.embedded_credentials_json:
        sa_info = _normalize_sa_info(settings.embedded_credentials_json)

    if not sa_info:
        raise RuntimeError("No valid service account credentials provided")

    # Validate private key format
    pk = sa_info.get("private_key", "")
    if not (
        pk.startswith("-----BEGIN PRIVATE KEY-----")
        and "-----END PRIVATE KEY-----" in pk
    ):
        raise ValueError("Invalid private_key PEM format")

    # Create credentials
    creds = service_account.Credentials.from_service_account_info(sa_info).with_scopes(
        SCOPES
    )
    return creds


class SheetsService:
    """Service for syncing data to Google Sheets."""

    def __init__(self):
        self.settings = get_settings()
        self.enabled = False
        self.client: Optional[gspread.Client] = None
        self.sheet: Optional[gspread.Worksheet] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def initialize(self) -> bool:
        """
        Initialize Google Sheets connection.

        Returns:
            True if successful, False otherwise
        """
        if not self.settings.enable_sheets:
            logger.info("Google Sheets integration disabled in settings")
            return False

        try:
            creds = _load_service_account_credentials()
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_key(
                self.settings.spreadsheet_id
            ).sheet1

            self.enabled = True
            logger.info("Google Sheets initialized successfully")
            return True

        except Exception as e:
            self.enabled = False
            logger.warning(f"Google Sheets disabled (reason: {e})")
            return False

    async def start(self):
        """Start the sheets sync service."""
        if not await self.initialize():
            logger.info("Sheets service not started (disabled or failed init)")
            return

        if self._running:
            logger.warning("Sheets service already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("Sheets sync service started")

    async def stop(self):
        """Stop the sheets sync service."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("Sheets sync service stopped")

    async def _run_loop(self):
        """Main service loop for syncing to sheets."""
        while self._running:
            try:
                await self.sync_all_cases()
                await asyncio.sleep(60)  # Sync every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sheets sync loop: {e}", exc_info=True)
                await asyncio.sleep(120)  # Wait longer on error

    async def sync_all_cases(self):
        """Sync all surgery cases to Google Sheets."""
        if not self.enabled or not self.sheet:
            return

        try:
            db = get_db()
            with db.get_session() as session:
                cases = get_all_cases(session)

            # Prepare data
            rows = [
                ["ID(mask)", "PatientID", "Status", "StartTime", "ETA(min)", "ETA_Time"]
            ]

            now_str = datetime.now().strftime("%H:%M")
            for case in cases:
                status = case.status or ""
                start_time_str = (
                    case.timestamp.strftime("%H:%M") if case.timestamp else ""
                )
                eta_min = case.eta_minutes
                eta_time_str = ""

                if status == "กำลังพักฟื้น":
                    eta_time_str = now_str  # Current time as ETA
                    eta_min = ""
                elif eta_min is not None and case.timestamp:
                    eta_dt = case.timestamp + timedelta(minutes=eta_min)
                    eta_time_str = eta_dt.strftime("%H:%M")

                rows.append(
                    [
                        mask_hn(case.hn) or str(case.id),
                        case.patient_id,
                        status,
                        start_time_str,
                        eta_min or "",
                        eta_time_str,
                    ]
                )

            # Update sheet
            await asyncio.to_thread(self.sheet.clear)
            await asyncio.to_thread(self.sheet.update, "A1", rows)

            logger.debug(f"Synced {len(cases)} cases to Google Sheets")

        except Exception as e:
            logger.error(f"Error syncing to sheets: {e}", exc_info=True)

    async def sync_config(self):
        """Sync configuration to Config worksheet."""
        if not self.enabled or not self.client:
            return

        try:
            # Get or create Config worksheet
            try:
                ss = self.client.open_by_key(self.settings.spreadsheet_id)
                cfg = ss.worksheet("Config")
            except gspread.exceptions.WorksheetNotFound:
                ss = self.client.open_by_key(self.settings.spreadsheet_id)
                cfg = ss.add_worksheet(title="Config", rows=10, cols=4)

            # Update config values
            await asyncio.to_thread(cfg.clear)
            config_data = [
                ["ANNOUNCE_MIN", self.settings.announce_minutes],
                ["RECOVERY_HOURS", self.settings.recovery_duration_hours],
                ["AUTO_DISCHARGE_MIN", self.settings.auto_discharge_delay_min],
                ["AUTO_DELETE_MIN", self.settings.auto_delete_after_discharge_min],
                ["SERVER_NOW_ISO", datetime.now().isoformat()],
            ]
            await asyncio.to_thread(cfg.update, "A1", config_data)

            logger.debug("Synced configuration to Google Sheets")

        except Exception as e:
            logger.error(f"Error syncing config to sheets: {e}", exc_info=True)


# Global service instance
_sheets_service: Optional[SheetsService] = None


def get_sheets_service() -> SheetsService:
    """Get or create global sheets service instance."""
    global _sheets_service
    if _sheets_service is None:
        _sheets_service = SheetsService()
    return _sheets_service
