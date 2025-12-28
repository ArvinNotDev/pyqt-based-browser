light_theme = """
/* =======================
   Base
======================= */
QMainWindow, QWidget {
    background-color: #ffffff;
    color: #202124;
    font-family: "Segoe UI", system-ui;
    font-size: 13px;
}

/* =======================
   Navigation / Toolbar
======================= */
QWidget#NavigationBar {
    background-color: #f5f5f5;
}

/* =======================
   LineEdit (URL bar)
======================= */
QLineEdit {
    background-color: #ffffff;
    color: #202124;
    border: 1px solid #d0d0d0;
    border-radius: 18px;
    padding: 4px 8px;
    min-height: 28px;
}

QLineEdit:focus {
    border-color: #1a73e8;
}

QLineEdit::placeholder {
    color: #7a7a7a;
}

/* =======================
   Buttons (general)
======================= */
QPushButton {
    background-color: #f1f3f4;
    color: #202124;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 28px;
}

QPushButton:hover {
    background-color: #e8eaed;
}

QPushButton:pressed {
    background-color: #dadce0;
}

/* icon buttons (nav, arrows, plus) */
QPushButton[icon="true"] {
    background: transparent;
    padding: 4px;
    min-width: 26px;
    min-height: 26px;
}

QPushButton[icon="true"]:hover {
    background-color: rgba(0,0,0,0.06);
    border-radius: 6px;
}

/* =======================
   Custom Tab Button
======================= */
QFrame {
    background: transparent;
}

QFrame[active="false"] {
    background-color: #f1f3f4;
}

QLabel {
    color: #202124;
    font-size: 12px;
}

/* close button inside tab */
QPushButton {
    background: transparent;
}

QPushButton:hover {
    background-color: rgba(0,0,0,0.04);
}

/* =======================
   Progress Bar
======================= */
QProgressBar {
    background: transparent;
    border: none;
    height: 4px;
}

QProgressBar::chunk {
    background-color: #1a73e8;
}

/* =======================
   ScrollArea (tabs)
======================= */
QScrollArea {
    background: transparent;
    border: none;
}

/* =======================
   Tooltip (tab preview)
======================= */
QToolTip {
    background-color: #ffffff;
    color: #202124;
    border: 1px solid #cfcfcf;
    padding: 6px;
    border-radius: 6px;
}

/* =======================
   Web View
======================= */
QWebEngineView {
    background-color: #ffffff;
}
"""


dark_theme = """
/* =======================
   Base
======================= */
QMainWindow, QWidget {
    background-color: #121212;
    color: #e8eaed;
    font-family: "Segoe UI", system-ui;
    font-size: 13px;
}

/* =======================
   Navigation / Toolbar
======================= */
QWidget#NavigationBar {
    background-color: #1f1f1f;
}

/* =======================
   LineEdit (URL bar)
======================= */
QLineEdit {
    background-color: #2b2b2b;
    color: #e8eaed;
    border: 1px solid #444;
    border-radius: 18px;
    padding: 4px 8px;
    min-height: 28px;
}

QLineEdit:focus {
    border-color: #8ab4f8;
}

QLineEdit::placeholder {
    color: #9aa0a6;
}

/* =======================
   Buttons
======================= */
QPushButton {
    background-color: #2b2b2b;
    color: #e8eaed;
    border: none;
    border-radius: 6px;
    padding: 4px 8px;
    min-height: 28px;
}

QPushButton:hover {
    background-color: #353535;
}

QPushButton:pressed {
    background-color: #3f3f3f;
}

/* icon buttons */
QPushButton[icon="true"] {
    background: transparent;
    padding: 4px;
    min-width: 26px;
    min-height: 26px;
}

QPushButton[icon="true"]:hover {
    background-color: rgba(255,255,255,0.06);
    border-radius: 6px;
}

/* =======================
   Custom Tab Button
======================= */
QFrame {
    background: transparent;
}

QLabel {
    color: #e8eaed;
    font-size: 12px;
}

/* close button */
QPushButton {
    background: transparent;
}

QPushButton:hover {
    background-color: rgba(255,255,255,0.05);
}

/* =======================
   Progress Bar
======================= */
QProgressBar {
    background: transparent;
    border: none;
    height: 4px;
}

QProgressBar::chunk {
    background-color: #8ab4f8;
}

/* =======================
   ScrollArea
======================= */
QScrollArea {
    background: transparent;
    border: none;
}

/* =======================
   Tooltip (tab preview)
======================= */
QToolTip {
    background-color: #1f1f1f;
    color: #e8eaed;
    border: 1px solid #333;
    padding: 6px;
    border-radius: 6px;
}

/* =======================
   Web View
======================= */
QWebEngineView {
    background-color: #0f0f0f;
}
"""
