"""
workers.py
Asynchronous QThread workers for ADB commands, transfers, and background device polling.
"""

from enum import Enum
import os
from pathlib import Path
import tempfile
import time
from typing import List, Optional

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from adb_manager import AdbError, AdbManager, ConnectionState, DeviceInfo, RemoteFileInfo


class TransferDirection(Enum):
    PUSH = "push"  # Mac to Android
    PULL = "pull"  # Android to Mac


class DeviceMonitorWorker(QThread):
    """
    Background worker that continuously polls for connected Android devices.
    Emits status signals without freezing the GUI.
    """
    device_status_changed = pyqtSignal(object, object, str)  # (ConnectionState, DeviceInfo or None, msg)
    devices_updated = pyqtSignal(list)                       # List[DeviceInfo]

    def __init__(self, adb: AdbManager, interval_sec: float = 2.0, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.interval = interval_sec
        self._running = True
        self._last_state: Optional[ConnectionState] = None
        self._last_serial: Optional[str] = None

    def run(self):
        while self._running:
            try:
                devices = self.adb.list_devices()
                state, primary_dev, msg = self.adb.get_primary_device()

                # Always emit devices list
                self.devices_updated.emit(devices)

                # Emit if changed or on first check
                cur_serial = primary_dev.serial if primary_dev else None
                if state != self._last_state or cur_serial != self._last_serial:
                    self._last_state = state
                    self._last_serial = cur_serial
                    self.device_status_changed.emit(state, primary_dev, msg)
            except Exception as e:
                self.device_status_changed.emit(ConnectionState.ERROR, None, str(e))

            # Sleep in small increments for responsive stop
            for _ in range(int(self.interval * 10)):
                if not self._running:
                    break
                time.sleep(0.1)

    def stop(self):
        self._running = False
        self.quit()
        self.wait(2000)


class AndroidListWorker(QThread):
    """Worker to list files in an Android directory asynchronously."""
    listing_finished = pyqtSignal(str, list)   # (path, List[RemoteFileInfo])
    listing_failed = pyqtSignal(str, str)      # (path, error_msg)

    def __init__(self, adb: AdbManager, path: str, serial: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.path = path
        self.serial = serial

    def run(self):
        try:
            items = self.adb.list_files(self.path, serial=self.serial)
            self.listing_finished.emit(self.path, items)
        except Exception as e:
            self.listing_failed.emit(self.path, str(e))


class TransferWorker(QThread):
    """
    Worker to push or pull files and folders asynchronously.
    Emits progress and handles cancellation.
    """
    progress = pyqtSignal(int, int, str, str)  # (current_index, total_count, item_name, detail)
    finished = pyqtSignal(bool, int, int, list) # (all_success, success_count, fail_count, error_messages)

    def __init__(
        self,
        adb: AdbManager,
        direction: TransferDirection,
        items: List[str],  # list of source paths
        dest_dir: str,
        serial: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.adb = adb
        self.direction = direction
        self.items = items
        self.dest_dir = dest_dir
        self.serial = serial
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.items)
        successes = 0
        failures = 0
        errors = []

        for idx, src_path in enumerate(self.items, start=1):
            if self._cancelled:
                errors.append("Transfer cancelled by user.")
                break

            base_name = os.path.basename(src_path.rstrip("/\\"))
            self.progress.emit(idx, total, base_name, f"Transferring {idx} of {total}...")

            try:
                if self.direction == TransferDirection.PUSH:
                    # Mac -> Android
                    # Ensure destination is remote dir path
                    remote_dest = self.dest_dir
                    if not remote_dest.endswith("/"):
                        remote_dest += "/"
                    self.adb.push(src_path, remote_dest, serial=self.serial)
                else:
                    # Android -> Mac
                    local_dest = self.dest_dir
                    self.adb.pull(src_path, local_dest, serial=self.serial)

                successes += 1
            except Exception as e:
                failures += 1
                errors.append(f"{base_name}: {str(e)}")

        all_success = (failures == 0 and not self._cancelled)
        self.finished.emit(all_success, successes, failures, errors)


class AndroidDeleteWorker(QThread):
    """Worker to delete Android files or directories."""
    finished = pyqtSignal(bool, int, int, list)

    def __init__(self, adb: AdbManager, items: List[RemoteFileInfo], serial: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.items = items
        self.serial = serial

    def run(self):
        successes = 0
        failures = 0
        errors = []

        for item in self.items:
            try:
                self.adb.delete(item.path, is_dir=item.is_dir, serial=self.serial)
                successes += 1
            except Exception as e:
                failures += 1
                errors.append(f"{item.name}: {str(e)}")

        self.finished.emit(failures == 0, successes, failures, errors)


class AndroidMkdirWorker(QThread):
    """Worker to create a directory on Android."""
    finished = pyqtSignal(bool, str)

    def __init__(self, adb: AdbManager, path: str, serial: Optional[str] = None, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.path = path
        self.serial = serial

    def run(self):
        try:
            self.adb.mkdir(self.path, serial=self.serial)
            self.finished.emit(True, f"Created directory '{self.path}'")
        except Exception as e:
            self.finished.emit(False, str(e))


class AndroidOpenTempWorker(QThread):
    """
    Worker to pull a remote Android file to a temporary cache location
    and notify when ready to open in macOS default application or Quick Look.
    Does NOT touch or pollute the user's active Mac working directory.
    """
    ready = pyqtSignal(str, bool)   # (local_temp_path, is_quick_look)
    failed = pyqtSignal(str, str)   # (item_name, error_msg)

    def __init__(
        self,
        adb: AdbManager,
        remote_path: str,
        item_name: str,
        expected_size: int = 0,
        quick_look: bool = False,
        serial: Optional[str] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.adb = adb
        self.remote_path = remote_path
        self.item_name = item_name
        self.expected_size = expected_size
        self.quick_look = quick_look
        self.serial = serial

    def run(self):
        try:
            cache_dir = os.path.join(tempfile.gettempdir(), "AndroidFileManager_TempCache")
            os.makedirs(cache_dir, exist_ok=True)
            local_path = os.path.join(cache_dir, self.item_name)

            need_download = True
            if os.path.exists(local_path) and self.expected_size > 0:
                if os.path.getsize(local_path) == self.expected_size:
                    need_download = False

            if need_download:
                self.adb.pull(self.remote_path, local_path, serial=self.serial)

            self.ready.emit(local_path, self.quick_look)
        except Exception as e:
            self.failed.emit(self.item_name, str(e))
