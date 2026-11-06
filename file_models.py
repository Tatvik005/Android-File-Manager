"""
file_models.py
Table models, high-DPI vector file icons, and metadata representation for PyQt6 views.
"""

from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QRectF, QSortFilterProxyModel, Qt
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)

from adb_manager import RemoteFileInfo, format_bytes


@dataclass
class LocalFileInfo:
    name: str
    path: str
    is_dir: bool
    size: int
    date_str: str
    mtime: float
    is_symlink: bool = False
    extension: str = ""

    @classmethod
    def from_path(cls, path_obj: Path) -> Optional["LocalFileInfo"]:
        try:
            stat = path_obj.lstat()
            is_dir = path_obj.is_dir()
            is_symlink = path_obj.is_symlink()
            mtime = stat.st_mtime
            dt = datetime.fromtimestamp(mtime)
            date_str = dt.strftime("%Y-%m-%d %H:%M")
            ext = path_obj.suffix.lower().lstrip(".") if not is_dir else ""
            size = stat.st_size if not is_dir else 0

            return cls(
                name=path_obj.name,
                path=str(path_obj.resolve() if not is_symlink else path_obj),
                is_dir=is_dir,
                size=size,
                date_str=date_str,
                mtime=mtime,
                is_symlink=is_symlink,
                extension=ext,
            )
        except (PermissionError, FileNotFoundError, OSError):
            return None


class IconHelper:
    """Provides high-DPI vector-drawn icons for files and folders."""

    IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "svg", "raw"}
    VIDEO_EXTS = {"mp4", "mkv", "mov", "avi", "webm", "flv", "wmv", "3gp"}
    AUDIO_EXTS = {"mp3", "m4a", "flac", "wav", "aac", "ogg", "opus"}
    ARCHIVE_EXTS = {"zip", "tar", "gz", "tgz", "bz2", "xz", "7z", "rar"}
    DOC_EXTS = {"doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "rtf"}
    PDF_EXTS = {"pdf"}
    CODE_EXTS = {"py", "js", "ts", "html", "css", "json", "xml", "java", "kt", "c", "cpp", "h", "sh", "yml", "yaml", "sql"}
    APP_EXTS = {"apk", "aab"}

    _icon_cache: Dict[str, QIcon] = {}

    @classmethod
    def get_type_description(cls, is_dir: bool, ext: str) -> str:
        if is_dir:
            return "Folder"
        ext = ext.lower()
        if ext in cls.IMAGE_EXTS:
            return f"{ext.upper()} Image"
        if ext in cls.VIDEO_EXTS:
            return f"{ext.upper()} Video"
        if ext in cls.AUDIO_EXTS:
            return f"{ext.upper()} Audio"
        if ext in cls.ARCHIVE_EXTS:
            return f"{ext.upper()} Archive"
        if ext in cls.PDF_EXTS:
            return "PDF Document"
        if ext in cls.DOC_EXTS:
            return f"{ext.upper()} Document"
        if ext in cls.CODE_EXTS:
            return f"{ext.upper()} Source"
        if ext in cls.APP_EXTS:
            return "Android Package"
        return f"{ext.upper()} File" if ext else "File"

    @classmethod
    def get_icon(cls, is_dir: bool, ext: str = "", is_symlink: bool = False, is_remote: bool = False) -> QIcon:
        """Returns cached high-DPI QIcon for file category."""
        key = f"{is_dir}_{ext.lower()}_{is_symlink}_{is_remote}"
        if key in cls._icon_cache:
            return cls._icon_cache[key]

        size = 48
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if is_dir:
            # Folder Icon: Blue for Mac, Emerald for Android
            if is_remote:
                top_color = "#34d399"
                base_color = "#059669"
                tab_color = "#047857"
            else:
                top_color = "#60a5fa"
                base_color = "#2563eb"
                tab_color = "#1d4ed8"

            # Back tab
            painter.setBrush(QColor(tab_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(6, 10, 18, 12), 3, 3)

            # Front folder gradient
            grad = QLinearGradient(0, 14, 0, 42)
            grad.setColorAt(0.0, QColor(top_color))
            grad.setColorAt(1.0, QColor(base_color))
            painter.setBrush(grad)
            painter.drawRoundedRect(QRectF(6, 16, 36, 26), 4, 4)

            # Subtle rim highlight
            painter.setPen(QColor(255, 255, 255, 70))
            painter.drawLine(8, 17, 40, 17)

        else:
            ext_l = ext.lower()
            # Determine badge color
            if ext_l in cls.IMAGE_EXTS:
                color1, color2 = "#f472b6", "#db2777"
                badge_text = "IMG"
            elif ext_l in cls.VIDEO_EXTS:
                color1, color2 = "#a855f7", "#7c3aed"
                badge_text = "MOV"
            elif ext_l in cls.AUDIO_EXTS:
                color1, color2 = "#fb7185", "#e11d48"
                badge_text = "AUD"
            elif ext_l in cls.PDF_EXTS:
                color1, color2 = "#f87171", "#dc2626"
                badge_text = "PDF"
            elif ext_l in cls.ARCHIVE_EXTS:
                color1, color2 = "#fbbf24", "#d97706"
                badge_text = "ZIP"
            elif ext_l in cls.CODE_EXTS:
                color1, color2 = "#38bdf8", "#0284c7"
                badge_text = "< >"
            elif ext_l in cls.APP_EXTS:
                color1, color2 = "#3ddc84", "#16a34a"
                badge_text = "APK"
            else:
                color1, color2 = "#94a3b8", "#64748b"
                badge_text = ext_l[:3].upper() if ext_l else "DOC"

            # Document Sheet
            sheet_rect = QRectF(10, 8, 28, 32)
            doc_grad = QLinearGradient(0, 8, 0, 40)
            doc_grad.setColorAt(0.0, QColor("#2a2b36"))
            doc_grad.setColorAt(1.0, QColor("#1e1f28"))
            painter.setBrush(doc_grad)
            painter.setPen(QPen(QColor("#404252"), 1.2))
            painter.drawRoundedRect(sheet_rect, 4, 4)

            # Folded top-right corner
            fold = QPainterPath()
            fold.moveTo(30, 8)
            fold.lineTo(38, 16)
            fold.lineTo(30, 16)
            fold.closeSubpath()
            painter.fillPath(fold, QColor("#363846"))

            # Colored accent bar
            bar_grad = QLinearGradient(12, 0, 36, 0)
            bar_grad.setColorAt(0.0, QColor(color1))
            bar_grad.setColorAt(1.0, QColor(color2))
            painter.setBrush(bar_grad)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRectF(13, 26, 22, 10), 3, 3)

            # Badge Text
            painter.setFont(QFont("-apple-system", 6, QFont.Weight.Bold))
            painter.setPen(QColor("#ffffff"))
            painter.drawText(QRectF(13, 26, 22, 10), int(Qt.AlignmentFlag.AlignCenter), badge_text)

        if is_symlink:
            # Small link badge on bottom-left
            painter.setBrush(QColor("#0a84ff"))
            painter.setPen(QColor("#ffffff"))
            painter.drawEllipse(QRectF(4, 30, 12, 12))

        painter.end()

        icon = QIcon(pixmap)
        cls._icon_cache[key] = icon
        return icon


class BaseFileTableModel(QAbstractTableModel):
    COL_NAME = 0
    COL_SIZE = 1
    COL_DATE = 2
    COL_TYPE = 3

    COLUMNS = ["NAME", "SIZE", "DATE MODIFIED", "TYPE"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: List[Any] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._items)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(self.COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(self.COLUMNS):
                return self.COLUMNS[section]
        return None

    def get_item(self, row: int) -> Optional[Any]:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None


class LocalFileTableModel(BaseFileTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_path: str = ""

    def load_directory(self, dir_path: str):
        self.beginResetModel()
        self.current_path = dir_path
        self._items = []

        try:
            p = Path(dir_path)
            if p.is_dir():
                for child in p.iterdir():
                    if child.name.startswith("."):
                        continue
                    item = LocalFileInfo.from_path(child)
                    if item:
                        self._items.append(item)
        except Exception:
            pass

        self._items.sort(key=lambda x: (not x.is_dir, x.name.lower()))
        self.endResetModel()

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None

        item: LocalFileInfo = self._items[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.COL_NAME:
                return item.name
            elif col == self.COL_SIZE:
                return "--" if item.is_dir else format_bytes(item.size)
            elif col == self.COL_DATE:
                return item.date_str
            elif col == self.COL_TYPE:
                return IconHelper.get_type_description(item.is_dir, item.extension)

        elif role == Qt.ItemDataRole.DecorationRole:
            if col == self.COL_NAME:
                return IconHelper.get_icon(item.is_dir, item.extension, item.is_symlink, is_remote=False)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self.COL_SIZE:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.UserRole:
            if col == self.COL_NAME:
                return (not item.is_dir, item.name.lower())
            elif col == self.COL_SIZE:
                return (not item.is_dir, item.size)
            elif col == self.COL_DATE:
                return item.mtime
            elif col == self.COL_TYPE:
                return item.extension

        return None


class RemoteFileTableModel(BaseFileTableModel):
    COLUMNS = ["NAME", "SIZE", "DATE MODIFIED", "PERMISSIONS"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_path: str = "/storage/emulated/0"

    def set_items(self, path: str, items: List[RemoteFileInfo]):
        self.beginResetModel()
        self.current_path = path
        self._items = [i for i in items if not i.name.startswith(".")]
        self.endResetModel()

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._items):
            return None

        item: RemoteFileInfo = self._items[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            if col == self.COL_NAME:
                target_str = f"  ➔  {item.link_target}" if item.is_symlink and item.link_target else ""
                return f"{item.name}{target_str}"
            elif col == self.COL_SIZE:
                return "--" if item.is_dir else format_bytes(item.size)
            elif col == self.COL_DATE:
                return item.date_str
            elif col == self.COL_TYPE:
                return item.permissions

        elif role == Qt.ItemDataRole.DecorationRole:
            if col == self.COL_NAME:
                return IconHelper.get_icon(item.is_dir, item.extension, item.is_symlink, is_remote=True)

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col == self.COL_SIZE:
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        elif role == Qt.ItemDataRole.UserRole:
            if col == self.COL_NAME:
                return (not item.is_dir, item.name.lower())
            elif col == self.COL_SIZE:
                return (not item.is_dir, item.size)
            elif col == self.COL_DATE:
                return item.date_str
            elif col == self.COL_TYPE:
                return item.permissions

        return None


class FileFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        filter_regex = self.filterRegularExpression()
        if not filter_regex.pattern():
            return True

        model = self.sourceModel()
        idx = model.index(source_row, 0, source_parent)
        name_val = model.data(idx, Qt.ItemDataRole.DisplayRole) or ""
        return filter_regex.match(name_val).hasMatch()

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        left_data = self.sourceModel().data(left, Qt.ItemDataRole.UserRole)
        right_data = self.sourceModel().data(right, Qt.ItemDataRole.UserRole)

        if left_data is None or right_data is None:
            return super().lessThan(left, right)

        return left_data < right_data
