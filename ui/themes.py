light_theme = """
QMainWindow {
    background-color: #ffffff;
}

QToolBar {
    background-color: #f2f2f2;
    border: none;
}

QLineEdit {
    background-color: #ffffff;
    color: #202124;
    border-radius: 8px;
    border: 1px solid #ccc;
    padding: 6px 10px;
}

QLineEdit::placeholder {
    color: #6b6b6b;
}

QLineEdit#search_bar {
    background-color: #ffffff;
    color: #202124;
    border-radius: 20px;
    border: 1px solid #ccc;
    padding: 6px 12px;
}

QLineEdit::placeholder#search_bar {
    color: #6b6b6b;
}

QPushButton {
    background-color: #f2f2f2;
    color: #202124;
    border-radius: 5px;
    padding: 5px 10px;
}
QPushButton:hover {
    background-color: #e0e0e0;
}

QTabBar::tab {
    background: #f1f3f4;
    color: #5f6368;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 500;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
}

QTabBar::tab:selected {
    background: #ffffff;
    color: #202124;
}

QTabBar::tab:hover {
    background: #e8eaed;
}

QTabBar::close-button {
    image: url(assets/icons/close_light.svg);
    subcontrol-position: right;
    subcontrol-origin: padding;
    width: 14px;
    height: 14px;
    margin-right: 4px;
}
QTabBar::close-button:hover {
    background-color: rgba(232,17,35,0.18);
    border-radius: 7px;
}
"""

dark_theme = """
QMainWindow {
    background-color: #121212;
}

QToolBar {
    background-color: #1f1f1f;
    border: none;
}

QLineEdit {
    background-color: #2c2c2c;
    color: #ffffff;
    border-radius: 8px;
    border: 1px solid #555;
    padding: 6px 10px;
}

QLineEdit::placeholder {
    color: #9a9a9a;
}

QLineEdit#search_bar {
    background-color: #2c2c2c;
    color: #ffffff;
    border-radius: 18px;
    border: 1px solid #555;
    padding: 6px 12px;
}

QLineEdit::placeholder#search_bar {
    color: #9a9a9a;
}

QPushButton {
    background-color: #2c2c2c;
    color: #ffffff;
    border-radius: 5px;
    padding: 5px 10px;
}
QPushButton:hover {
    background-color: #3a3a3a;
}

QTabBar::tab {
    background: #2a2a2a;
    color: #9ea0a6;
    padding: 10px 18px;
    font-size: 13px;
    font-weight: 500;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    margin-right: 4px;
}

QTabBar::tab:selected {
    background: #1f1f1f;
    color: #ffffff;
}

QTabBar::tab:hover {
    background: #353535;
}

QTabBar::close-button {
    image: url(assets/icons/close_dark.svg);
    subcontrol-position: right;
    subcontrol-origin: padding;
    width: 14px;
    height: 14;
    margin-right: 4px;
}
QTabBar::close-button:hover {
    background-color: rgba(232,17,35,0.18);
    border-radius: 7px;
}
"""
