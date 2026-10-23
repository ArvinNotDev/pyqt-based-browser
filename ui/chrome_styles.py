"""Focused premium styling for ARMA's native browser chrome.

The main application themes still own dialogs and feature panels. These final,
browser-chrome-only rules make the title bar, navigation toolbar, tabs, address
field, menus, and bookmarks strip feel like one carefully composed surface.
"""
from __future__ import annotations

LIGHT_CHROME_POLISH = """
/* ARMA / porcelain glass — light chrome */
QFrame#browserShell {
    background: #edf2f8;
    border: 1px solid rgba(255,255,255,235);
    border-radius: 18px;
}
QWidget#customTitleBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(250,252,255,255), stop:1 rgba(239,244,251,255));
    border-bottom: 1px solid rgba(196,208,225,160);
    border-top-left-radius: 17px;
    border-top-right-radius: 17px;
}
QLabel#titleBarLogo {
    color: #ffffff;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #6aa6ff, stop:1 #3269c8);
    border: 1px solid rgba(255,255,255,210);
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}
QLabel#titleBarTitle {
    color: #3d4b60;
    font-size: 12px;
    font-weight: 600;
}
QToolButton#windowMinimizeButton, QToolButton#windowMaximizeButton,
QToolButton#windowCloseButton {
    color: #68778c;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0;
    font-size: 14px;
}
QToolButton#windowMinimizeButton:hover, QToolButton#windowMaximizeButton:hover {
    color: #27364a;
    background: rgba(203,216,234,150);
    border-color: rgba(177,195,220,145);
}
QToolButton#windowCloseButton:hover {
    color: #ffffff;
    background: #d94e58;
    border-color: #d94e58;
}
QToolBar#NavigationBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(250,252,255,255), stop:1 rgba(235,241,249,255));
    border: 1px solid rgba(255,255,255,235);
    border-bottom-color: rgba(190,204,224,235);
    border-radius: 12px;
    spacing: 4px;
    padding: 1px 8px;
}
QToolBar::separator {
    background: rgba(150,166,190,115);
    width: 1px;
    margin: 8px 5px;
}
QToolButton#navigationToolButton, QToolButton#utilityToolButton, QToolButton#bookmarkMenuButton {
    color: #55647a;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 11px;
    padding: 3px 7px;
    min-width: 30px;
    min-height: 32px;
}
QToolButton#navigationToolButton:hover, QToolButton#utilityToolButton:hover, QToolButton#bookmarkMenuButton:hover {
    color: #243852;
    background: rgba(207,222,244,190);
    border-color: rgba(177,199,230,185);
}
QToolButton#navigationToolButton:pressed, QToolButton#utilityToolButton:pressed, QToolButton#bookmarkMenuButton:pressed {
    background: rgba(190,211,240,225);
    border-color: rgba(151,180,221,220);
}
QToolButton#navigationToolButton:focus, QToolButton#utilityToolButton:focus, QToolButton#bookmarkMenuButton:focus {
    border-color: #6b9ce4;
}
QToolButton#navigationToolButton:disabled, QToolButton#utilityToolButton:disabled {
    color: #a4afbf;
    background: transparent;
    border-color: transparent;
}
QLineEdit#urlBar {
    color: #26364c;
    background: rgba(255,255,255,250);
    border: 1px solid rgba(202,214,232,245);
    border-radius: 10px;
    padding: 4px 15px;
    min-height: 30px;
    selection-color: #ffffff;
    selection-background-color: #477fcf;
}
QLineEdit#urlBar:hover {
    background: #ffffff;
    border-color: #b4c8e6;
}
QLineEdit#urlBar:focus {
    color: #1c2d43;
    background: #ffffff;
    border: 1px solid #6195e2;
}
QLineEdit#urlBar::placeholder { color: #8c99ab; }
QToolButton#menuButton {
    color: #50617a;
    background: rgba(255,255,255,195);
    border: 1px solid rgba(190,205,227,220);
    border-radius: 10px;
    padding: 0;
    min-width: 34px;
    max-width: 34px;
    min-height: 30px;
    max-height: 30px;
}
QToolButton#menuButton:hover, QToolButton#menuButton[menuOpen="true"] {
    color: #24446e;
    background: #e1ecfb;
    border-color: #a9c5ee;
}
QToolButton#menuButton[gamingMode="true"] {
    color: #245eae;
    background: #dbe9fc;
    border-color: #9dbcec;
}
QMenu {
    color: #28384e;
    background: rgba(250,252,255,252);
    border: 1px solid rgba(196,210,231,240);
    border-radius: 12px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 30px 8px 12px;
    border-radius: 7px;
    margin: 1px 0;
}
QMenu::item:selected {
    color: #1c3e6c;
    background: rgba(213,229,251,245);
}
QMenu::item:disabled { color: #a3adbb; }
QMenu::separator {
    background: rgba(166,181,203,145);
    height: 1px;
    margin: 5px 8px;
}
QFrame#suggestionPopup {
    background: rgba(250,252,255,252);
    border: 1px solid rgba(193,209,231,240);
    border-radius: 13px;
}
QListWidget#suggestionList {
    color: #2d3d53;
    background: transparent;
    border: none;
    outline: none;
    padding: 4px;
}
QListWidget#suggestionList::item {
    padding: 8px 10px;
    border-radius: 7px;
}
QListWidget#suggestionList::item:hover {
    background: rgba(223,235,251,180);
}
QListWidget#suggestionList::item:selected {
    color: #1c3e6c;
    background: rgba(207,226,252,245);
}
QFrame#browserTabBar {
    background: rgba(18,23,31,150);
    border: 1px solid rgba(255,255,255,32);
    border-bottom-color: rgba(255,255,255,22);
    border-radius: 11px;
}
QFrame#browserTab {
    color: #a9b7c9;
    background: rgba(50,60,75,75);
    border: 1px solid rgba(255,255,255,24);
    border-radius: 9px;
}
QFrame#browserTab:hover {
    color: #344761;
    background: rgba(255,255,255,175);
    border-color: rgba(190,207,232,165);
}
QFrame#browserTab[active="true"] {
    color: #edf4ff;
    background: rgba(55,66,83,235);
    border: 1px solid rgba(152,178,214,110);
    border-top: 2px solid #80b3fb;
}
QPushButton#tabPlusButton {
    color: #536782;
    background: rgba(255,255,255,118);
    border: 1px solid rgba(255,255,255,165);
    border-radius: 10px;
    min-width: 32px;
    min-height: 30px;
    font-size: 19px;
}
QPushButton#tabPlusButton:hover {
    color: #244d82;
    background: rgba(255,255,255,235);
    border-color: rgba(164,192,231,235);
}
QPushButton#tabCloseButton {
    color: #8592a5;
    background: transparent;
    border: none;
    border-radius: 7px;
    min-width: 22px;
    min-height: 22px;
}
QPushButton#tabCloseButton:hover {
    color: #ffffff;
    background: #d94e58;
}
QWidget#BookmarksBar {
    color: #627188;
    background: rgba(232,238,247,225);
    border: none;
    border-bottom: 1px solid rgba(196,208,226,190);
}
QToolButton#bookmarkItem, QToolButton#bookmarkMore, QToolButton#bookmarkManage {
    color: #53647c;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 4px 9px;
}
QToolButton#bookmarkItem:hover, QToolButton#bookmarkMore:hover, QToolButton#bookmarkManage:hover {
    color: #26446b;
    background: rgba(255,255,255,195);
    border-color: rgba(192,210,237,190);
}
QProgressBar {
    background: rgba(151,174,208,75);
    border: none;
    border-radius: 2px;
    max-height: 3px;
    min-height: 3px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #81b9ff, stop:1 #4279d0);
    border-radius: 2px;
}
QScrollBar:vertical {
    width: 9px;
    margin: 3px 2px;
    background: transparent;
}
QScrollBar::handle:vertical {
    min-height: 28px;
    border-radius: 4px;
    background: rgba(121,139,164,105);
}
QScrollBar::handle:vertical:hover { background: rgba(99,121,154,170); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip {
    color: #2d3d53;
    background: rgba(250,252,255,252);
    border: 1px solid rgba(187,204,229,240);
    border-radius: 7px;
    padding: 5px 8px;
}


/* Compact frosted browser chrome. */
QToolBar#NavigationBar { border-radius: 12px; padding: 1px 8px; spacing: 4px; }
QLineEdit#urlBar { border-radius: 10px; min-height: 26px; max-height: 30px; padding: 4px 12px; }
QFrame#browserTabBar {
    background: rgba(220,228,240,140);
    border: 1px solid rgba(255,255,255,180);
    border-bottom-color: rgba(195,207,225,205);
    border-radius: 10px;
}
QFrame#browserTab {
    color: #68778b; background: rgba(255,255,255,72);
    border: 1px solid rgba(255,255,255,105); border-radius: 8px;
}
QFrame#browserTab:hover { color: #344761; background: rgba(255,255,255,175); border-color: rgba(190,207,232,165); }
QFrame#browserTab[active="true"] {
    color: #253a56; background: rgba(255,255,255,235);
    border: 1px solid rgba(187,205,231,235); border-top: 2px solid #5c94e5;
}
QToolButton#bookmarkMenuButton {
    color: #53647c; background: rgba(255,255,255,92);
    border: 1px solid rgba(255,255,255,150); border-radius: 9px;
    padding: 3px 8px; min-width: 76px; min-height: 26px;
}
QToolButton#bookmarkMenuButton:hover { background: rgba(255,255,255,205); border-color: rgba(192,210,237,190); }
QMenu#bookmarksPopupMenu { padding: 6px; }
QMenu#bookmarksPopupMenu::item { padding: 8px 28px 8px 12px; border-radius: 7px; }
"""

DARK_CHROME_POLISH = """
/* ARMA / obsidian glass — dark chrome */
QFrame#browserShell {
    background: #171c24;
    border: 1px solid rgba(255,255,255,34);
    border-radius: 18px;
}
QWidget#customTitleBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(31,38,49,255), stop:1 rgba(23,29,39,255));
    border-bottom: 1px solid rgba(255,255,255,26);
    border-top-left-radius: 17px;
    border-top-right-radius: 17px;
}
QLabel#titleBarLogo {
    color: #ffffff;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #78b3ff, stop:1 #346fc8);
    border: 1px solid rgba(255,255,255,75);
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}
QLabel#titleBarTitle {
    color: #c2cbd9;
    font-size: 12px;
    font-weight: 600;
}
QToolButton#windowMinimizeButton, QToolButton#windowMaximizeButton,
QToolButton#windowCloseButton {
    color: #a2aec0;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 0;
    font-size: 14px;
}
QToolButton#windowMinimizeButton:hover, QToolButton#windowMaximizeButton:hover {
    color: #edf3fc;
    background: rgba(78,92,113,135);
    border-color: rgba(130,150,179,95);
}
QToolButton#windowCloseButton:hover {
    color: #ffffff;
    background: #d94e58;
    border-color: #d94e58;
}
QToolBar#NavigationBar {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 rgba(37,45,58,255), stop:1 rgba(27,34,45,255));
    border: 1px solid rgba(255,255,255,38);
    border-bottom-color: rgba(255,255,255,24);
    border-radius: 12px;
    spacing: 4px;
    padding: 1px 8px;
}
QToolBar::separator {
    background: rgba(170,184,205,58);
    width: 1px;
    margin: 8px 5px;
}
QToolButton#navigationToolButton, QToolButton#utilityToolButton, QToolButton#bookmarkMenuButton {
    color: #bbc7d8;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 11px;
    padding: 3px 7px;
    min-width: 30px;
    min-height: 32px;
}
QToolButton#navigationToolButton:hover, QToolButton#utilityToolButton:hover, QToolButton#bookmarkMenuButton:hover {
    color: #f0f5fc;
    background: rgba(100,121,151,92);
    border-color: rgba(155,178,211,72);
}
QToolButton#navigationToolButton:pressed, QToolButton#utilityToolButton:pressed, QToolButton#bookmarkMenuButton:pressed {
    background: rgba(115,143,184,115);
    border-color: rgba(152,182,225,95);
}
QToolButton#navigationToolButton:focus, QToolButton#utilityToolButton:focus, QToolButton#bookmarkMenuButton:focus {
    border-color: #7eb1fa;
}
QToolButton#navigationToolButton:disabled, QToolButton#utilityToolButton:disabled {
    color: #657286;
    background: transparent;
    border-color: transparent;
}
QLineEdit#urlBar {
    color: #e7edf6;
    background: rgba(15,20,28,248);
    border: 1px solid rgba(112,129,153,135);
    border-radius: 10px;
    padding: 4px 15px;
    min-height: 30px;
    selection-color: #ffffff;
    selection-background-color: #3e6eac;
}
QLineEdit#urlBar:hover {
    color: #f4f7fc;
    background: rgba(19,26,36,255);
    border-color: rgba(137,157,187,185);
}
QLineEdit#urlBar:focus {
    color: #f6f9fd;
    background: #151e2a;
    border: 1px solid #7eb1fa;
}
QLineEdit#urlBar::placeholder { color: #8492a6; }
QToolButton#menuButton {
    color: #c3cedd;
    background: rgba(60,72,90,125);
    border: 1px solid rgba(255,255,255,48);
    border-radius: 10px;
    padding: 0;
    min-width: 34px;
    max-width: 34px;
    min-height: 30px;
    max-height: 30px;
}
QToolButton#menuButton:hover, QToolButton#menuButton[menuOpen="true"] {
    color: #e8f2ff;
    background: rgba(86,112,149,178);
    border-color: rgba(139,177,232,130);
}
QToolButton#menuButton[gamingMode="true"] {
    color: #b6d5ff;
    background: rgba(59,87,127,190);
    border-color: rgba(124,169,232,135);
}
QMenu {
    color: #e2eaf5;
    background: rgba(29,36,47,252);
    border: 1px solid rgba(145,162,187,95);
    border-radius: 12px;
    padding: 6px;
}
QMenu::item {
    padding: 8px 30px 8px 12px;
    border-radius: 7px;
    margin: 1px 0;
}
QMenu::item:selected {
    color: #f2f7ff;
    background: rgba(89,126,180,125);
}
QMenu::item:disabled { color: #68778c; }
QMenu::separator {
    background: rgba(147,164,190,68);
    height: 1px;
    margin: 5px 8px;
}
QFrame#suggestionPopup {
    background: rgba(25,32,43,252);
    border: 1px solid rgba(112,132,160,125);
    border-radius: 13px;
}
QListWidget#suggestionList {
    color: #dce5f2;
    background: transparent;
    border: none;
    outline: none;
    padding: 4px;
}
QListWidget#suggestionList::item {
    padding: 8px 10px;
    border-radius: 7px;
}
QListWidget#suggestionList::item:hover {
    background: rgba(81,101,130,105);
}
QListWidget#suggestionList::item:selected {
    color: #f0f6ff;
    background: rgba(67,102,154,180);
}
QFrame#browserTabBar {
    background: rgba(18,23,31,150);
    border: 1px solid rgba(255,255,255,32);
    border-bottom-color: rgba(255,255,255,22);
    border-radius: 11px;
}
QFrame#browserTab {
    color: #a9b7c9;
    background: rgba(50,60,75,75);
    border: 1px solid rgba(255,255,255,24);
    border-radius: 9px;
}
QFrame#browserTab:hover {
    color: #dbe5f2;
    background: rgba(67,80,101,155);
    border-color: rgba(147,169,201,75);
}
QFrame#browserTab[active="true"] {
    color: #edf4ff;
    background: rgba(55,66,83,235);
    border: 1px solid rgba(152,178,214,110);
    border-top: 2px solid #80b3fb;
}
QPushButton#tabPlusButton {
    color: #a9b8cc;
    background: rgba(48,59,75,150);
    border: 1px solid rgba(255,255,255,30);
    border-radius: 10px;
    min-width: 32px;
    min-height: 30px;
    font-size: 19px;
}
QPushButton#tabPlusButton:hover {
    color: #e8f2ff;
    background: rgba(75,94,123,200);
    border-color: rgba(130,175,244,110);
}
QPushButton#tabCloseButton {
    color: #7f8da1;
    background: transparent;
    border: none;
    border-radius: 7px;
    min-width: 22px;
    min-height: 22px;
}
QPushButton#tabCloseButton:hover {
    color: #ffffff;
    background: #d94e58;
}
QWidget#BookmarksBar {
    color: #9cacc1;
    background: rgba(22,28,37,245);
    border: none;
    border-bottom: 1px solid rgba(255,255,255,22);
}
QToolButton#bookmarkItem, QToolButton#bookmarkMore, QToolButton#bookmarkManage {
    color: #bac6d7;
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 4px 9px;
}
QToolButton#bookmarkItem:hover, QToolButton#bookmarkMore:hover, QToolButton#bookmarkManage:hover {
    color: #eff5ff;
    background: rgba(68,83,106,155);
    border-color: rgba(145,166,197,70);
}
QProgressBar {
    background: rgba(128,151,183,36);
    border: none;
    border-radius: 2px;
    max-height: 3px;
    min-height: 3px;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #80b8ff, stop:1 #4786e3);
    border-radius: 2px;
}
QScrollBar:vertical {
    width: 9px;
    margin: 3px 2px;
    background: transparent;
}
QScrollBar::handle:vertical {
    min-height: 28px;
    border-radius: 4px;
    background: rgba(133,151,177,95);
}
QScrollBar::handle:vertical:hover { background: rgba(159,180,210,145); }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QToolTip {
    color: #e0e9f5;
    background: rgba(29,36,47,252);
    border: 1px solid rgba(130,149,177,130);
    border-radius: 7px;
    padding: 5px 8px;
}


/* Compact obsidian-glass browser chrome. */
QToolBar#NavigationBar { border-radius: 12px; padding: 1px 8px; spacing: 4px; }
QLineEdit#urlBar { border-radius: 10px; min-height: 26px; max-height: 30px; padding: 4px 12px; }
QFrame#browserTabBar {
    background: rgba(18,23,31,150);
    border: 1px solid rgba(255,255,255,32);
    border-bottom-color: rgba(255,255,255,22);
    border-radius: 10px;
}
QFrame#browserTab {
    color: #a9b7c9; background: rgba(50,60,75,75);
    border: 1px solid rgba(255,255,255,30); border-radius: 8px;
}
QFrame#browserTab:hover { color: #dbe5f2; background: rgba(67,80,101,155); border-color: rgba(147,169,201,75); }
QFrame#browserTab[active="true"] {
    color: #edf4ff; background: rgba(55,66,83,235);
    border: 1px solid rgba(152,178,214,110); border-top: 2px solid #80b3fb;
}
QToolButton#bookmarkMenuButton {
    color: #c7d4e6; background: rgba(50,60,75,145);
    border: 1px solid rgba(255,255,255,38); border-radius: 9px;
    padding: 3px 8px; min-width: 76px; min-height: 26px;
}
QToolButton#bookmarkMenuButton:hover { color: #edf4ff; background: rgba(75,94,123,205); border-color: rgba(130,175,244,110); }
QMenu#bookmarksPopupMenu { padding: 6px; }
QMenu#bookmarksPopupMenu::item { padding: 8px 28px 8px 12px; border-radius: 7px; }
"""

__all__ = ["LIGHT_CHROME_POLISH", "DARK_CHROME_POLISH"]
