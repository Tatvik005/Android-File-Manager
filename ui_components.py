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

from pathlib import Path
from typing import Any, List, Optional

from PyQt6.QtCore import QEvent, QPoint, QRegularExpression, QSize, Qt, pyqtSignal
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
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from adb_manager import (
    ANDROID_INTERNAL_STORAGE,
    ConnectionState,
    DeviceInfo,
    RemoteFileInfo,
    format_display_remote_path,
    normalize_remote_path,
)
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

        display_str = format_display_remote_path(clean) if self.is_remote else clean
        self.path_edit.setText(display_str)
        self.update_nav_buttons()

    def update_nav_buttons(self):
        self.btn_back.setEnabled(self.history_index > 0)
        self.btn_forward.setEnabled(self.history_index < len(self.history) - 1)
        if self.is_remote:
            cur = self.current_path
            self.btn_up.setEnabled(cur not in (ANDROID_INTERNAL_STORAGE, f"{ANDROID_INTERNAL_STORAGE}/", "/"))
        else:
            cur = self.current_path
            self.btn_up.setEnabled(cur not in ("/", ""))

    def on_path_entered(self):
        raw = self.path_edit.text().strip()
        if raw:
            target = normalize_remote_path(raw) if self.is_remote else raw
            self.navigate_requested.emit(target)

    def go_back(self):
        if self.history_index > 0:
            self.history_index -= 1
            target = self.history[self.history_index]
            self._current_path = target
            display_str = format_display_remote_path(target) if self.is_remote else target
            self.path_edit.setText(display_str)
            self.update_nav_buttons()
            self.navigate_requested.emit(target)

    def go_forward(self):
        if self.history_index < len(self.history) - 1:
            self.history_index += 1
            target = self.history[self.history_index]
            self._current_path = target
            display_str = format_display_remote_path(target) if self.is_remote else target
            self.path_edit.setText(display_str)
            self.update_nav_buttons()
            self.navigate_requested.emit(target)

    def go_up(self):
        cur = self.current_path
        if self.is_remote:
            if cur in (ANDROID_INTERNAL_STORAGE, f"{ANDROID_INTERNAL_STORAGE}/", "/"):
                return
            parts = cur.rstrip("/").rsplit("/", 1)
            parent_dir = parts[0] if parts[0] else ANDROID_INTERNAL_STORAGE
            self.navigate_requested.emit(parent_dir)
        else:
            cur = cur.rstrip("/")
            if not cur or cur == "/":
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
        shortcuts_layout = QHBoxLayout()
        shortcuts_layout.setContentsMargins(0, 2, 0, 2)
        shortcuts_layout.setSpacing(6)

        if is_remote:
            shortcut_data = [
                ("📱 Internal Storage", ANDROID_INTERNAL_STORAGE),
                ("📥 Download", f"{ANDROID_INTERNAL_STORAGE}/Download"),
                ("📸 DCIM", f"{ANDROID_INTERNAL_STORAGE}/DCIM"),
                ("🖼️ Pictures", f"{ANDROID_INTERNAL_STORAGE}/Pictures"),
                ("📄 Documents", f"{ANDROID_INTERNAL_STORAGE}/Documents"),
                ("🎵 Music", f"{ANDROID_INTERNAL_STORAGE}/Music"),
                ("🎬 Movies", f"{ANDROID_INTERNAL_STORAGE}/Movies"),
            ]
        else:
            home = Path.home()
            shortcut_data = [
                ("🏠 Home", str(home)),
                ("📥 Downloads", str(home / "Downloads")),
                ("🖥️ Desktop", str(home / "Desktop")),
                ("📄 Documents", str(home / "Documents")),
                ("🖼️ Pictures", str(home / "Pictures")),
                ("🎵 Music", str(home / "Music")),
            ]

        for label, target_path in shortcut_data:
            btn = QPushButton(label)
            btn.setObjectName("shortcutPill")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, p=target_path: self.path_bar.navigate_requested.emit(p))
            shortcuts_layout.addWidget(btn)

        shortcuts_layout.addStretch()
        layout.addLayout(shortcuts_layout)

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
