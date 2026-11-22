import logging
import time
from pathlib import Path

from sqlalchemy import select
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from app.connectors.fusion import sync_fusion_directory
from app.database import SessionLocal
from app.models import User
from app.security.audit import record_audit

logger = logging.getLogger("fusion_watcher")
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".pdf", ".docx", ".txt", ".html", ".md"}


class FusionFileEventHandler(FileSystemEventHandler):
    """Handles file creation and modification events in data/fusion using watchdog."""

    def __init__(self, directory: Path):
        super().__init__()
        self.directory = directory
        self._last_processed: dict[str, float] = {}

    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._handle_file(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            self._handle_file(Path(event.src_path))

    def _handle_file(self, path: Path):
        if path.suffix.lower() not in ALLOWED_EXTENSIONS or path.name.startswith("."):
            return

        now = time.time()
        # Debounce: avoid processing duplicate events within 2 seconds
        if path.name in self._last_processed and (now - self._last_processed[path.name] < 2.0):
            return
        self._last_processed[path.name] = now

        # Brief pause to allow file write to finish
        time.sleep(0.5)

        logger.info(f"[Watchdog] Detected new/modified Fusion file: {path.name}")
        with SessionLocal() as db:
            admin = db.scalar(select(User).where(User.role == "admin"))
            try:
                synced = sync_fusion_directory(
                    session=db,
                    directory=self.directory,
                    owner=admin,
                    visibility="roles",
                    allowed_roles=["student", "faculty", "management", "admin"],
                )
                if synced:
                    record_audit(
                        db,
                        action="SYNC_FUSION_WATCHDOG",
                        user_id=admin.id if admin else None,
                        details={"file": path.name, "directory": str(self.directory)},
                        ip_address="127.0.0.1",
                    )
                    db.commit()
                    logger.info(f"[Watchdog] Successfully auto-indexed Fusion file: {path.name}")
            except Exception as e:
                logger.error(f"[Watchdog] Failed to ingest {path.name}: {e}", exc_info=True)


class WatchdogManager:
    """Manages the background Watchdog Observer lifecycle."""

    def __init__(self, watch_dir: str = "./data/fusion"):
        self.watch_dir = Path(watch_dir).resolve()
        self.observer: Observer | None = None
        self.is_running = False

    def start(self):
        if self.is_running:
            return
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        handler = FusionFileEventHandler(self.watch_dir)
        self.observer = Observer()
        self.observer.schedule(handler, path=str(self.watch_dir), recursive=True)
        self.observer.daemon = True
        self.observer.start()
        self.is_running = True
        logger.info(f"[Watchdog] Monitoring directory for Fusion exports: {self.watch_dir}")

    def stop(self):
        if self.observer and self.is_running:
            self.observer.stop()
            self.observer.join(timeout=2)
            self.is_running = False
            logger.info("[Watchdog] Observer stopped.")


# Global instance
fusion_watchdog = WatchdogManager()
