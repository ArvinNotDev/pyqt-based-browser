"""Shared light and dark styles for browser chrome and its dialogs."""

light_theme = """
QMainWindow, QDialog, QWidget {
    background-color: #f7f8fa;
    color: #20242a;
    font-family: "Segoe UI";
    font-size: 13px;
}
QLabel { background-color: transparent; }

QWidget#browserWindowRoot { background: transparent; }
QFrame#browserShell { background-color: rgba(247,249,253,248); border: 1px solid rgba(255,255,255,235); border-radius: 17px; }
QFrame#browserShell[edgeToEdge="true"] { border: 0; border-radius: 0; }
QFrame#browserTabBar { background: rgba(231,237,246,220); border: 1px solid rgba(255,255,255,175); border-radius: 12px; }
QWidget#browserContentCard { background: #e9edf3; border: 1px solid #dce1e8; border-radius: 14px; }
QDockWidget#proxyDock { border: 1px solid #dce1e8; border-radius: 14px; }
QDockWidget#proxyDock::title { background: #eef1f5; border-top-left-radius: 13px; border-top-right-radius: 13px; padding: 7px 10px; }

QWidget#customTitleBar {
    background-color: rgba(242,246,252,235);
    border-bottom: 1px solid rgba(255,255,255,205);
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
}
QLabel#titleBarLogo {
    color: #ffffff;
    background-color: #3979d6;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 700;
}
QLabel#titleBarTitle { color: #25303d; font-size: 12px; font-weight: 600; }
QToolButton#windowMinimizeButton, QToolButton#windowMaximizeButton,
QToolButton#windowCloseButton {
    color: #46505c;
    background: transparent;
    border: none;
    border-radius: 13px;
    font-size: 16px;
}
QToolButton#windowMinimizeButton:hover, QToolButton#windowMaximizeButton:hover {
    background-color: #dfe5ed;
}
QToolButton#windowCloseButton:hover { color: #ffffff; background-color: #d34c4c; }

QToolBar#NavigationBar {
    background-color: rgba(247,249,253,225);
    border: 1px solid rgba(255,255,255,215);
    border-bottom: 1px solid rgba(220,228,239,210);
    border-radius: 12px;
    spacing: 3px;
    padding: 1px 6px;
}

QToolBar::separator {
    background: #d9dde4;
    width: 1px;
    margin: 6px 4px;
}

QToolButton#navigationToolButton, QToolButton#utilityToolButton {
    background: transparent;
    color: #3f4752;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 3px 7px;
    min-height: 24px;
}
QToolButton#navigationToolButton:hover, QToolButton#utilityToolButton:hover { background-color: #e9edf3; }
QToolButton#navigationToolButton:pressed, QToolButton#utilityToolButton:pressed { background-color: #dfe5ed; }
QToolButton#navigationToolButton:focus, QToolButton#utilityToolButton:focus { border-color: #3979d6; }
QPushButton#tabPlusButton {
    color: #3f4752;
    background-color: #e9edf3;
    border: 1px solid transparent;
    border-radius: 9px;
    font-size: 23px;
    font-weight: 600;
}
QPushButton#tabPlusButton:hover { background-color: #dce5f2; color: #285eae; }
QFrame#browserTab { background: rgba(242,245,249,190); border: 1px solid rgba(255,255,255,185); border-top: 3px solid transparent; border-radius: 10px; }
QFrame#browserTab:hover { background: rgba(255,255,255,220); }
QFrame#browserTab[active="true"] { background: rgba(255,255,255,248); border-color: #d8e2f1; border-top-color: #3979d6; }
QPushButton#tabCloseButton { color: #68717d; background: transparent; border: none; border-radius: 7px; font-size: 16px; padding: 0; }
QPushButton#tabCloseButton:hover { color: #ffffff; background: #d34c4c; }
QFrame#downloadsPanel { background-color: #f1f3f6; border: 1px solid #dce1e8; border-radius: 14px; }
QSplitter#downloadsSplitter { background: transparent; }
QSplitter#downloadsSplitter::handle:horizontal { background: #e1e5eb; width: 8px; margin: 8px 2px; border-radius: 4px; }
QSplitter#downloadsSplitter::handle:horizontal:hover { background: #d5deec; border-radius: 4px; }
QLabel#downloadsTitle { color: #20242a; font-size: 19px; font-weight: 700; }
QLabel#downloadsSubtitle, QLabel#downloadsEmpty, QLabel#downloadSource, QLabel#downloadStatus { color: #68717d; }
QToolButton#downloadsCloseButton, QToolButton#downloadMoreButton { color: #56606c; background: transparent; border: none; border-radius: 7px; font-size: 19px; min-width: 28px; min-height: 28px; }
QToolButton#downloadsCloseButton:hover, QToolButton#downloadMoreButton:hover { background: #e4e8ee; }
QLineEdit#downloadsSearch { background: #ffffff; border: 1px solid #d9dde4; border-radius: 8px; padding: 8px 10px; }
QFrame#downloadCard { background: #ffffff; border: 1px solid #e0e4ea; border-radius: 10px; }
QLabel#downloadFileName { color: #20242a; font-weight: 600; }
QProgressBar#downloadProgress { background: #e7ebf1; border: none; border-radius: 2px; }
QProgressBar#downloadProgress::chunk { background: #3979d6; border-radius: 2px; }
QPushButton#downloadsSecondaryButton { color: #3f4752; background: #ffffff; border: 1px solid #d9dde4; border-radius: 7px; padding: 7px 9px; }
QPushButton#downloadsSecondaryButton:hover { border-color: #3979d6; color: #285eae; }
QPushButton#downloadsPrimaryButton { color: #ffffff; background: #3979d6; border: none; border-radius: 7px; padding: 7px 12px; }
QPushButton#downloadsPrimaryButton:hover { background: #2868c5; }
QFrame#downloadToast { background: #ffffff; border: 1px solid #d9dde4; border-radius: 10px; }
QLabel#downloadToastTitle { color: #20242a; font-weight: 700; }
QLabel#downloadToastFile { color: #68717d; }
QPushButton#downloadToastButton { color: #285eae; background: #e8f0fc; border: none; border-radius: 7px; padding: 7px 10px; }
QToolButton#menuButton {
    background: #eef1f5;
    color: #3f4752;
    border: 1px solid #e1e5eb;
    border-radius: 10px;
    padding: 0 8px;
    min-width: 30px;
    min-height: 28px;
    font-size: 22px;
}
QToolButton#menuButton:hover, QToolButton#menuButton[menuOpen="true"] { background-color: #e0e8f5; border-color: #cbd8eb; color: #285eae; }
QToolButton#menuButton[gamingMode="true"] { color: #285eae; background-color: #e8f0fc; }
QMenu {
    background-color: #ffffff;
    color: #20242a;
    border: 1px solid #d9dde4;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item { padding: 7px 30px 7px 12px; border-radius: 5px; }
QMenu::item:selected { background-color: #e8f0fc; color: #20242a; }
QMenu::separator { height: 1px; background: #e3e6eb; margin: 5px 7px; }
QToolButton:disabled, QPushButton:disabled { color: #a6adb8; }

QLineEdit#urlBar {
    background-color: rgba(255,255,255,235);
    color: #20242a;
    border: 1px solid #d9dde4;
    border-radius: 15px;
    padding: 5px 12px;
    min-height: 25px;
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
    border-radius: 10px;
}
QLabel#bookmarksHeading, QLabel#bookmarksEmpty, QLabel#dialogStatus {
    color: #68717d;
}
QToolButton#bookmarkItem, QToolButton#bookmarkMore, QToolButton#bookmarkManage {
    background: transparent;
    color: #3f4752;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 3px 8px;
    min-height: 22px;
}
QToolButton#bookmarkItem:hover, QToolButton#bookmarkMore:hover,
QToolButton#bookmarkManage:hover { background-color: #e9edf3; }
QToolButton#bookmarkItem:focus, QToolButton#bookmarkMore:focus,
QToolButton#bookmarkManage:focus { border-color: #3979d6; }

QDialog { background-color: #f7f8fa; }
QDialog#settingsDialog { border: 1px solid #dce1e8; border-radius: 15px; }
QLabel#dialogTitle { color: #20242a; font-size: 18px; font-weight: 600; }
QLabel#settingsSubtitle, QLabel#settingsSectionDescription, QLabel#settingsNote,
QLabel#shortcutDescription { color: #68717d; }
QLabel#settingsSectionTitle { color: #20242a; font-size: 17px; font-weight: 600; }
QFrame#settingsCard { background-color: #ffffff; border: 1px solid #e1e5eb; border-radius: 10px; }
QListWidget#settingsNav {
    background-color: transparent;
    border: none;
    outline: none;
}
QListWidget#settingsNav::item { padding: 10px 12px; border-radius: 7px; }
QListWidget#settingsNav::item:selected { background-color: #e8f0fc; color: #285eae; font-weight: 600; }
QListWidget#settingsNav::item:hover:!selected { background-color: #edf0f4; }
QScrollArea#settingsScroll, QScrollArea#downloadsScroll { background: transparent; border: none; }
QLineEdit#settingsInput {
    background-color: #ffffff;
    border: 1px solid #d9dde4;
    border-radius: 7px;
    padding: 8px 10px;
    min-height: 22px;
}
QLineEdit#settingsInput:focus { border-color: #3979d6; }
QLabel#shortcutKey {
    background-color: #f0f2f6;
    color: #3f4752;
    border: 1px solid #d9dde4;
    border-radius: 5px;
    padding: 4px 7px;
    font-family: Consolas;
    font-size: 11px;
}
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
    border-radius: 9px;
    padding: 6px 11px;
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
QScrollBar:vertical { background: transparent; width: 10px; margin: 3px 1px; }
QScrollBar::handle:vertical { background: #c8ced8; min-height: 26px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #aeb8c6; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip {
    background-color: #ffffff;
    color: #20242a;
    border: 1px solid #cdd3dc;
    padding: 5px 7px;
}

/* Shared glass surface refinements for popovers and browser utility panels. */
QMenu { background-color: rgba(255,255,255,246); border-color: rgba(205,215,229,220); }
QFrame#suggestionPopup, QFrame#downloadToast { background-color: rgba(255,255,255,232); border-color: rgba(215,223,234,225); }
QFrame#downloadsPanel, QFrame#downloadCard, QFrame#settingsCard { background-color: rgba(250,252,255,238); }
QWidget#BookmarksBar { background-color: rgba(247,249,253,222); }
QLineEdit#urlBar { background-color: rgba(255,255,255,240); border-color: rgba(207,218,232,235); }
QToolTip { background-color: rgba(255,255,255,248); border-color: rgba(195,207,224,230); }
"""


dark_theme = """
QMainWindow, QDialog, QWidget {
    background-color: #1b1e23;
    color: #e4e8ee;
    font-family: "Segoe UI";
    font-size: 13px;
}
QLabel { background-color: transparent; }
QWidget#browserWindowRoot { background: transparent; }
QFrame#browserShell { background-color: rgba(25,29,36,250); border: 1px solid rgba(255,255,255,35); border-radius: 17px; }
QFrame#browserShell[edgeToEdge="true"] { border: 0; border-radius: 0; }
QFrame#browserTabBar { background: rgba(34,40,49,230); border: 1px solid rgba(255,255,255,24); border-radius: 12px; }
QWidget#browserContentCard { background: #22272e; border: 1px solid #30353d; border-radius: 14px; }
QDockWidget#proxyDock { border: 1px solid #30353d; border-radius: 14px; }
QDockWidget#proxyDock::title { background: #22272e; border-top-left-radius: 13px; border-top-right-radius: 13px; padding: 7px 10px; }

QWidget#customTitleBar {
    background-color: rgba(23,27,34,242);
    border-bottom: 1px solid rgba(255,255,255,30);
    border-top-left-radius: 16px;
    border-top-right-radius: 16px;
}
QLabel#titleBarLogo {
    color: #ffffff;
    background-color: #3979d6;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 700;
}
QLabel#titleBarTitle { color: #e4e8ee; font-size: 12px; font-weight: 600; }
QToolButton#windowMinimizeButton, QToolButton#windowMaximizeButton,
QToolButton#windowCloseButton {
    color: #c7ced8;
    background: transparent;
    border: none;
    border-radius: 13px;
    font-size: 16px;
}
QToolButton#windowMinimizeButton:hover, QToolButton#windowMaximizeButton:hover {
    background-color: #30353d;
}
QToolButton#windowCloseButton:hover { color: #ffffff; background-color: #c53f49; }

QToolBar#NavigationBar {
    background-color: rgba(27,31,38,235);
    border: 1px solid rgba(255,255,255,35);
    border-bottom: 1px solid rgba(255,255,255,28);
    border-radius: 12px;
    spacing: 3px;
    padding: 1px 6px;
}

QToolBar::separator {
    background: #3b424c;
    width: 1px;
    margin: 6px 4px;
}

QToolButton#navigationToolButton, QToolButton#utilityToolButton {
    background: transparent;
    color: #c7ced8;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 3px 7px;
    min-height: 24px;
}
QToolButton#navigationToolButton:hover, QToolButton#utilityToolButton:hover { background-color: #2a3038; }
QToolButton#navigationToolButton:pressed, QToolButton#utilityToolButton:pressed { background-color: #343c47; }
QToolButton#navigationToolButton:focus, QToolButton#utilityToolButton:focus { border-color: #82aff4; }
QPushButton#tabPlusButton {
    color: #c7ced8;
    background-color: #2a3038;
    border: 1px solid transparent;
    border-radius: 9px;
    font-size: 23px;
    font-weight: 600;
}
QPushButton#tabPlusButton:hover { background-color: #35465f; color: #a8c9ff; }
QFrame#browserTab { background: rgba(41,47,57,210); border: 1px solid rgba(255,255,255,28); border-top: 3px solid transparent; border-radius: 10px; }
QFrame#browserTab:hover { background: rgba(52,60,72,230); }
QFrame#browserTab[active="true"] { background: rgba(58,66,79,250); border-color: #53627a; border-top-color: #82aff4; }
QPushButton#tabCloseButton { color: #9aa4b1; background: transparent; border: none; border-radius: 7px; font-size: 16px; padding: 0; }
QPushButton#tabCloseButton:hover { color: #ffffff; background: #c53f49; }
QFrame#downloadsPanel { background-color: #1b1e23; border: 1px solid #30353d; border-radius: 14px; }
QSplitter#downloadsSplitter { background: transparent; }
QSplitter#downloadsSplitter::handle:horizontal { background: #303740; width: 8px; margin: 8px 2px; border-radius: 4px; }
QSplitter#downloadsSplitter::handle:horizontal:hover { background: #35465f; border-radius: 4px; }
QLabel#downloadsTitle { color: #e4e8ee; font-size: 19px; font-weight: 700; }
QLabel#downloadsSubtitle, QLabel#downloadsEmpty, QLabel#downloadSource, QLabel#downloadStatus { color: #9aa4b1; }
QToolButton#downloadsCloseButton, QToolButton#downloadMoreButton { color: #c7ced8; background: transparent; border: none; border-radius: 7px; font-size: 19px; min-width: 28px; min-height: 28px; }
QToolButton#downloadsCloseButton:hover, QToolButton#downloadMoreButton:hover { background: #30353d; }
QLineEdit#downloadsSearch { background: #252a31; color: #e4e8ee; border: 1px solid #3a414b; border-radius: 8px; padding: 8px 10px; }
QFrame#downloadCard { background: #252a31; border: 1px solid #3a414b; border-radius: 10px; }
QLabel#downloadFileName { color: #e4e8ee; font-weight: 600; }
QProgressBar#downloadProgress { background: #343c47; border: none; border-radius: 2px; }
QProgressBar#downloadProgress::chunk { background: #82aff4; border-radius: 2px; }
QPushButton#downloadsSecondaryButton { color: #c7ced8; background: #252a31; border: 1px solid #3a414b; border-radius: 7px; padding: 7px 9px; }
QPushButton#downloadsSecondaryButton:hover { border-color: #82aff4; color: #a8c9ff; }
QPushButton#downloadsPrimaryButton { color: #ffffff; background: #3979d6; border: none; border-radius: 7px; padding: 7px 12px; }
QPushButton#downloadsPrimaryButton:hover { background: #4a88e3; }
QFrame#downloadToast { background: #252a31; border: 1px solid #414954; border-radius: 10px; }
QLabel#downloadToastTitle { color: #e4e8ee; font-weight: 700; }
QLabel#downloadToastFile { color: #9aa4b1; }
QPushButton#downloadToastButton { color: #a8c9ff; background: #35465f; border: none; border-radius: 7px; padding: 7px 10px; }
QToolButton#menuButton {
    background: #252a31;
    color: #c7ced8;
    border: 1px solid #343c47;
    border-radius: 10px;
    padding: 0 8px;
    min-width: 30px;
    min-height: 28px;
    font-size: 22px;
}
QToolButton#menuButton:hover, QToolButton#menuButton[menuOpen="true"] { background-color: #35465f; border-color: #4a5c78; color: #a8c9ff; }
QToolButton#menuButton[gamingMode="true"] { color: #a8c9ff; background-color: #35465f; }
QMenu {
    background-color: #252a31;
    color: #e4e8ee;
    border: 1px solid #414954;
    border-radius: 8px;
    padding: 5px;
}
QMenu::item { padding: 7px 30px 7px 12px; border-radius: 5px; }
QMenu::item:selected { background-color: #35465f; color: #ffffff; }
QMenu::separator { height: 1px; background: #3a414b; margin: 5px 7px; }
QToolButton:disabled, QPushButton:disabled { color: #68717d; }

QLineEdit#urlBar {
    background-color: rgba(43,49,59,245);
    color: #e4e8ee;
    border: 1px solid #3a414b;
    border-radius: 15px;
    padding: 5px 12px;
    min-height: 25px;
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
    border-radius: 10px;
}
QLabel#bookmarksHeading, QLabel#bookmarksEmpty, QLabel#dialogStatus {
    color: #a5afbb;
}
QToolButton#bookmarkItem, QToolButton#bookmarkMore, QToolButton#bookmarkManage {
    background: transparent;
    color: #c7ced8;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 3px 8px;
    min-height: 22px;
}
QToolButton#bookmarkItem:hover, QToolButton#bookmarkMore:hover,
QToolButton#bookmarkManage:hover { background-color: #2a3038; }
QToolButton#bookmarkItem:focus, QToolButton#bookmarkMore:focus,
QToolButton#bookmarkManage:focus { border-color: #82aff4; }

QDialog { background-color: #1b1e23; }
QDialog#settingsDialog { border: 1px solid #30353d; border-radius: 15px; }
QLabel#dialogTitle { color: #edf0f5; font-size: 18px; font-weight: 600; }
QLabel#settingsSubtitle, QLabel#settingsSectionDescription, QLabel#settingsNote,
QLabel#shortcutDescription { color: #a5afbb; }
QLabel#settingsSectionTitle { color: #edf0f5; font-size: 17px; font-weight: 600; }
QFrame#settingsCard { background-color: #22272e; border: 1px solid #3a414b; border-radius: 10px; }
QListWidget#settingsNav {
    background-color: transparent;
    border: none;
    outline: none;
}
QListWidget#settingsNav::item { padding: 10px 12px; border-radius: 7px; }
QListWidget#settingsNav::item:selected { background-color: #35465f; color: #ffffff; font-weight: 600; }
QListWidget#settingsNav::item:hover:!selected { background-color: #2a3038; }
QScrollArea#settingsScroll, QScrollArea#downloadsScroll { background: transparent; border: none; }
QLineEdit#settingsInput {
    background-color: #252a31;
    border: 1px solid #3a414b;
    border-radius: 7px;
    padding: 8px 10px;
    min-height: 22px;
}
QLineEdit#settingsInput:focus { border-color: #82aff4; }
QLabel#shortcutKey {
    background-color: #292f37;
    color: #e4e8ee;
    border: 1px solid #3a414b;
    border-radius: 5px;
    padding: 4px 7px;
    font-family: Consolas;
    font-size: 11px;
}
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
    border-radius: 9px;
    padding: 6px 11px;
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
QScrollBar:vertical { background: transparent; width: 10px; margin: 3px 1px; }
QScrollBar::handle:vertical { background: #454e5a; min-height: 26px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #5b6878; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip {
    background-color: #252a31;
    color: #e4e8ee;
    border: 1px solid #414954;
    padding: 5px 7px;
}

QMenu { background-color: rgba(37,43,52,248); border-color: rgba(90,104,124,215); }
QFrame#suggestionPopup, QFrame#downloadToast { background-color: rgba(37,43,52,242); border-color: rgba(85,99,119,220); }
QFrame#downloadsPanel, QFrame#downloadCard, QFrame#settingsCard { background-color: rgba(34,40,49,242); }
QWidget#BookmarksBar { background-color: rgba(27,31,38,232); }
QLineEdit#urlBar { background-color: rgba(43,49,59,248); border-color: rgba(75,87,104,238); }
QToolTip { background-color: rgba(37,43,52,250); border-color: rgba(90,104,124,230); }
"""
