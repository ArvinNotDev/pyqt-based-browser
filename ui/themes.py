"""Shared light and dark styles for browser chrome and its dialogs."""

light_theme = """
QMainWindow, QDialog, QWidget {
    background-color: #f7f8fa;
    color: #20242a;
    font-family: "Segoe UI";
    font-size: 13px;
}
QLabel { background-color: transparent; }

QToolBar#NavigationBar {
    background-color: #f7f8fa;
    border: none;
    border-bottom: 1px solid #e3e6eb;
    spacing: 4px;
    padding: 5px 8px;
}

QToolBar::separator {
    background: #d9dde4;
    width: 1px;
    margin: 8px 5px;
}

QToolButton#navigationToolButton, QToolButton#utilityToolButton,
QToolButton#newTabButton {
    background: transparent;
    color: #3f4752;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 5px 8px;
    min-height: 28px;
}
QToolButton#navigationToolButton:hover, QToolButton#utilityToolButton:hover,
QToolButton#newTabButton:hover { background-color: #e9edf3; }
QToolButton#navigationToolButton:pressed, QToolButton#utilityToolButton:pressed,
QToolButton#newTabButton:pressed { background-color: #dfe5ed; }
QToolButton#navigationToolButton:focus, QToolButton#utilityToolButton:focus,
QToolButton#newTabButton:focus { border-color: #3979d6; }
QToolButton:disabled, QPushButton:disabled { color: #a6adb8; }

QLineEdit#urlBar {
    background-color: #ffffff;
    color: #20242a;
    border: 1px solid #d9dde4;
    border-radius: 17px;
    padding: 7px 14px;
    min-height: 30px;
    selection-background-color: #cfe0fb;
}
QLineEdit#urlBar:hover { border-color: #b8c0cc; }
QLineEdit#urlBar:focus { border: 1px solid #3979d6; }
QLineEdit#urlBar::placeholder { color: #78818d; }

QFrame#suggestionPopup {
    background-color: #ffffff;
    border: 1px solid #d9dde4;
    border-radius: 8px;
}
QListWidget#suggestionList {
    background: transparent;
    color: #20242a;
    border: none;
    outline: none;
    padding: 4px;
}
QListWidget#suggestionList::item { padding: 7px 10px; border-radius: 5px; }
QListWidget#suggestionList::item:selected { background-color: #e8f0fc; color: #20242a; }

QWidget#BookmarksBar {
    background-color: #f7f8fa;
    border-bottom: 1px solid #e3e6eb;
}
QLabel#bookmarksHeading, QLabel#bookmarksEmpty, QLabel#dialogStatus {
    color: #68717d;
}
QToolButton#bookmarkItem, QToolButton#bookmarkMore, QToolButton#bookmarkManage {
    background: transparent;
    color: #3f4752;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 24px;
}
QToolButton#bookmarkItem:hover, QToolButton#bookmarkMore:hover,
QToolButton#bookmarkManage:hover { background-color: #e9edf3; }
QToolButton#bookmarkItem:focus, QToolButton#bookmarkMore:focus,
QToolButton#bookmarkManage:focus { border-color: #3979d6; }

QDialog { background-color: #f7f8fa; }
QLabel#dialogTitle { color: #20242a; font-size: 18px; font-weight: 600; }
QListWidget, QTableWidget, QTreeWidget {
    background-color: #ffffff;
    color: #20242a;
    border: 1px solid #d9dde4;
    border-radius: 8px;
    alternate-background-color: #f5f7fa;
    selection-background-color: #e8f0fc;
    selection-color: #20242a;
    outline: none;
}
QTableWidget::item { background-color: transparent; padding: 4px 6px; }
QTableWidget::item:hover { background-color: #f0f4fa; }
QWidget#downloadCell { background-color: transparent; }
QHeaderView::section {
    background-color: #f0f2f6;
    color: #4c5561;
    border: none;
    border-bottom: 1px solid #d9dde4;
    padding: 7px 9px;
    font-weight: 600;
}
QPushButton {
    background-color: #edf0f4;
    color: #28313c;
    border: 1px solid #d9dde4;
    border-radius: 7px;
    padding: 7px 12px;
    min-height: 20px;
}
QPushButton:hover { background-color: #e3e8ef; }
QPushButton:pressed { background-color: #d8e0ea; }
QPushButton:focus { border-color: #3979d6; }
QPushButton:disabled { color: #a6adb8; background-color: #f1f2f4; }
QPushButton#primaryButton { background-color: #326fca; color: #ffffff; border-color: #326fca; }
QPushButton#primaryButton:hover { background-color: #285eae; }
QPushButton#dangerButton { color: #a33b36; }
QProgressBar {
    background-color: #e9edf2;
    color: #4c5561;
    border: none;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
    text-align: center;
}
QProgressBar::chunk { background-color: #3979d6; border-radius: 4px; }
QToolTip {
    background-color: #ffffff;
    color: #20242a;
    border: 1px solid #cdd3dc;
    padding: 5px 7px;
}
"""


dark_theme = """
QMainWindow, QDialog, QWidget {
    background-color: #1b1e23;
    color: #e4e8ee;
    font-family: "Segoe UI";
    font-size: 13px;
}
QLabel { background-color: transparent; }

QToolBar#NavigationBar {
    background-color: #1b1e23;
    border: none;
    border-bottom: 1px solid #30353d;
    spacing: 4px;
    padding: 5px 8px;
}

QToolBar::separator {
    background: #3b424c;
    width: 1px;
    margin: 8px 5px;
}

QToolButton#navigationToolButton, QToolButton#utilityToolButton,
QToolButton#newTabButton {
    background: transparent;
    color: #c7ced8;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 5px 8px;
    min-height: 28px;
}
QToolButton#navigationToolButton:hover, QToolButton#utilityToolButton:hover,
QToolButton#newTabButton:hover { background-color: #2a3038; }
QToolButton#navigationToolButton:pressed, QToolButton#utilityToolButton:pressed,
QToolButton#newTabButton:pressed { background-color: #343c47; }
QToolButton#navigationToolButton:focus, QToolButton#utilityToolButton:focus,
QToolButton#newTabButton:focus { border-color: #82aff4; }
QToolButton:disabled, QPushButton:disabled { color: #68717d; }

QLineEdit#urlBar {
    background-color: #252a31;
    color: #e4e8ee;
    border: 1px solid #3a414b;
    border-radius: 17px;
    padding: 7px 14px;
    min-height: 30px;
    selection-background-color: #3d5d89;
}
QLineEdit#urlBar:hover { border-color: #525c69; }
QLineEdit#urlBar:focus { border: 1px solid #82aff4; }
QLineEdit#urlBar::placeholder { color: #9ba5b2; }

QFrame#suggestionPopup {
    background-color: #252a31;
    border: 1px solid #414954;
    border-radius: 8px;
}
QListWidget#suggestionList {
    background: transparent;
    color: #e4e8ee;
    border: none;
    outline: none;
    padding: 4px;
}
QListWidget#suggestionList::item { padding: 7px 10px; border-radius: 5px; }
QListWidget#suggestionList::item:selected { background-color: #35465f; color: #ffffff; }

QWidget#BookmarksBar {
    background-color: #1b1e23;
    border-bottom: 1px solid #30353d;
}
QLabel#bookmarksHeading, QLabel#bookmarksEmpty, QLabel#dialogStatus {
    color: #a5afbb;
}
QToolButton#bookmarkItem, QToolButton#bookmarkMore, QToolButton#bookmarkManage {
    background: transparent;
    color: #c7ced8;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 24px;
}
QToolButton#bookmarkItem:hover, QToolButton#bookmarkMore:hover,
QToolButton#bookmarkManage:hover { background-color: #2a3038; }
QToolButton#bookmarkItem:focus, QToolButton#bookmarkMore:focus,
QToolButton#bookmarkManage:focus { border-color: #82aff4; }

QDialog { background-color: #1b1e23; }
QLabel#dialogTitle { color: #edf0f5; font-size: 18px; font-weight: 600; }
QListWidget, QTableWidget, QTreeWidget {
    background-color: #22272e;
    color: #e4e8ee;
    border: 1px solid #3a414b;
    border-radius: 8px;
    alternate-background-color: #252b33;
    selection-background-color: #35465f;
    selection-color: #ffffff;
    outline: none;
}
QTableWidget::item { background-color: transparent; padding: 4px 6px; }
QTableWidget::item:hover { background-color: #2b323c; }
QWidget#downloadCell { background-color: transparent; }
QHeaderView::section {
    background-color: #292f37;
    color: #c7ced8;
    border: none;
    border-bottom: 1px solid #3a414b;
    padding: 7px 9px;
    font-weight: 600;
}
QPushButton {
    background-color: #2b3139;
    color: #e4e8ee;
    border: 1px solid #3a414b;
    border-radius: 7px;
    padding: 7px 12px;
    min-height: 20px;
}
QPushButton:hover { background-color: #343c47; }
QPushButton:pressed { background-color: #3c4653; }
QPushButton:focus { border-color: #82aff4; }
QPushButton:disabled { color: #68717d; background-color: #252a31; }
QPushButton#primaryButton { background-color: #376fb9; color: #ffffff; border-color: #376fb9; }
QPushButton#primaryButton:hover { background-color: #4380ce; }
QPushButton#dangerButton { color: #f0958e; }
QProgressBar {
    background-color: #303740;
    color: #c7ced8;
    border: none;
    border-radius: 4px;
    min-height: 8px;
    max-height: 8px;
    text-align: center;
}
QProgressBar::chunk { background-color: #82aff4; border-radius: 4px; }
QToolTip {
    background-color: #252a31;
    color: #e4e8ee;
    border: 1px solid #414954;
    padding: 5px 7px;
}
"""
