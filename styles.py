"""
styles.py
High-end macOS Sonoma / Sequoia Dark-Mode design system for Android File Manager.
"""

DARK_THEME_QSS = """
/* Base Window & Global Typography */
QMainWindow, QDialog {
    background-color: #121316;
    color: #f3f3f6;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
}

QWidget {
    color: #e2e2e8;
    font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 13px;
    selection-background-color: #0071e3;
    selection-color: #ffffff;
}

/* Splitter */
QSplitter::handle {
    background-color: #23242c;
    width: 2px;
}
QSplitter::handle:hover {
    background-color: #0071e3;
}

/* Pane Frame Container */
QFrame#paneFrame {
    background-color: #1a1b22;
    border: 1px solid #282934;
    border-radius: 10px;
}

/* Top Warning / Alert Banner */
QFrame#bannerFrame {
    background-color: #2e2300;
    border: 1px solid #997300;
    border-radius: 8px;
    padding: 8px 14px;
}

/* Base Buttons */
QPushButton {
    background-color: #24252f;
    border: 1px solid #343542;
    border-radius: 7px;
    color: #f0f0f5;
    padding: 6px 14px;
    font-weight: 500;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #2f303d;
    border-color: #454758;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #1c1d25;
}

QPushButton:disabled {
    background-color: #181920;
    border-color: #23242d;
    color: #5c5d68;
}

/* Pull to Mac - Apple Blue Vibrant Button */
QPushButton#primaryActionBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #0077ed, stop:1 #005ec4);
    border: 1px solid #288df7;
    color: #ffffff;
    font-weight: 600;
    padding: 7px 18px;
    border-radius: 7px;
}
QPushButton#primaryActionBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #1a87f5, stop:1 #006ddb);
    border-color: #479ff8;
}
QPushButton#primaryActionBtn:pressed {
    background: #004fb0;
}

/* Push to Android - Emerald Green Vibrant Button */
QPushButton#secondaryActionBtn {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #059669, stop:1 #047857);
    border: 1px solid #10b981;
    color: #ffffff;
    font-weight: 600;
    padding: 7px 18px;
    border-radius: 7px;
}
QPushButton#secondaryActionBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #10b981, stop:1 #059669);
    border-color: #34d399;
}
QPushButton#secondaryActionBtn:pressed {
    background: #065f46;
}

/* Danger Button - Red Tint */
QPushButton#dangerActionBtn {
    background-color: #2c1618;
    border: 1px solid #5c2226;
    color: #ff6b6b;
    font-weight: 500;
    padding: 7px 14px;
    border-radius: 7px;
}
QPushButton#dangerActionBtn:hover {
    background-color: #3d1b1f;
    border-color: #7d2a30;
    color: #ff8585;
}
QPushButton#dangerActionBtn:pressed {
    background-color: #221012;
}

/* Navigation Segmented Buttons */
QPushButton#navBtn {
    background-color: #23242e;
    border: 1px solid #31333f;
    border-radius: 5px;
    padding: 4px 9px;
    font-size: 12px;
    color: #c4c5cf;
}
QPushButton#navBtn:hover {
    background-color: #2f313e;
    border-color: #434555;
    color: #ffffff;
}
QPushButton#navBtn:pressed {
    background-color: #1a1b22;
}

/* Quick Shortcut Pills */
QPushButton#shortcutPill {
    background-color: #22232c;
    border: 1px solid #30313d;
    border-radius: 12px;
    padding: 3px 11px;
    font-size: 11px;
    font-weight: 500;
    color: #b0b2be;
}
QPushButton#shortcutPill:hover {
    background-color: #2d2f3b;
    border-color: #424454;
    color: #ffffff;
}
QPushButton#shortcutPill:pressed {
    background-color: #1a1b22;
}

/* Line Edit / Path Bar / Search */
QLineEdit {
    background-color: #14151a;
    border: 1px solid #2d2e3a;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f0f0f5;
    font-size: 12px;
}
QLineEdit:focus {
    border: 1px solid #0071e3;
    background-color: #181920;
}

/* Capsule Search Field */
QLineEdit#searchField {
    background-color: #14151a;
    border: 1px solid #2d2e3a;
    border-radius: 13px;
    padding: 4px 12px;
    color: #ffffff;
    font-size: 12px;
}
QLineEdit#searchField:focus {
    border: 1px solid #0071e3;
    background-color: #17181f;
}

/* Table View */
QTableView {
    background-color: #16171d;
    alternate-background-color: #1a1b22;
    border: none;
    gridline-color: transparent;
    selection-background-color: #0071e3;
    selection-color: #ffffff;
    outline: none;
}

QTableView::item {
    padding: 4px 8px;
    border-bottom: 1px solid #21222b;
}

QTableView::item:hover {
    background-color: #22242e;
}

QTableView::item:selected {
    background-color: #0071e3;
    color: #ffffff;
}

/* Table Header */
QHeaderView::section {
    background-color: #1e1f27;
    color: #8c8d99;
    font-size: 11px;
    font-weight: 600;
    padding: 7px 10px;
    border: none;
    border-bottom: 1px solid #2b2c37;
    border-right: 1px solid #242530;
    letter-spacing: 0.6px;
}

QHeaderView::section:hover {
    background-color: #252631;
    color: #e0e0ea;
}

/* ScrollBars */
QScrollBar:vertical {
    background: #14151a;
    width: 9px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #333542;
    min-height: 24px;
    border-radius: 4px;
    margin: 2px;
}
QScrollBar::handle:vertical:hover {
    background: #4a4d5e;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QScrollBar:horizontal {
    background: #14151a;
    height: 9px;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background: #333542;
    min-width: 24px;
    border-radius: 4px;
    margin: 2px;
}
QScrollBar::handle:horizontal:hover {
    background: #4a4d5e;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}

/* Status Bar */
QStatusBar {
    background-color: #14151a;
    border-top: 1px solid #24252e;
    color: #9293a0;
    font-size: 12px;
    padding: 5px 12px;
}

/* Progress Bar */
QProgressBar {
    background-color: #22232c;
    border: 1px solid #333542;
    border-radius: 6px;
    text-align: center;
    color: #ffffff;
    font-size: 11px;
    font-weight: 600;
    height: 18px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0071e3, stop:1 #38bdf8);
    border-radius: 5px;
}

/* Menu & Context Menu */
QMenu {
    background-color: #1e1f27;
    border: 1px solid #31333f;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item {
    padding: 6px 22px;
    border-radius: 5px;
    color: #e5e5eb;
}
QMenu::item:selected {
    background-color: #0071e3;
    color: #ffffff;
}
QMenu::separator {
    height: 1px;
    background-color: #2c2e39;
    margin: 4px 8px;
}

/* Tooltip */
QToolTip {
    background-color: #22232c;
    color: #ffffff;
    border: 1px solid #3e404f;
    border-radius: 5px;
    padding: 5px 9px;
    font-size: 11px;
}
"""
