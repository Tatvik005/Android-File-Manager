"""
main_window.py
Main application window for Android File Manager.
Dual-pane architecture with action bar, status bar, background threads, and error handling.
"""

import os
from pathlib import Path
import subprocess
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QIcon, QKeySequence
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from adb_manager import (
    ANDROID_INTERNAL_STORAGE,
    AdbManager,
    ConnectionState,
    DeviceInfo,
    RemoteFileInfo,
    format_display_remote_path,
    normalize_remote_path,
)
from file_models import LocalFileInfo
from ui_components import (
    FilePane,
    NewFolderDialog,
    SetupGuideDialog,
    StatusIndicator,
    TransferProgressDialog,
    UnauthorizedBanner,
)
from workers import (
    AndroidDeleteWorker,
    AndroidListWorker,
    AndroidMkdirWorker,
    AndroidOpenTempWorker,
    DeviceMonitorWorker,
    TransferDirection,
    TransferWorker,
)


class MainWindow(QMainWindow):
    """Main window of the Android File Manager."""

    def __init__(self, adb_manager: Optional[AdbManager] = None):
        super().__init__()
        self.adb = adb_manager or AdbManager()
        self.current_state = ConnectionState.NO_DEVICE
        self.current_device: Optional[DeviceInfo] = None
        self._unauthorized_alert_shown = False

        # Active workers
        self._list_worker: Optional[AndroidListWorker] = None
        self._transfer_worker: Optional[TransferWorker] = None
        self._progress_dialog: Optional[TransferProgressDialog] = None

        self.setWindowTitle("Android File Manager")
        self.resize(1240, 780)
        self.setMinimumSize(900, 560)

        self._setup_ui()
        self._init_data()
        self._start_device_monitor()

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 10, 12, 8)
        main_layout.setSpacing(8)

        # 1. Top Unauthorized Alert Banner (hidden by default)
        self.unauth_banner = UnauthorizedBanner()
        self.unauth_banner.refresh_requested.connect(self.on_refresh_device_check)
        self.unauth_banner.guide_requested.connect(self.show_setup_guide)
        main_layout.addWidget(self.unauth_banner)

        # 2. Top Action Bar
        action_bar_layout = QHBoxLayout()
        action_bar_layout.setContentsMargins(0, 0, 0, 4)
        action_bar_layout.setSpacing(10)

        # Primary Actions
        self.btn_copy_to_mac = QPushButton("⬇  Copy to Mac (Pull)")
        self.btn_copy_to_mac.setObjectName("primaryActionBtn")
        self.btn_copy_to_mac.setToolTip("Pull selected Android files/folders to the active Mac directory (Cmd+Left)")
        self.btn_copy_to_mac.clicked.connect(self.on_copy_to_mac)
        action_bar_layout.addWidget(self.btn_copy_to_mac)

        self.btn_copy_to_android = QPushButton("⬆  Copy to Android (Push)")
        self.btn_copy_to_android.setObjectName("secondaryActionBtn")
        self.btn_copy_to_android.setToolTip("Push selected Mac files/folders to the active Android directory (Cmd+Right)")
        self.btn_copy_to_android.clicked.connect(self.on_copy_to_android)
        action_bar_layout.addWidget(self.btn_copy_to_android)

        self.btn_delete_android = QPushButton("🗑  Delete on Android")
        self.btn_delete_android.setObjectName("dangerActionBtn")
        self.btn_delete_android.setToolTip("Delete selected items on the Android device")
        self.btn_delete_android.clicked.connect(self.on_delete_android_items)
        action_bar_layout.addWidget(self.btn_delete_android)

        action_bar_layout.addStretch()

        # Extra Action Buttons
        self.btn_new_folder = QPushButton("📁 New Folder (Android)")
        self.btn_new_folder.setToolTip("Create a new folder in current Android directory (⇧⌘N)")
        self.btn_new_folder.clicked.connect(self.on_new_android_folder)
        action_bar_layout.addWidget(self.btn_new_folder)

        self.btn_guide = QPushButton("📖 USB Guide")
        self.btn_guide.setToolTip("Step-by-step guide to enable USB Debugging on your phone")
        self.btn_guide.clicked.connect(self.show_setup_guide)
        action_bar_layout.addWidget(self.btn_guide)

        self.btn_refresh_all = QPushButton("🔄 Refresh All")
        self.btn_refresh_all.setToolTip("Restart ADB & refresh both Mac and Android directories")
        self.btn_refresh_all.clicked.connect(self.on_refresh_both)
        action_bar_layout.addWidget(self.btn_refresh_all)

        main_layout.addLayout(action_bar_layout)

        # 3. Central Dual-Pane Splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(2)

        # Left Pane: Mac Local Files
        self.mac_pane = FilePane(title="💻 Mac Local Files", is_remote=False)
        self.mac_pane.item_double_clicked.connect(self.on_mac_item_double_clicked)
        self.mac_pane.path_bar.navigate_requested.connect(self.load_mac_directory)
        self.mac_pane.path_bar.refresh_requested.connect(self.refresh_mac)
        self.mac_pane.open_context_menu.connect(self.show_mac_context_menu)
        self.mac_pane.selection_changed.connect(self.update_action_states)
        self.mac_pane.new_folder_requested.connect(self.on_new_mac_folder)
        self.splitter.addWidget(self.mac_pane)

        # Right Pane: Android Remote Files
        self.android_pane = FilePane(title="📱 Android Device", is_remote=True)
        self.android_pane.item_double_clicked.connect(self.on_android_item_double_clicked)
        self.android_pane.path_bar.navigate_requested.connect(self.load_android_directory)
        self.android_pane.path_bar.refresh_requested.connect(self.refresh_android)
        self.android_pane.open_context_menu.connect(self.show_android_context_menu)
        self.android_pane.selection_changed.connect(self.update_action_states)
        self.android_pane.new_folder_requested.connect(self.on_new_android_folder)
        self.splitter.addWidget(self.android_pane)

        # Balance splitter 50/50
        self.splitter.setSizes([550, 550])
        main_layout.addWidget(self.splitter, 1)

        # 4. Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        self.status_indicator = StatusIndicator()
        self.status_bar.addWidget(self.status_indicator)

        self.status_device_label = QLabel("Initializing ADB...")
        self.status_device_label.setStyleSheet("font-weight: 500; color: #e5e5ea; padding-left: 4px;")
        self.status_bar.addWidget(self.status_device_label)

        self.status_storage_label = QLabel("")
        self.status_storage_label.setStyleSheet("color: #98989d; font-size: 11px;")
        self.status_bar.addPermanentWidget(self.status_storage_label)

        # Keyboard shortcuts
        self._setup_shortcuts()
        self.update_action_states()

    def _setup_shortcuts(self):
        # Cmd+Left for Pull (Android -> Mac)
        copy_mac_action = QAction(self)
        copy_mac_action.setShortcut(QKeySequence("Ctrl+Left"))
        copy_mac_action.triggered.connect(self.on_copy_to_mac)
        self.addAction(copy_mac_action)

        # Cmd+Right for Push (Mac -> Android)
        copy_android_action = QAction(self)
        copy_android_action.setShortcut(QKeySequence("Ctrl+Right"))
        copy_android_action.triggered.connect(self.on_copy_to_android)
        self.addAction(copy_android_action)

        # Delete key
        delete_action = QAction(self)
        delete_action.setShortcut(QKeySequence.StandardKey.Delete)
        delete_action.triggered.connect(self.on_delete_shortcut)
        self.addAction(delete_action)

        # Spacebar for macOS Quick Look Preview
        space_action = QAction(self)
        space_action.setShortcut(QKeySequence(Qt.Key.Key_Space))
        space_action.triggered.connect(self.on_spacebar_preview)
        self.addAction(space_action)

        # Shift+Cmd+N for New Folder
        new_folder_action = QAction(self)
        new_folder_action.setShortcut(QKeySequence("Ctrl+Shift+N"))
        new_folder_action.triggered.connect(self.on_new_folder_shortcut)
        self.addAction(new_folder_action)

        # Return / Enter key shortcut for opening active pane selected item
        return_action = QAction(self)
        return_action.setShortcut(QKeySequence(Qt.Key.Key_Return))
        return_action.triggered.connect(self.on_return_open_shortcut)
        self.addAction(return_action)

        enter_action = QAction(self)
        enter_action.setShortcut(QKeySequence(Qt.Key.Key_Enter))
        enter_action.triggered.connect(self.on_return_open_shortcut)
        self.addAction(enter_action)

    def _init_data(self):
        # Default Mac pane to User's Home directory
        home_path = str(Path.home())
        self.load_mac_directory(home_path)

        # Default Android path to Internal Storage
        self.android_pane.path_bar.set_path(ANDROID_INTERNAL_STORAGE)

    def _start_device_monitor(self):
        self.monitor = DeviceMonitorWorker(self.adb, interval_sec=1.5, parent=self)
        self.monitor.device_status_changed.connect(self.on_device_status_changed)
        self.monitor.start()

    def closeEvent(self, event):
        if hasattr(self, "monitor"):
            self.monitor.stop()
        super().closeEvent(event)

    # -------------------------------------------------------------
    # Device State Handling
    # -------------------------------------------------------------
    def on_device_status_changed(self, state: ConnectionState, device: Optional[DeviceInfo], msg: str):
        prev_state = self.current_state
        self.current_state = state
        self.current_device = device
        self.status_indicator.set_state(state)

        if state == ConnectionState.CONNECTED:
            self.unauth_banner.setVisible(False)
            self._unauthorized_alert_shown = False
            self.status_device_label.setText(f"Connected: {device.display_name if device else 'Android Device'}")
            dev_model = device.model if device else "Android"
            self.android_pane.title_label.setText(f"📱 {dev_model} • Internal Storage")
            self.update_storage_stats()

            # If newly connected or previously no device, load Android Internal Storage
            if prev_state != ConnectionState.CONNECTED:
                cur_android_path = self.android_pane.current_path
                self.load_android_directory(cur_android_path)

        elif state == ConnectionState.DEBUGGING_DISABLED:
            dev_name = device.model if device else "Android Device"
            self.unauth_banner.set_content(ConnectionState.DEBUGGING_DISABLED, dev_name)
            self.status_device_label.setText(f"USB Device Detected ({dev_name}) — USB Debugging is OFF")
            self.status_storage_label.setText("")
            self.android_pane.title_label.setText(f"📱 {dev_name} (USB Debugging OFF)")
            self.android_pane.model.set_items(self.android_pane.path_bar.path_edit.text(), [])

        elif state == ConnectionState.UNAUTHORIZED:
            self.unauth_banner.set_content(ConnectionState.UNAUTHORIZED)
            self.status_device_label.setText("Device Unauthorized: Tap 'Allow USB Debugging' on phone")
            self.status_storage_label.setText("")
            self.android_pane.title_label.setText("📱 Android (Unauthorized)")
            self.android_pane.model.set_items(self.android_pane.path_bar.path_edit.text(), [])

            # Generate UI alert once per unauthorized occurrence
            if not self._unauthorized_alert_shown:
                self._unauthorized_alert_shown = True
                QMessageBox.warning(
                    self,
                    "USB Debugging Unauthorized",
                    "An Android device was detected, but USB Debugging is not authorized.\n\n"
                    "👉 Please check your physical phone screen and tap 'Allow USB Debugging'.\n"
                    "Tip: Check 'Always allow from this computer' to remember this Mac.",
                )

        elif state == ConnectionState.NO_DEVICE:
            self.unauth_banner.setVisible(False)
            self._unauthorized_alert_shown = False
            self.status_device_label.setText("No Android Device Found (Connect via USB)")
            self.status_storage_label.setText("")
            self.android_pane.title_label.setText("📱 Android Device (Disconnected)")
            self.android_pane.model.set_items(self.android_pane.path_bar.path_edit.text(), [])

        elif state == ConnectionState.OFFLINE:
            self.unauth_banner.setVisible(False)
            self.status_device_label.setText("Android Device Offline")
            self.status_storage_label.setText("")

        self.update_action_states()

    def show_setup_guide(self):
        guide = SetupGuideDialog(self)
        guide.exec()

    def on_refresh_device_check(self):
        self.adb.start_server()
        state, dev, msg = self.adb.get_primary_device()
        self.on_device_status_changed(state, dev, msg)
        if state == ConnectionState.CONNECTED:
            self.refresh_android()

    def update_storage_stats(self):
        stats = self.adb.get_storage_stats(remote_path=ANDROID_INTERNAL_STORAGE)
        if stats:
            self.status_storage_label.setText(
                f"Internal Storage: {stats['free']} free of {stats['size']} ({stats['percent']} used)"
            )
        else:
            self.status_storage_label.setText("")

    # -------------------------------------------------------------
    # Mac Directory Operations
    # -------------------------------------------------------------
    def load_mac_directory(self, path: str):
        p = Path(path)
        if not p.exists() or not p.is_dir():
            QMessageBox.warning(self, "Invalid Directory", f"The directory does not exist:\n{path}")
            return

        self.mac_pane.model.load_directory(str(p))
        self.mac_pane.path_bar.set_path(str(p.resolve()))
        self.mac_pane.update_footer()
        self.update_action_states()

    def refresh_mac(self):
        cur = self.mac_pane.path_bar.path_edit.text()
        if cur:
            self.load_mac_directory(cur)

    def on_mac_item_double_clicked(self, item: LocalFileInfo):
        if item.is_dir:
            self.load_mac_directory(item.path)
        else:
            # Open file with default macOS application
            try:
                subprocess.Popen(["open", item.path])
            except Exception as e:
                QMessageBox.critical(self, "Error Opening File", f"Could not open file: {e}")

    # -------------------------------------------------------------
    # Android Directory Operations
    # -------------------------------------------------------------
    def load_android_directory(self, path: str):
        if self.current_state != ConnectionState.CONNECTED:
            self.status_bar.showMessage("Cannot open folder: Android device is not connected or authorized.", 3500)
            return

        clean_path = normalize_remote_path(path.strip())
        display_name = format_display_remote_path(clean_path)
        self.android_pane.footer_label.setText(f"Loading '{display_name}'...")
        self.status_bar.showMessage(f"Loading '{display_name}' from Android...", 3000)

        # Stop previous list worker if running to prevent race conditions
        if self._list_worker is not None and self._list_worker.isRunning():
            self._list_worker.quit()
            self._list_worker.wait(500)

        # Run async worker
        self._list_worker = AndroidListWorker(self.adb, clean_path, parent=self)
        self._list_worker.listing_finished.connect(self._on_android_listing_finished)
        self._list_worker.listing_failed.connect(self._on_android_listing_failed)
        self._list_worker.start()

    def _on_android_listing_finished(self, path: str, items: List[RemoteFileInfo]):
        self.android_pane.model.set_items(path, items)
        self.android_pane.path_bar.set_path(path)
        self.android_pane.update_footer()
        self.update_action_states()
        display_name = format_display_remote_path(path)
        self.status_bar.showMessage(f"Loaded {len(items)} items in {display_name}", 3000)

    def _on_android_listing_failed(self, path: str, error_msg: str):
        display_name = format_display_remote_path(path)
        self.android_pane.footer_label.setText("Error loading directory")
        self.status_bar.showMessage(f"Failed to access '{display_name}': {error_msg}", 5000)
        QMessageBox.warning(
            self,
            "Android Access Error",
            f"Failed to access '{display_name}' on Android device:\n\n{error_msg}",
        )

    def refresh_android(self):
        cur = self.android_pane.current_path
        self.load_android_directory(cur)
        self.update_storage_stats()

    def on_android_item_double_clicked(self, item: RemoteFileInfo):
        if item.is_dir:
            self.load_android_directory(item.path)
        else:
            # Seamlessly open in macOS default viewer via temporary cache (WITHOUT copying to Mac directory)
            self.open_android_file_temp(item, quick_look=False)

    def open_android_file_temp(self, item: RemoteFileInfo, quick_look: bool = False):
        """
        Opens an Android file in macOS default app or Quick Look via a temporary cache,
        leaving the user's active Mac working directory completely clean and untouched.
        """
        action_desc = "Quick Looking" if quick_look else "Opening"
        self.status_bar.showMessage(f"{action_desc} '{item.name}' from Android...", 4000)

        worker = AndroidOpenTempWorker(
            self.adb,
            remote_path=item.path,
            item_name=item.name,
            expected_size=item.size,
            quick_look=quick_look,
            parent=self,
        )
        worker.ready.connect(self._on_temp_file_ready)
        worker.failed.connect(self._on_temp_file_failed)
        worker.start()

    def _on_temp_file_ready(self, local_temp_path: str, is_quick_look: bool):
        base_name = os.path.basename(local_temp_path)
        try:
            if is_quick_look:
                subprocess.Popen(["qlmanage", "-p", local_temp_path])
                self.status_bar.showMessage(f"Previewing '{base_name}'", 3000)
            else:
                subprocess.Popen(["open", local_temp_path])
                self.status_bar.showMessage(f"Opened '{base_name}'", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Error Opening File", f"Could not launch viewer: {e}")

    def _on_temp_file_failed(self, item_name: str, error_msg: str):
        QMessageBox.warning(
            self,
            "Failed to Open File",
            f"Could not load '{item_name}' from Android:\n\n{error_msg}",
        )

    def on_spacebar_preview(self):
        """macOS Spacebar Quick Look support for both Android and Mac panes."""
        if self.android_pane.table_view.hasFocus():
            selected = self.android_pane.get_selected_items()
            if selected and not selected[0].is_dir:
                self.open_android_file_temp(selected[0], quick_look=True)
        elif self.mac_pane.table_view.hasFocus():
            selected = self.mac_pane.get_selected_items()
            if selected and not selected[0].is_dir:
                subprocess.Popen(["qlmanage", "-p", selected[0].path])

    def on_return_open_shortcut(self):
        """Open the selected item when Return or Enter is pressed on keyboard."""
        focus_widget = QApplication.focusWidget()
        if isinstance(focus_widget, QLineEdit):
            return

        # Prioritize whichever pane has focus or selection
        if self.android_pane.table_view.hasFocus() or (
            not self.mac_pane.table_view.hasFocus() and len(self.android_pane.get_selected_items()) > 0
        ):
            self.android_pane.open_current_or_selected()
        elif self.mac_pane.table_view.hasFocus() or len(self.mac_pane.get_selected_items()) > 0:
            self.mac_pane.open_current_or_selected()

    def on_refresh_both(self):
        self.adb.start_server()
        state, dev, msg = self.adb.get_primary_device()
        self.on_device_status_changed(state, dev, msg)
        self.refresh_mac()
        if self.current_state == ConnectionState.CONNECTED:
            self.refresh_android()

    # -------------------------------------------------------------
    # Transfers (Push & Pull)
    # -------------------------------------------------------------
    def on_copy_to_mac(self):
        """Pull selected Android files/folders to the active Mac directory."""
        if self.current_state != ConnectionState.CONNECTED:
            QMessageBox.warning(self, "No Device", "Please connect and authorize an Android device first.")
            return

        selected_items = self.android_pane.get_selected_items()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select at least one item from the Android pane to copy.")
            return

        mac_dest = self.mac_pane.path_bar.path_edit.text()
        if not os.path.isdir(mac_dest):
            QMessageBox.warning(self, "Invalid Mac Directory", f"The Mac destination directory is invalid:\n{mac_dest}")
            return

        paths = [item.path for item in selected_items]
        self._execute_transfer(TransferDirection.PULL, paths, mac_dest)

    def on_copy_to_android(self):
        """Push selected Mac files/folders to the active Android directory."""
        if self.current_state != ConnectionState.CONNECTED:
            QMessageBox.warning(self, "No Device", "Please connect and authorize an Android device first.")
            return

        selected_items = self.mac_pane.get_selected_items()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select at least one item from the Mac pane to copy.")
            return

        android_dest = self.android_pane.current_path
        paths = [item.path for item in selected_items]
        self._execute_transfer(TransferDirection.PUSH, paths, android_dest)

    def _execute_transfer(
        self,
        direction: TransferDirection,
        source_paths: List[str],
        dest_dir: str,
        auto_open_single: Optional[str] = None,
    ):
        title = "Pushing to Android..." if direction == TransferDirection.PUSH else "Pulling to Mac..."
        self._progress_dialog = TransferProgressDialog(title, parent=self)

        self._transfer_worker = TransferWorker(
            self.adb,
            direction=direction,
            items=source_paths,
            dest_dir=dest_dir,
            parent=self,
        )

        self._progress_dialog.cancelled.connect(self._transfer_worker.cancel)
        self._transfer_worker.progress.connect(self._progress_dialog.update_progress)
        self._transfer_worker.finished.connect(
            lambda ok, succ, fail, errs: self._on_transfer_finished(
                ok, succ, fail, errs, direction, dest_dir, auto_open_single
            )
        )

        self._transfer_worker.start()
        self._progress_dialog.exec()

    def _on_transfer_finished(
        self,
        all_success: bool,
        success_count: int,
        failed_count: int,
        errors: List[str],
        direction: TransferDirection,
        dest_dir: str,
        auto_open_single: Optional[str] = None,
    ):
        if self._progress_dialog:
            self._progress_dialog.close()
            self._progress_dialog = None

        # Refresh the receiving pane
        if direction == TransferDirection.PUSH:
            self.refresh_android()
        else:
            self.refresh_mac()

        if all_success:
            self.status_bar.showMessage(f"Successfully transferred {success_count} item(s).", 4000)
            if auto_open_single:
                target_file = os.path.join(dest_dir, auto_open_single)
                if os.path.exists(target_file):
                    subprocess.Popen(["open", target_file])
        else:
            err_summary = "\n".join(errors[:5])
            if len(errors) > 5:
                err_summary += f"\n...and {len(errors) - 5} more."
            QMessageBox.warning(
                self,
                "Transfer Completed with Errors",
                f"Completed: {success_count} succeeded, {failed_count} failed.\n\nDetails:\n{err_summary}",
            )

    # -------------------------------------------------------------
    # Delete Operations
    # -------------------------------------------------------------
    def on_delete_android_items(self):
        """Delete selected items on Android with confirmation."""
        if self.current_state != ConnectionState.CONNECTED:
            QMessageBox.warning(self, "No Device", "Please connect and authorize an Android device first.")
            return

        selected_items: List[RemoteFileInfo] = self.android_pane.get_selected_items()
        if not selected_items:
            QMessageBox.information(self, "No Selection", "Please select items on Android to delete.")
            return

        count = len(selected_items)
        first_name = selected_items[0].name
        msg = (
            f"Are you sure you want to permanently delete '{first_name}'?"
            if count == 1
            else f"Are you sure you want to permanently delete {count} items on Android?"
        )

        reply = QMessageBox.question(
            self,
            "Confirm Delete on Android",
            msg + "\n\n⚠️ This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        worker = AndroidDeleteWorker(self.adb, selected_items, parent=self)
        worker.finished.connect(self._on_delete_finished)
        worker.start()

    def _on_delete_finished(self, all_success: bool, successes: int, failures: int, errors: List[str]):
        self.refresh_android()
        if all_success:
            self.status_bar.showMessage(f"Successfully deleted {successes} item(s) on Android.", 4000)
        else:
            err_msg = "\n".join(errors[:5])
            QMessageBox.warning(self, "Delete Errors", f"Errors occurred during deletion:\n\n{err_msg}")

    def on_delete_shortcut(self):
        focused = QApplication.focusWidget()
        if self.android_pane.table_view.hasFocus():
            self.on_delete_android_items()
        elif self.mac_pane.table_view.hasFocus():
            self.on_delete_mac_items()

    def on_delete_mac_items(self):
        selected: List[LocalFileInfo] = self.mac_pane.get_selected_items()
        if not selected:
            return

        count = len(selected)
        first_name = selected[0].name
        msg = f"Move '{first_name}' to Trash?" if count == 1 else f"Move {count} items to Trash?"

        reply = QMessageBox.question(
            self,
            "Confirm Delete (Mac)",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            for item in selected:
                try:
                    # Move to Mac Trash via AppleScript or os.remove
                    cmd = f'tell application "Finder" to delete POSIX file "{item.path}"'
                    subprocess.run(["osascript", "-e", cmd], check=True)
                except Exception:
                    # Fallback to direct removal
                    try:
                        if item.is_dir:
                            import shutil
                            shutil.rmtree(item.path)
                        else:
                            os.remove(item.path)
                    except Exception as e:
                        QMessageBox.warning(self, "Error", f"Could not delete {item.name}: {e}")
            self.refresh_mac()

    # -------------------------------------------------------------
    # New Folder
    # -------------------------------------------------------------
    def on_new_folder_shortcut(self):
        """Keyboard shortcut handler (Shift+Cmd+N) for creating folders in active pane."""
        if self.mac_pane.table_view.hasFocus():
            self.on_new_mac_folder()
        else:
            self.on_new_android_folder()

    def on_new_android_folder(self):
        if self.current_state != ConnectionState.CONNECTED:
            QMessageBox.warning(self, "No Device", "Please connect and authorize an Android device first.")
            return

        cur_dir = self.android_pane.current_path
        display_loc = format_display_remote_path(cur_dir)

        dialog = NewFolderDialog(location_display=display_loc, is_remote=True, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            clean_name = dialog.get_folder_name()
            if clean_name:
                new_path = f"{cur_dir.rstrip('/')}/{clean_name}"
                self.status_bar.showMessage(f"Creating folder '{clean_name}' on Android...", 3000)

                worker = AndroidMkdirWorker(self.adb, new_path, parent=self)
                worker.finished.connect(self._on_mkdir_finished)
                worker.start()

    def _on_mkdir_finished(self, success: bool, msg: str):
        if success:
            self.status_bar.showMessage(msg, 3000)
            self.refresh_android()
        else:
            QMessageBox.warning(self, "Error Creating Folder", msg)

    def on_new_mac_folder(self):
        cur_dir = self.mac_pane.path_bar.path_edit.text()
        dialog = NewFolderDialog(location_display=cur_dir, is_remote=False, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            clean_name = dialog.get_folder_name()
            if clean_name:
                target = Path(cur_dir) / clean_name
                try:
                    target.mkdir(parents=True, exist_ok=True)
                    self.status_bar.showMessage(f"Created folder '{clean_name}' on Mac", 3000)
                    self.refresh_mac()
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"Failed to create directory: {e}")

    # -------------------------------------------------------------
    # Context Menus
    # -------------------------------------------------------------
    def show_mac_context_menu(self, pos):
        menu = QMenu(self)
        selected = self.mac_pane.get_selected_items()

        act_push = menu.addAction("⬆ Copy to Android (Push)")
        act_push.setEnabled(self.current_state == ConnectionState.CONNECTED and len(selected) > 0)
        act_push.triggered.connect(self.on_copy_to_android)

        menu.addSeparator()

        if len(selected) == 1:
            item = selected[0]
            if not item.is_dir:
                act_ql = menu.addAction("👁 Quick Look (Space)")
                act_ql.triggered.connect(lambda: subprocess.Popen(["qlmanage", "-p", item.path]))

            act_open = menu.addAction("Open")
            act_open.triggered.connect(lambda: self.on_mac_item_double_clicked(item))

            act_reveal = menu.addAction("Reveal in Finder")
            act_reveal.triggered.connect(lambda: subprocess.run(["open", "-R", item.path]))

        menu.addSeparator()

        act_new_folder = menu.addAction("📁 New Folder...")
        act_new_folder.triggered.connect(self.on_new_mac_folder)

        if selected:
            act_trash = menu.addAction("🗑 Move to Trash")
            act_trash.triggered.connect(self.on_delete_mac_items)

        menu.exec(self.mac_pane.table_view.viewport().mapToGlobal(pos))

    def show_android_context_menu(self, pos):
        menu = QMenu(self)
        selected = self.android_pane.get_selected_items()

        if len(selected) == 1:
            item = selected[0]
            if item.is_dir:
                act_open_dir = menu.addAction("📂 Open Folder")
                act_open_dir.triggered.connect(lambda: self.load_android_directory(item.path))
                menu.addSeparator()
            else:
                act_ql = menu.addAction("👁 Quick Look (Space)")
                act_ql.triggered.connect(lambda: self.open_android_file_temp(item, quick_look=True))

                act_open = menu.addAction("↗ Open in Default Viewer")
                act_open.triggered.connect(lambda: self.open_android_file_temp(item, quick_look=False))

                menu.addSeparator()

        act_pull = menu.addAction("⬇ Save to Mac Active Folder (Pull)")
        act_pull.setEnabled(len(selected) > 0)
        act_pull.triggered.connect(self.on_copy_to_mac)

        menu.addSeparator()

        act_new_dir = menu.addAction("📁 New Folder...")
        act_new_dir.setEnabled(self.current_state == ConnectionState.CONNECTED)
        act_new_dir.triggered.connect(self.on_new_android_folder)

        if len(selected) == 1:
            item = selected[0]
            act_rename = menu.addAction("✏ Rename...")
            act_rename.triggered.connect(lambda: self.on_rename_android_item(item))

            act_copy_path = menu.addAction("📋 Copy Remote Path")
            act_copy_path.triggered.connect(lambda: QApplication.clipboard().setText(item.path))

        if selected:
            menu.addSeparator()
            act_del = menu.addAction("🗑 Delete on Android")
            act_del.triggered.connect(self.on_delete_android_items)

        menu.exec(self.android_pane.table_view.viewport().mapToGlobal(pos))

    def on_rename_android_item(self, item: RemoteFileInfo):
        new_name, ok = QInputDialog.getText(
            self,
            "Rename on Android",
            f"Enter new name for '{item.name}':",
            text=item.name,
        )
        if ok and new_name.strip() and new_name.strip() != item.name:
            parent_dir = item.path.rsplit("/", 1)[0]
            new_path = f"{parent_dir}/{new_name.strip()}"
            try:
                self.adb.rename(item.path, new_path)
                self.refresh_android()
            except Exception as e:
                QMessageBox.warning(self, "Rename Error", f"Failed to rename: {e}")

    # -------------------------------------------------------------
    # Action Button Enable/Disable Logic
    # -------------------------------------------------------------
    def update_action_states(self):
        is_connected = (self.current_state == ConnectionState.CONNECTED)
        has_mac_selection = len(self.mac_pane.get_selected_items()) > 0
        has_android_selection = len(self.android_pane.get_selected_items()) > 0

        self.btn_copy_to_android.setEnabled(is_connected and has_mac_selection)
        self.btn_copy_to_mac.setEnabled(is_connected and has_android_selection)
        self.btn_delete_android.setEnabled(is_connected and has_android_selection)
        self.btn_new_folder.setEnabled(is_connected)
