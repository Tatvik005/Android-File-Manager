"""
ui_components.py
Enhanced macOS-style UI widgets for Android File Manager:
- PathBar (navigation and shortcuts)
- StatusIndicator (LED connection dot)
- UnauthorizedBanner (actionable warning banner)
- SetupGuideDialog (interactive setup guide)
- FilePane (complete file browser pane with search, shortcut pills, and modern table)
- TransferProgressDialog (dialog with cancel button)
"""

import os
from pathlib import Path
from typing import Any, List, Optional, Tuple

from PyQt6.QtCore import QEvent, QPoint, QRegularExpression, QSettings, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeyEvent, QPainter, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from adb_manager import (
    ANDROID_INTERNAL_STORAGE,
    ConnectionState,
    DeviceInfo,
    RemoteFileInfo,
    StorageVolume,
    format_display_remote_path,
    normalize_remote_path,
)
from workers import WirelessWorker
from file_models import (
    BaseFileTableModel,
    FileFilterProxyModel,
    LocalFileInfo,
    LocalFileTableModel,
    RemoteFileTableModel,
)


class StatusIndicator(QWidget):
    """Circular LED status light indicating USB connection state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self._state = ConnectionState.NO_DEVICE

    def set_state(self, state: ConnectionState):
        self._state = state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._state == ConnectionState.CONNECTED:
            color = QColor("#30d158")  # Green
            border = QColor("#249940")
        elif self._state in (ConnectionState.UNAUTHORIZED, ConnectionState.DEBUGGING_DISABLED):
            color = QColor("#ffd60a")  # Amber / Yellow
            border = QColor("#b39500")
        elif self._state == ConnectionState.OFFLINE:
            color = QColor("#8e8e93")  # Gray
            border = QColor("#636366")
        else:
            color = QColor("#ff453a")  # Red
            border = QColor("#b3261e")

        painter.setBrush(color)
        painter.setPen(border)
        painter.drawEllipse(1, 1, 12, 12)


class UnauthorizedBanner(QFrame):
    """Top warning banner shown when Android device is unauthorized or debugging is off."""

    refresh_requested = pyqtSignal()
    guide_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bannerFrame")
        self.setVisible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(12)

        self.icon_label = QLabel("⚠️")
        self.icon_label.setStyleSheet("font-size: 22px;")
        layout.addWidget(self.icon_label)

        self.text_label = QLabel("")
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("color: #ffeb99; font-size: 13px; line-height: 1.4;")
        layout.addWidget(self.text_label, 1)

        self.btn_guide = QPushButton("📖 USB Guide")
        self.btn_guide.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_guide.setStyleSheet(
            "background-color: #3b3c48; color: #f2f2f7; font-weight: 600; padding: 7px 14px; border: 1px solid #545668; border-radius: 6px;"
        )
        self.btn_guide.clicked.connect(self.guide_requested.emit)
        layout.addWidget(self.btn_guide)

        self.btn_refresh = QPushButton("Check Again")
        self.btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_refresh.setStyleSheet(
            "background-color: #ffd60a; color: #1a1a1e; font-weight: bold; padding: 7px 16px; border: none; border-radius: 6px;"
        )
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self.btn_refresh)

    def set_content(self, state: ConnectionState, device_name: str = "Android Device"):
        if state == ConnectionState.DEBUGGING_DISABLED:
            self.text_label.setText(
                f"<b>{device_name} Connected via USB (USB Debugging is OFF):</b> "
                "To access and transfer files, please turn ON <b>USB Debugging</b> in your phone's Developer Options."
            )
            self.btn_guide.setVisible(True)
            self.setVisible(True)
        elif state == ConnectionState.UNAUTHORIZED:
            self.text_label.setText(
                "<b>USB Debugging Unauthorized:</b> Please check your phone screen and tap <b>'Allow USB Debugging'</b>. "
                "Check 'Always allow from this computer'."
            )
            self.btn_guide.setVisible(False)
            self.setVisible(True)
        else:
            self.setVisible(False)


class SetupGuideDialog(QDialog):
    """Step-by-step setup guide dialog for enabling USB debugging."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enable USB Debugging Guide")
        self.resize(540, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("📱 How to Enable USB Debugging")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Android requires USB Debugging to be enabled once before your Mac can transfer files over USB."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #9898a4; font-size: 13px;")
        layout.addWidget(subtitle)

        guide_frame = QFrame()
        guide_frame.setStyleSheet(
            "background-color: #1e1f27; border: 1px solid #31333f; border-radius: 9px; padding: 14px;"
        )
        guide_layout = QVBoxLayout(guide_frame)
        guide_layout.setSpacing(12)

        steps = [
            ("1. Enable Developer Options",
             "Open phone <b>Settings</b> ➔ <b>About phone</b> (or <i>About device</i>) ➔ <b>Software information</b>.<br>"
             "Tap <b>Build number</b> rapidly <b>7 times</b> until it says <i>'Developer mode has been enabled'</i>."),
            ("2. Turn ON USB Debugging",
             "Go back to main <b>Settings</b> ➔ scroll to bottom ➔ tap <b>Developer options</b>.<br>"
             "Find <b>USB debugging</b> and toggle the switch to <b>ON</b>. Tap <b>OK</b> to confirm."),
            ("3. Authorize Your Mac",
             "Unplug and plug your USB cable back in.<br>"
             "Look at your phone screen for: <b>'Allow USB debugging?'</b><br>"
             "Check the box <b>'Always allow from this computer'</b> and tap <b>Allow</b>."),
            ("4. Check USB Connection Mode",
             "Swipe down notifications, tap <b>'Charging via USB'</b>, and select <b>'Transferring files' (MTP)</b>."),
        ]

        for step_title, step_desc in steps:
            step_label = QLabel(f"<b style='color: #0071e3; font-size: 13px;'>{step_title}</b><br><span style='color: #e2e2e8; font-size: 12px;'>{step_desc}</span>")
            step_label.setWordWrap(True)
            guide_layout.addWidget(step_label)

        layout.addWidget(guide_frame)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Got It, Close")
        btn_close.setObjectName("primaryActionBtn")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


class WifiConnectDialog(QDialog):
    """
    High-end dialog for one-click USB-to-Wi-Fi switching (Method 1)
    as well as direct wireless connection and Android 11+ pairing.
    """
    connection_succeeded = pyqtSignal(str)  # (ip_port)

    def __init__(self, adb: Any, current_device: Optional[DeviceInfo] = None, parent=None):
        super().__init__(parent)
        self.adb = adb
        self.current_device = current_device
        self._worker: Optional[WirelessWorker] = None
        self.settings = QSettings("AndroidFileManager", "Preferences")

        self.setWindowTitle("📶 Connect Wirelessly (Wi-Fi)")
        self.resize(560, 520)
        self.setMinimumWidth(520)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Header Title
        title = QLabel("📶 Android Wireless Connection")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Manage and transfer your Android files without a USB cable over your local Wi-Fi network."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #9898a4; font-size: 13px;")
        layout.addWidget(subtitle)

        # Tabs Container
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # --- TAB 1: ⚡ One-Click Switch (Method 1) ---
        tab_switch = QWidget()
        tab_switch_layout = QVBoxLayout(tab_switch)
        tab_switch_layout.setContentsMargins(16, 16, 16, 16)
        tab_switch_layout.setSpacing(12)

        is_usb_connected = (
            self.current_device is not None
            and self.current_device.state == ConnectionState.CONNECTED
            and not self.current_device.is_wireless
        )
        is_already_wireless = (
            self.current_device is not None
            and self.current_device.state == ConnectionState.CONNECTED
            and self.current_device.is_wireless
        )

        card_switch = QFrame()
        card_switch.setStyleSheet(
            "background-color: #1e1f27; border: 1px solid #31333f; border-radius: 9px; padding: 14px;"
        )
        card_layout = QVBoxLayout(card_switch)
        card_layout.setSpacing(10)

        if is_usb_connected:
            dev_name = self.current_device.display_name if self.current_device else "Android Device"
            card_layout.addWidget(QLabel(f"<span style='color: #10b981; font-weight: bold;'>🔌 USB Device Connected:</span> <b style='color: #ffffff;'>{dev_name}</b>"))

            ip_row = QHBoxLayout()
            ip_row.addWidget(QLabel("Phone Wi-Fi IP:"))
            self.txt_usb_ip = QLineEdit()
            self.txt_usb_ip.setPlaceholderText("Auto-detecting...")
            # Query auto-detected IP
            detected_ip = self.adb.get_device_ip(self.current_device.serial if self.current_device else None)
            if detected_ip:
                self.txt_usb_ip.setText(detected_ip)
            else:
                saved_ip = self.settings.value("last_wifi_ip", "")
                if saved_ip:
                    self.txt_usb_ip.setText(saved_ip)
            ip_row.addWidget(self.txt_usb_ip)
            card_layout.addLayout(ip_row)

            self.btn_switch = QPushButton("⚡ Switch to Wi-Fi Mode (One-Click)")
            self.btn_switch.setObjectName("wifiActionBtn")
            self.btn_switch.setFixedHeight(36)
            self.btn_switch.clicked.connect(self.on_switch_clicked)
            card_layout.addWidget(self.btn_switch)

            hint = QLabel(
                "👉 <b>One-Click Setup:</b> Enables wireless mode on your phone and connects your Mac.<br>"
                "<b>You can safely unplug the USB cable immediately after clicking!</b>"
            )
            hint.setWordWrap(True)
            hint.setStyleSheet("color: #9ca3af; font-size: 12px; margin-top: 4px;")
            card_layout.addWidget(hint)

        elif is_already_wireless:
            dev_name = self.current_device.display_name if self.current_device else "Android Device"
            card_layout.addWidget(QLabel(f"<span style='color: #10b981; font-weight: bold;'>🟢 Active Wi-Fi Connection:</span> <b style='color: #ffffff;'>{dev_name}</b>"))
            info_lbl = QLabel("You are currently managing this device wirelessly over Wi-Fi without any USB cable!")
            info_lbl.setStyleSheet("color: #d1d5db; font-size: 13px;")
            card_layout.addWidget(info_lbl)

            self.btn_disconnect_active = QPushButton("🔌 Disconnect Wireless Session")
            self.btn_disconnect_active.setObjectName("dangerActionBtn")
            self.btn_disconnect_active.clicked.connect(self.on_direct_disconnect_clicked)
            card_layout.addWidget(self.btn_disconnect_active)

        else:
            no_usb_title = QLabel("<b style='color: #fbbf24; font-size: 14px;'>🔌 No USB Phone Connected</b>")
            card_layout.addWidget(no_usb_title)
            no_usb_desc = QLabel(
                "To use <b>One-Click Switch</b>, connect your phone via USB cable once with USB Debugging turned ON.<br><br>"
                "If your phone was already configured for wireless mode earlier or you know its IP address, "
                "switch to the <b>Direct Connect</b> tab to connect wirelessly without plugging in."
            )
            no_usb_desc.setWordWrap(True)
            no_usb_desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
            card_layout.addWidget(no_usb_desc)

        tab_switch_layout.addWidget(card_switch)
        tab_switch_layout.addStretch()
        self.tabs.addTab(tab_switch, "⚡ One-Click Switch")

        # --- TAB 2: 🔗 Direct Connect / Reconnect ---
        tab_direct = QWidget()
        tab_direct_layout = QVBoxLayout(tab_direct)
        tab_direct_layout.setContentsMargins(16, 16, 16, 16)
        tab_direct_layout.setSpacing(12)

        card_direct = QFrame()
        card_direct.setStyleSheet(
            "background-color: #1e1f27; border: 1px solid #31333f; border-radius: 9px; padding: 14px;"
        )
        card_direct_layout = QVBoxLayout(card_direct)
        card_direct_layout.setSpacing(10)

        card_direct_layout.addWidget(QLabel("<b style='color: #ffffff;'>Connect by IP Address:</b>"))

        row_direct = QHBoxLayout()
        row_direct.addWidget(QLabel("Phone IP:"))
        self.txt_direct_ip = QLineEdit()
        self.txt_direct_ip.setPlaceholderText("e.g. 192.168.1.45")
        saved_ip = self.settings.value("last_wifi_ip", "")
        if saved_ip:
            self.txt_direct_ip.setText(saved_ip)
        row_direct.addWidget(self.txt_direct_ip, 3)

        row_direct.addWidget(QLabel("Port:"))
        self.txt_direct_port = QLineEdit()
        self.txt_direct_port.setFixedWidth(70)
        self.txt_direct_port.setText(self.settings.value("last_wifi_port", "5555"))
        row_direct.addWidget(self.txt_direct_port, 1)
        card_direct_layout.addLayout(row_direct)

        btns_row = QHBoxLayout()
        self.btn_direct_connect = QPushButton("⚡ Connect Wirelessly")
        self.btn_direct_connect.setObjectName("wifiActionBtn")
        self.btn_direct_connect.clicked.connect(self.on_direct_connect_clicked)
        btns_row.addWidget(self.btn_direct_connect)

        self.btn_disconnect_all = QPushButton("Disconnect All")
        self.btn_disconnect_all.clicked.connect(self.on_direct_disconnect_clicked)
        btns_row.addWidget(self.btn_disconnect_all)
        card_direct_layout.addLayout(btns_row)

        direct_tip = QLabel(
            "💡 <b>Tip:</b> If your phone's IP changes when reconnecting to Wi-Fi, you can find the current IP on your phone in "
            "<b>Settings ➔ About Phone ➔ Status ➔ IP Address</b>."
        )
        direct_tip.setWordWrap(True)
        direct_tip.setStyleSheet("color: #9ca3af; font-size: 12px;")
        card_direct_layout.addWidget(direct_tip)

        tab_direct_layout.addWidget(card_direct)
        tab_direct_layout.addStretch()
        self.tabs.addTab(tab_direct, "🔗 Direct Connect")

        # --- TAB 3: 📱 Cable-Free Pairing (Android 11+) ---
        tab_pair = QWidget()
        tab_pair_layout = QVBoxLayout(tab_pair)
        tab_pair_layout.setContentsMargins(16, 16, 16, 16)
        tab_pair_layout.setSpacing(12)

        card_pair = QFrame()
        card_pair.setStyleSheet(
            "background-color: #1e1f27; border: 1px solid #31333f; border-radius: 9px; padding: 14px;"
        )
        card_pair_layout = QVBoxLayout(card_pair)
        card_pair_layout.setSpacing(10)

        card_pair_layout.addWidget(QLabel("<b style='color: #ffffff;'>Pair Device Wirelessly (No Cable Required):</b>"))

        pair_row1 = QHBoxLayout()
        pair_row1.addWidget(QLabel("Pairing IP & Port:"))
        self.txt_pair_host = QLineEdit()
        self.txt_pair_host.setPlaceholderText("e.g. 192.168.1.45:38475")
        pair_row1.addWidget(self.txt_pair_host)
        card_pair_layout.addLayout(pair_row1)

        pair_row2 = QHBoxLayout()
        pair_row2.addWidget(QLabel("6-Digit Pairing Code:"))
        self.txt_pair_code = QLineEdit()
        self.txt_pair_code.setPlaceholderText("e.g. 123456")
        pair_row2.addWidget(self.txt_pair_code)
        card_pair_layout.addLayout(pair_row2)

        self.btn_pair = QPushButton("Pair Device")
        self.btn_pair.setObjectName("primaryActionBtn")
        self.btn_pair.clicked.connect(self.on_pair_clicked)
        card_pair_layout.addWidget(self.btn_pair)

        pair_steps = QLabel(
            "1. On phone: <b>Settings ➔ Developer Options ➔ Wireless Debugging</b> (toggle ON).<br>"
            "2. Tap <b>'Wireless debugging'</b> ➔ tap <b>'Pair device with pairing code'</b>.<br>"
            "3. Enter the Pairing IP:Port and 6-digit code shown on your phone screen above, then click Pair."
        )
        pair_steps.setWordWrap(True)
        pair_steps.setStyleSheet("color: #9ca3af; font-size: 12px;")
        card_pair_layout.addWidget(pair_steps)

        tab_pair_layout.addWidget(card_pair)
        tab_pair_layout.addStretch()
        self.tabs.addTab(tab_pair, "📱 Cable-Free Pairing")

        # Status & Progress Area
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 13px; font-weight: 500; min-height: 22px;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Animated marquee
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Bottom Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def on_switch_clicked(self):
        target_ip = self.txt_usb_ip.text().strip()
        serial = self.current_device.serial if self.current_device else None
        self._start_worker(
            WirelessWorker.OP_SWITCH_USB_TO_WIFI,
            serial=serial,
            ip=target_ip or None,
            port=5555,
        )

    def on_direct_connect_clicked(self):
        ip = self.txt_direct_ip.text().strip()
        if not ip:
            self.status_label.setText("<span style='color: #ef4444;'>Please enter an IP address.</span>")
            return
        port_str = self.txt_direct_port.text().strip() or "5555"
        try:
            port = int(port_str)
        except ValueError:
            port = 5555
        self._start_worker(
            WirelessWorker.OP_CONNECT,
            ip=ip,
            port=port,
        )

    def on_direct_disconnect_clicked(self):
        self._start_worker(WirelessWorker.OP_DISCONNECT)

    def on_pair_clicked(self):
        host = self.txt_pair_host.text().strip()
        code = self.txt_pair_code.text().strip()
        if not host or not code:
            self.status_label.setText("<span style='color: #ef4444;'>Host:port and pairing code are required.</span>")
            return
        self._start_worker(
            WirelessWorker.OP_PAIR,
            ip=host,
            pair_code=code,
        )

    def _start_worker(self, op: str, **kwargs):
        self._set_ui_busy(True)
        self.progress_bar.setVisible(True)
        self.status_label.setText("⏳ Connecting...")

        self._worker = WirelessWorker(self.adb, op, **kwargs)
        self._worker.progress.connect(self.on_worker_progress)
        self._worker.finished.connect(self.on_worker_finished)
        self._worker.start()

    def _set_ui_busy(self, busy: bool):
        self.tabs.setEnabled(not busy)

    def on_worker_progress(self, msg: str):
        self.status_label.setText(f"⏳ {msg}")

    def on_worker_finished(self, success: bool, msg: str):
        self._set_ui_busy(False)
        self.progress_bar.setVisible(False)

        if success:
            self.status_label.setText(f"<span style='color: #10b981;'>{msg}</span>")

            # Save IP for fast reconnects
            ip_to_save = getattr(self._worker, "ip", None)
            if ip_to_save and ":" in ip_to_save:
                ip_only = ip_to_save.split(":")[0]
                self.settings.setValue("last_wifi_ip", ip_only)
            elif ip_to_save:
                self.settings.setValue("last_wifi_ip", ip_to_save)

            target = f"{self._worker.ip}:{self._worker.port}" if self._worker and self._worker.ip else ""
            self.connection_succeeded.emit(target)

            if self._worker and self._worker.operation == WirelessWorker.OP_SWITCH_USB_TO_WIFI:
                QMessageBox.information(
                    self,
                    "Wireless Mode Activated!",
                    "🎉 Android File Manager is now connected to your phone over Wi-Fi!\n\n"
                    "👉 You can now safely UNPLUG your USB cable and continue browsing or transferring files wirelessly.",
                )
                self.accept()
        else:
            self.status_label.setText(f"<span style='color: #ef4444;'>❌ {msg}</span>")


class NewFolderDialog(QDialog):
    """Modern dialog to create a new folder with clean validation."""

    def __init__(self, location_display: str, is_remote: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Folder")
        self.setFixedWidth(430)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(12)

        title_text = "📁 Create Folder on Android" if is_remote else "📁 Create Folder on Mac"
        title_lbl = QLabel(title_text)
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title_lbl)

        loc_lbl = QLabel(f"Location: <span style='color: #0071e3;'><b>{location_display}</b></span>")
        loc_lbl.setStyleSheet("color: #9898a4; font-size: 12px;")
        loc_lbl.setWordWrap(True)
        layout.addWidget(loc_lbl)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Enter folder name...")
        self.name_edit.setText("New Folder")
        self.name_edit.selectAll()
        self.name_edit.returnPressed.connect(self.on_create_clicked)
        layout.addWidget(self.name_edit)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")
        layout.addWidget(self.error_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        self.btn_create = QPushButton("Create Folder")
        self.btn_create.setObjectName("primaryActionBtn")
        self.btn_create.clicked.connect(self.on_create_clicked)
        btn_layout.addWidget(self.btn_create)

        layout.addLayout(btn_layout)

    def on_create_clicked(self):
        name = self.name_edit.text().strip()
        if not name:
            self.error_label.setText("Folder name cannot be empty.")
            return
        if any(c in name for c in '/\\:*?"<>|'):
            self.error_label.setText('Folder name cannot contain / \\ : * ? " < > |')
            return
        self.accept()

    def get_folder_name(self) -> str:
        return self.name_edit.text().strip()


def get_mac_volumes() -> List[Tuple[str, str, bool]]:
    """
    Discover all mounted external volumes on macOS:
    Returns list of (display_label, absolute_path, is_removable).
    e.g. [('💾 SD', '/Volumes/SD', True), ('💽 USB_DRIVE', '/Volumes/USB_DRIVE', True)]
    """
    volumes = []
    seen = set()

    if os.path.exists("/Volumes") and os.path.isdir("/Volumes"):
        try:
            for item in sorted(os.listdir("/Volumes")):
                p = os.path.join("/Volumes", item)
                if os.path.islink(p) and os.path.realpath(p) == "/":
                    continue
                if item.startswith(".") or item in (
                    "Recovery", "Preboot", "VM", "Update", "xarts", "iSCPreboot", "Hardware"
                ):
                    continue
                if os.path.isdir(p) and p not in seen:
                    seen.add(p)
                    item_lower = item.lower()
                    if "sd" in item_lower or "card" in item_lower:
                        icon = "💾"
                    elif "usb" in item_lower or "flash" in item_lower or "thumb" in item_lower:
                        icon = "🔌"
                    else:
                        icon = "💽"
                    display = f"{icon} {item}"
                    volumes.append((display, p, True))
        except Exception:
            pass

    return volumes


def normalize_local_path(path: str) -> str:
    """Normalize local macOS path supporting ~, Volumes, and drive names."""
    if not path:
        return str(Path.home())
    clean = path.strip()
    if not clean:
        return str(Path.home())

    if clean in ("~", "home", "Home", "home/"):
        return str(Path.home())
    if clean.startswith("~/"):
        return os.path.expanduser(clean)

    if clean in ("Volumes", "/Volumes", "volumes", "/volumes"):
        return "/Volumes"

    if not clean.startswith("/"):
        vol_path = os.path.join("/Volumes", clean)
        if os.path.exists(vol_path) and os.path.isdir(vol_path):
            return vol_path

        if os.path.exists("/Volumes"):
            for v_name in os.listdir("/Volumes"):
                if v_name.lower() == clean.lower():
                    return os.path.join("/Volumes", v_name)

        home_sub = Path.home() / clean
        if home_sub.exists():
            return str(home_sub)

    return os.path.abspath(os.path.expanduser(clean))


def format_display_local_path(path: str) -> str:
    """Format local path for user-friendly display (e.g. '💾 SD / Documents' or '~/Downloads')."""
    if not path:
        return "~"
    clean = os.path.abspath(path.strip())

    if clean in ("/Volumes", "/Volumes/"):
        return "📂 All Volumes"

    if clean.startswith("/Volumes/"):
        rel = clean[len("/Volumes/"):].strip()
        parts = [p.strip() for p in rel.split("/") if p.strip()]
        if parts:
            vol_name = parts[0]
            icon = "💾" if ("sd" in vol_name.lower() or "card" in vol_name.lower()) else "💽"
            sub = parts[1:]
            return f"{icon} {vol_name}" + (" / " + " / ".join(sub) if sub else "")

    home_str = str(Path.home())
    if clean == home_str:
        return "~"
    if clean.startswith(f"{home_str}/"):
        rel = clean[len(home_str) + 1:].strip()
        return f"~/{rel}"

    return clean


class PathBar(QWidget):
    """Navigation address bar with Back, Forward, Up, Home and Refresh."""

    navigate_requested = pyqtSignal(str)
    refresh_requested = pyqtSignal()

    def __init__(self, is_remote: bool = False, parent=None):
        super().__init__(parent)
        self.is_remote = is_remote
        self._current_path: str = ANDROID_INTERNAL_STORAGE if is_remote else str(Path.home())
        self.history: List[str] = []
        self.history_index: int = -1

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)

        self.btn_back = QPushButton("◀")
        self.btn_back.setObjectName("navBtn")
        self.btn_back.setToolTip("Back")
        self.btn_back.setEnabled(False)
        self.btn_back.clicked.connect(self.go_back)
        layout.addWidget(self.btn_back)

        self.btn_forward = QPushButton("▶")
        self.btn_forward.setObjectName("navBtn")
        self.btn_forward.setToolTip("Forward")
        self.btn_forward.setEnabled(False)
        self.btn_forward.clicked.connect(self.go_forward)
        layout.addWidget(self.btn_forward)

        self.btn_up = QPushButton("▲")
        self.btn_up.setObjectName("navBtn")
        self.btn_up.setToolTip("Up to parent directory")
        self.btn_up.clicked.connect(self.go_up)
        layout.addWidget(self.btn_up)

        self.btn_home = QPushButton("🏠")
        self.btn_home.setObjectName("navBtn")
        self.btn_home.setToolTip("Go to Home directory")
        self.btn_home.clicked.connect(self.go_home)
        layout.addWidget(self.btn_home)

        self.path_edit = QLineEdit()
        self.path_edit.returnPressed.connect(self.on_path_entered)
        layout.addWidget(self.path_edit, 1)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setObjectName("navBtn")
        self.btn_refresh.setToolTip("Refresh current directory")
        self.btn_refresh.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(self.btn_refresh)

    @property
    def current_path(self) -> str:
        return self._current_path

    def set_path(self, path: str, record_history: bool = True):
        clean = path.strip()
        if self.is_remote:
            clean = normalize_remote_path(clean)
        else:
            if not clean:
                clean = str(Path.home())

        self._current_path = clean

        if record_history:
            if self.history_index < len(self.history) - 1:
                self.history = self.history[: self.history_index + 1]
            if not self.history or self.history[-1] != clean:
                self.history.append(clean)
                self.history_index = len(self.history) - 1

        display_str = format_display_remote_path(clean) if self.is_remote else format_display_local_path(clean)
        self.path_edit.setText(display_str)
        self.update_nav_buttons()

    def update_nav_buttons(self):
        self.btn_back.setEnabled(self.history_index > 0)
        self.btn_forward.setEnabled(self.history_index < len(self.history) - 1)
        if self.is_remote:
            cur = self.current_path.rstrip("/")
            self.btn_up.setEnabled(cur not in ("/storage", "/", ""))
        else:
            cur = self.current_path.rstrip("/")
            self.btn_up.setEnabled(cur not in ("/", ""))

    def on_path_entered(self):
        raw = self.path_edit.text().strip()
        if raw:
            target = normalize_remote_path(raw) if self.is_remote else normalize_local_path(raw)
            self.navigate_requested.emit(target)

    def go_back(self):
        if self.history_index > 0:
            self.history_index -= 1
            target = self.history[self.history_index]
            self._current_path = target
            display_str = format_display_remote_path(target) if self.is_remote else format_display_local_path(target)
            self.path_edit.setText(display_str)
            self.update_nav_buttons()
            self.navigate_requested.emit(target)

    def go_forward(self):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            target = self.history[self.history_index]
            self._current_path = target
            display_str = format_display_remote_path(target) if self.is_remote else format_display_local_path(target)
            self.path_edit.setText(display_str)
            self.update_nav_buttons()
            self.navigate_requested.emit(target)

    def go_up(self):
        cur = self.current_path.rstrip("/")
        if self.is_remote:
            if not cur or cur in ("/storage", "/", ""):
                return
            if cur in (ANDROID_INTERNAL_STORAGE, f"{ANDROID_INTERNAL_STORAGE}"):
                # Navigating up from Internal Storage root reveals all mounted storage roots
                self.navigate_requested.emit("/storage")
                return
            parts = cur.rsplit("/", 1)
            parent_dir = parts[0] if parts[0] else "/storage"
            self.navigate_requested.emit(parent_dir)
        else:
            if not cur or cur in ("/", ""):
                return
            if cur in ("/Volumes", "/Volumes/"):
                self.navigate_requested.emit("/")
                return
            parts = cur.rsplit("/", 1)
            parent_dir = parts[0] if parts[0] else "/"
            self.navigate_requested.emit(parent_dir)

    def go_home(self):
        if self.is_remote:
            self.navigate_requested.emit(ANDROID_INTERNAL_STORAGE)
        else:
            self.navigate_requested.emit(str(Path.home()))


class FileTableView(QTableView):
    """Modern file table view with native macOS keyboard shortcuts."""
    item_open_requested = pyqtSignal()
    navigate_up_requested = pyqtSignal()
    navigate_back_requested = pyqtSignal()
    navigate_forward_requested = pyqtSignal()

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        modifiers = event.modifiers()

        # 1. Return / Enter / Cmd+Down / Cmd+O -> Open selected item (folder or file)
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or (
            key == Qt.Key.Key_Down and bool(modifiers & Qt.KeyboardModifier.MetaModifier)
        ) or (
            key == Qt.Key.Key_O and bool(modifiers & Qt.KeyboardModifier.MetaModifier)
        ):
            self.item_open_requested.emit()
            event.accept()
            return

        # 2. Cmd+Up or Backspace -> Go up to parent folder
        if (key == Qt.Key.Key_Up and bool(modifiers & Qt.KeyboardModifier.MetaModifier)) or key == Qt.Key.Key_Backspace:
            self.navigate_up_requested.emit()
            event.accept()
            return

        # 3. Cmd+[ or Option+Left -> History Back
        if (key == Qt.Key.Key_BracketLeft and bool(modifiers & Qt.KeyboardModifier.MetaModifier)) or (
            key == Qt.Key.Key_Left and bool(modifiers & Qt.KeyboardModifier.AltModifier)
        ):
            self.navigate_back_requested.emit()
            event.accept()
            return

        # 4. Cmd+] or Option+Right -> History Forward
        if (key == Qt.Key.Key_BracketRight and bool(modifiers & Qt.KeyboardModifier.MetaModifier)) or (
            key == Qt.Key.Key_Right and bool(modifiers & Qt.KeyboardModifier.AltModifier)
        ):
            self.navigate_forward_requested.emit()
            event.accept()
            return

        super().keyPressEvent(event)


class FilePane(QFrame):
    """Complete File Explorer Pane with PathBar, Quick Shortcuts, Filter, and Modern TableView."""

    item_double_clicked = pyqtSignal(object)
    selection_changed = pyqtSignal()
    open_context_menu = pyqtSignal(QPoint)
    new_folder_requested = pyqtSignal()

    def __init__(self, title: str, is_remote: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("paneFrame")
        self.is_remote = is_remote

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.setSpacing(8)

        # 1. Header Bar (Title + New Folder Button + Search Filter)
        header_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(self.title_label)

        header_layout.addStretch()

        if not self.is_remote:
            self.btn_pane_drives = QPushButton("💾 Drives")
            self.btn_pane_drives.setObjectName("navBtn")
            self.btn_pane_drives.setToolTip("Quick access to SD card, USB drives and mounted Mac volumes")
            self.btn_pane_drives.setCursor(Qt.CursorShape.PointingHandCursor)
            self.btn_pane_drives.clicked.connect(self.show_drives_menu)
            header_layout.addWidget(self.btn_pane_drives)

        self.btn_pane_new_folder = QPushButton("➕ New Folder")
        self.btn_pane_new_folder.setObjectName("navBtn")
        self.btn_pane_new_folder.setToolTip("Create a new folder in this location")
        self.btn_pane_new_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pane_new_folder.clicked.connect(self.new_folder_requested.emit)
        header_layout.addWidget(self.btn_pane_new_folder)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("searchField")
        self.search_edit.setPlaceholderText("🔍 Filter...")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(170)
        self.search_edit.textChanged.connect(self.on_filter_changed)
        header_layout.addWidget(self.search_edit)

        layout.addLayout(header_layout)

        # 2. Path Navigation Bar
        self.path_bar = PathBar(is_remote=is_remote)
        layout.addWidget(self.path_bar)

        # 3. Horizontal Quick Shortcut Pills
        self.shortcuts_layout = QHBoxLayout()
        self.shortcuts_layout.setContentsMargins(0, 2, 0, 2)
        self.shortcuts_layout.setSpacing(6)
        self._remote_volumes: List[StorageVolume] = []
        self._shortcut_buttons: List[QPushButton] = []
        self.rebuild_shortcuts()
        layout.addLayout(self.shortcuts_layout)

        # 4. Table Model and Proxy
        if is_remote:
            self.model = RemoteFileTableModel(self)
        else:
            self.model = LocalFileTableModel(self)

        self.proxy_model = FileFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)

        # 5. Table View
        self.table_view = FileTableView()
        self.table_view.setModel(self.proxy_model)
        self.table_view.setSortingEnabled(True)
        self.table_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.table_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table_view.setShowGrid(False)
        self.table_view.setAlternatingRowColors(True)
        self.table_view.verticalHeader().setVisible(False)
        self.table_view.verticalHeader().setDefaultSectionSize(34)  # Roomy, modern 34px row height
        self.table_view.setIconSize(QSize(22, 22))                   # Crisp high-DPI icon size
        self.table_view.horizontalHeader().setHighlightSections(False)
        self.table_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        header = self.table_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        self.table_view.setColumnWidth(1, 105)
        self.table_view.setColumnWidth(2, 145)
        self.table_view.setColumnWidth(3, 115)

        # Disable cell-inline editing so double-click opens immediately without hesitation
        self.table_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_view.doubleClicked.connect(self.on_double_click)
        self.table_view.activated.connect(self.on_double_click)
        self.table_view.item_open_requested.connect(self.open_current_or_selected)
        self.table_view.navigate_up_requested.connect(self.path_bar.go_up)
        self.table_view.navigate_back_requested.connect(self.path_bar.go_back)
        self.table_view.navigate_forward_requested.connect(self.path_bar.go_forward)
        self.table_view.selectionModel().selectionChanged.connect(self.on_selection_change)
        self.table_view.customContextMenuRequested.connect(self.open_context_menu.emit)

        layout.addWidget(self.table_view, 1)

        # 6. Footer Summary
        self.footer_label = QLabel("0 items")
        self.footer_label.setStyleSheet("color: #8c8d99; font-size: 11px;")
        layout.addWidget(self.footer_label)

    @property
    def current_path(self) -> str:
        return self.path_bar.current_path

    def open_current_or_selected(self):
        """Open the currently highlighted or selected folder or file."""
        # 1. Check selected items
        selected = self.get_selected_items()
        if selected:
            self.item_double_clicked.emit(selected[0])
            return

        # 2. Check current focus index (e.g. from arrow key navigation)
        cur_idx = self.table_view.currentIndex()
        if cur_idx.isValid():
            src_idx = self.proxy_model.mapToSource(cur_idx)
            item = self.model.get_item(src_idx.row())
            if item:
                self.item_double_clicked.emit(item)

    def on_filter_changed(self, text: str):
        regex = QRegularExpression(text, QRegularExpression.PatternOption.CaseInsensitiveOption)
        self.proxy_model.setFilterRegularExpression(regex)
        self.update_footer()

    def on_double_click(self, proxy_index):
        src_index = self.proxy_model.mapToSource(proxy_index)
        item = self.model.get_item(src_index.row())
        if item:
            self.item_double_clicked.emit(item)

    def on_selection_change(self):
        self.update_footer()
        self.selection_changed.emit()

    def get_selected_items(self) -> List[Any]:
        selected_rows = self.table_view.selectionModel().selectedRows()
        items = []
        for p_idx in selected_rows:
            s_idx = self.proxy_model.mapToSource(p_idx)
            item = self.model.get_item(s_idx.row())
            if item:
                items.append(item)
        return items

    def update_footer(self):
        total = self.proxy_model.rowCount()
        selected = len(self.table_view.selectionModel().selectedRows())
        if selected > 0:
            self.footer_label.setText(f"{total} items ({selected} selected)")
        else:
            self.footer_label.setText(f"{total} items")

    def set_storage_volumes(self, volumes: List[StorageVolume]):
        """Update discovered storage volumes (e.g. SD Card, USB OTG) and rebuild shortcut pills."""
        self._remote_volumes = volumes or []
        if self.is_remote:
            self.rebuild_shortcuts()

    def _resolve_shortcut_target(self, folder_name: str) -> str:
        """Resolve standard folders against active storage root (Internal Storage or SD Card)."""
        cur = self.current_path.rstrip("/")
        # If currently inside an external volume /storage/<UUID>/...
        if cur.startswith("/storage/") and not cur.startswith("/storage/emulated") and not cur.startswith("/storage/self"):
            parts = cur.split("/")
            if len(parts) >= 3 and parts[2]:
                vol_base = f"/storage/{parts[2]}"
                return f"{vol_base}/{folder_name}"
        return f"{ANDROID_INTERNAL_STORAGE}/{folder_name}"

    def rebuild_shortcuts(self):
        """Build or rebuild horizontal quick shortcut pills."""
        # Clear existing shortcuts
        while self.shortcuts_layout.count() > 0:
            item = self.shortcuts_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._shortcut_buttons.clear()

        if self.is_remote:
            # 1. Primary volume
            btn_internal = QPushButton("📱 Internal Storage")
            btn_internal.setObjectName("shortcutPill")
            btn_internal.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_internal.clicked.connect(lambda: self.path_bar.navigate_requested.emit(ANDROID_INTERNAL_STORAGE))
            self.shortcuts_layout.addWidget(btn_internal)
            self._shortcut_buttons.append(btn_internal)

            # 2. External volumes (MicroSD / USB OTG)
            external_vols = [v for v in self._remote_volumes if v.is_removable]
            if external_vols:
                for v in external_vols:
                    btn_sd = QPushButton(f"💾 {v.name}")
                    btn_sd.setObjectName("shortcutPill")
                    btn_sd.setCursor(Qt.CursorShape.PointingHandCursor)
                    p = v.path
                    btn_sd.clicked.connect(lambda checked=False, target=p: self.path_bar.navigate_requested.emit(target))
                    self.shortcuts_layout.addWidget(btn_sd)
                    self._shortcut_buttons.append(btn_sd)
            else:
                # Fallback SD card button that jumps to /storage or scans
                btn_sd = QPushButton("💾 SD Card")
                btn_sd.setObjectName("shortcutPill")
                btn_sd.setToolTip("Open SD Card or browse all mounted storage points (/storage)")
                btn_sd.setCursor(Qt.CursorShape.PointingHandCursor)
                btn_sd.clicked.connect(self._on_sd_card_pill_clicked)
                self.shortcuts_layout.addWidget(btn_sd)
                self._shortcut_buttons.append(btn_sd)

            # 3. All storage root pill
            btn_all = QPushButton("📂 All Storage")
            btn_all.setObjectName("shortcutPill")
            btn_all.setToolTip("Browse all storage roots (/storage)")
            btn_all.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_all.clicked.connect(lambda: self.path_bar.navigate_requested.emit("/storage"))
            self.shortcuts_layout.addWidget(btn_all)
            self._shortcut_buttons.append(btn_all)

            # 4. Standard Android folders (context-aware: uses active storage volume)
            folders = [
                ("📥 Download", "Download"),
                ("📸 DCIM", "DCIM"),
                ("🖼️ Pictures", "Pictures"),
                ("📄 Documents", "Documents"),
                ("🎵 Music", "Music"),
                ("🎬 Movies", "Movies"),
            ]
            for label, f_name in folders:
                btn = QPushButton(label)
                btn.setObjectName("shortcutPill")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                fn = f_name
                btn.clicked.connect(lambda checked=False, name=fn: self.path_bar.navigate_requested.emit(self._resolve_shortcut_target(name)))
                self.shortcuts_layout.addWidget(btn)
                self._shortcut_buttons.append(btn)
        else:
            # 1. External mounted drives on macOS (SD card, USB drives, etc.)
            mac_vols = get_mac_volumes()
            for label, target_path, _ in mac_vols:
                btn = QPushButton(label)
                btn.setObjectName("shortcutPill")
                btn.setToolTip(f"Open Mac volume: {target_path}")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                p = target_path
                btn.clicked.connect(lambda checked=False, target=p: self.path_bar.navigate_requested.emit(target))
                self.shortcuts_layout.addWidget(btn)
                self._shortcut_buttons.append(btn)

            # 2. Volumes directory pill
            btn_vols = QPushButton("📂 Volumes")
            btn_vols.setObjectName("shortcutPill")
            btn_vols.setToolTip("Browse all mounted Mac external drives and SD cards (/Volumes)")
            btn_vols.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_vols.clicked.connect(lambda: self.path_bar.navigate_requested.emit("/Volumes"))
            self.shortcuts_layout.addWidget(btn_vols)
            self._shortcut_buttons.append(btn_vols)

            # 3. Standard user home folders
            home = Path.home()
            local_shortcuts = [
                ("🏠 Home", str(home)),
                ("📥 Downloads", str(home / "Downloads")),
                ("🖥️ Desktop", str(home / "Desktop")),
                ("📄 Documents", str(home / "Documents")),
                ("🖼️ Pictures", str(home / "Pictures")),
                ("🎵 Music", str(home / "Music")),
            ]
            for label, target_path in local_shortcuts:
                btn = QPushButton(label)
                btn.setObjectName("shortcutPill")
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                p = target_path
                btn.clicked.connect(lambda checked=False, target=p: self.path_bar.navigate_requested.emit(target))
                self.shortcuts_layout.addWidget(btn)
                self._shortcut_buttons.append(btn)

        self.shortcuts_layout.addStretch()

    def show_drives_menu(self):
        """Show popup menu listing Mac external drives (SD card, USB drives) and Volumes."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #26272e;
                color: #ffffff;
                border: 1px solid #3d3e4a;
                border-radius: 8px;
                padding: 6px;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 14px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #3b82f6;
            }
            QMenu::separator {
                height: 1px;
                background: #3d3e4a;
                margin: 4px 0;
            }
        """)
        mac_vols = get_mac_volumes()
        if mac_vols:
            act_header = menu.addAction("Mounted External Drives on Mac:")
            act_header.setEnabled(False)
            for label, p, _ in mac_vols:
                act = menu.addAction(f"{label}  ({p})")
                act.triggered.connect(lambda checked=False, target=p: self.path_bar.navigate_requested.emit(target))
            menu.addSeparator()

        act_vols = menu.addAction("📂 Browse All /Volumes")
        act_vols.triggered.connect(lambda: self.path_bar.navigate_requested.emit("/Volumes"))

        act_root = menu.addAction("🖥️ Macintosh HD (Root /)")
        act_root.triggered.connect(lambda: self.path_bar.navigate_requested.emit("/"))

        if hasattr(self, "btn_pane_drives"):
            pos = self.btn_pane_drives.mapToGlobal(QPoint(0, self.btn_pane_drives.height() + 2))
        else:
            pos = self.mapToGlobal(QPoint(10, 30))
        menu.exec(pos)

    def _on_sd_card_pill_clicked(self):
        external_vols = [v for v in self._remote_volumes if v.is_removable]
        if external_vols:
            self.path_bar.navigate_requested.emit(external_vols[0].path)
        else:
            self.path_bar.navigate_requested.emit("/storage")


class TransferProgressDialog(QDialog):
    """Modal transfer progress dialog with Cancel button."""

    cancelled = pyqtSignal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(460)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 20)
        layout.setSpacing(14)

        self.status_label = QLabel("Preparing transfer...")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #ffffff;")
        layout.addWidget(self.status_label)

        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("font-size: 12px; color: #9898a4;")
        self.detail_label.setWordWrap(True)
        layout.addWidget(self.detail_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)

        layout.addLayout(btn_layout)

    def update_progress(self, current: int, total: int, item_name: str, detail: str):
        pct = int((current / max(total, 1)) * 100)
        self.progress_bar.setValue(pct)
        self.status_label.setText(f"Transferring: {item_name}")
        self.detail_label.setText(detail)

    def on_cancel_clicked(self):
        self.btn_cancel.setEnabled(False)
        self.status_label.setText("Cancelling transfer...")
        self.cancelled.emit()
