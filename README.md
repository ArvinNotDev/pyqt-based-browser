<div align="center">

# 🛡️ Freebuff Desktop

**A privacy-focused desktop browser with built-in Tor proxy support**

A modern, PySide6-powered web browser designed for users who value their privacy. Routes all traffic through Tor with one click, while providing a familiar tabbed browsing experience.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![PySide6](https://img.shields.io/badge/PySide6-6.10-41CD52?style=for-the-badge&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython-6/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](#license)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=for-the-badge)](#installation)

<br>

![Freebuff Screenshot](assets/icons/home.png)

</div>

---

## ✨ Features

### 🔒 Privacy & Security
- **One-Click Tor Connection** — Route all browser traffic through the Tor network instantly
- **Built-in HTTP Proxy** — Local proxy server handles CONNECT and HTTP requests with Tor routing
- **Host Blocking** — Block specific domains or use wildcard patterns (`*.example.com`)
- **Host Exclusion** — Exclude specific sites from Tor routing for faster access
- **Identity Changer** — Switch Tor circuits with a single click or automatically on a timer

### 🌐 Browsing Experience
- **Tabbed Interface** — Full-featured tab bar with previews, scroll arrows, and smooth animations
- **Multi-Profile Support** — Create separate browsing profiles with independent history, cookies, and settings
- **Profile Customization** — Upload, crop, rotate, and zoom profile images with a visual editor
- **Smart URL Bar** — Search suggestions from browsing history as you type
- **Quick Navigation** — Back, forward, reload, and home buttons

### ⚙️ Configuration
- **Custom Ports** — Configure proxy, SOCKS, control, and DNS ports manually
- **Tor Bridge Support** — Use obfs4, webtunnel, meek, snowflake, scramblesuit, or fte bridges
- **Tor Bundle Updater** — Download and manage Tor bundles directly from the built-in updater
- **Dark & Light Themes** — Toggle between themes with a consistent, modern UI
- **Persistent Settings** — Per-profile settings for homepage, search engine, history, and cookies

### 📊 Monitoring
- **Connection Status** — Visual indicator showing connected/disconnected/connecting state
- **Real-time Data Usage** — Track bandwidth consumed through the proxy
- **Tor Bootstrap Progress** — Watch the Tor connection progress in real-time
- **IP Lookup** — Check your public IP address through the Tor network
- **Activity Logs** — View detailed logs of proxy and Tor operations

---

## 📁 Project Structure

```
.
├── main.py                  # Application entry point
├── requirements.txt         # Python dependencies
├── assets/
│   └── icons/               # UI icons (back, forward, home, reload, etc.)
├── managers/
│   ├── history_manager.py   # Browsing history storage and retrieval
│   └── profile_manager.py   # Machine ID and profile management
├── proxy/
│   ├── config.py            # Application configuration and settings
│   ├── proxy.py             # HTTP proxy server with Tor routing
│   ├── set_proxy.py         # OS-level proxy management
│   ├── tor.py               # Tor process runner and controller
│   ├── updater.py           # Tor bundle download and verification
│   ├── utils.py             # Resource path and extraction utilities
│   ├── whatismyip.py        # Public IP address lookup
│   ├── bundles/             # Downloaded Tor bundles
│   └── ui_/                 # Proxy panel UI components
│       ├── window/          # Proxy, settings, block, exclude, updater windows
│       ├── btn/             # Custom pulse button widget
│       ├── worker/          # Background worker threads
│       └── emojis/          # Cross-platform emoji/icon mappings
└── ui/
    ├── browser_window.py    # Main browser window with tab management
    ├── navigation_bar.py    # Navigation toolbar with URL bar
    ├── history_window.py    # Browsing history viewer
    ├── profile_dialog.py    # Profile image editor
    ├── settings.py          # Browser settings dataclass
    ├── settings_window.py   # Settings dialog
    └── themes.py            # Light and dark theme stylesheets
```

---

## 🚀 Installation

### Prerequisites
- Python 3.10 or higher
- pip (Python package manager)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/ArvinNotDev/pyqt-based-browser.git
   cd pyqt-based-browser
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate        # Linux/macOS
   venv\Scripts\activate           # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Install additional dependencies** (for Tor proxy features)
   ```bash
   pip install pysocks beautifulsoup4 requests stem
   ```

5. **Run the application**
   ```bash
   python main.py
   ```

> **Note:** The first time you connect, the application will download a Tor bundle compatible with your system. You can manage Tor bundles through the built-in Updater panel.

---

## 🖥️ Usage

### Connecting to Tor
1. Click the **"Connect"** button in the Proxy panel (docked on the right side)
2. Wait for the bootstrap progress to reach 100%
3. Once connected, all browser traffic is routed through Tor
4. Use **"Change Identity"** to switch Tor circuits at any time

### Managing Profiles
1. Click the **profile icon** in the navigation bar
2. Select **"Add New Profile"** to create a new browsing profile
3. Select **"Customize Profile"** to upload and edit a profile picture
4. Switch between profiles using the profile menu

### Blocking & Excluding Hosts
- **Block Host** — Prevent requests to specific domains entirely
- **Exclude Host** — Bypass Tor routing for specific domains (useful for local services)

### Keyboard Shortcuts
| Shortcut | Action |
|----------|--------|
| `Ctrl+Alt+P` | Toggle window visibility (Windows) |
| `Ctrl+O` | Open image (profile editor) |
| `Ctrl+V` | Paste image (profile editor) |
| `Ctrl+S` | Save (profile editor) |

---

## 🏗️ Architecture

The application follows a modular architecture separating concerns into three main layers:

| Layer | Description |
|-------|-------------|
| **`ui/`** | Browser UI — tabs, navigation, settings, history, profile management |
| **`proxy/`** | Proxy engine — HTTP server, Tor integration, bundle management, config |
| **`managers/`** | Data layer — history persistence, profile/machine identification |

The proxy runs as a local HTTP server (using Python's `ThreadingHTTPServer`) and routes traffic through a Tor SOCKS5 proxy. The browser (PySide6 `QWebEngineView`) connects to the local proxy via Chromium's `--proxy-server` flag, ensuring all requests pass through the privacy layer.

---

## 🙏 Acknowledgements

This project builds upon the work of **[Nima Salamat](https://github.com/nima-salamat)** and his [Tor Proxy](https://github.com/nima-salamat/tor-proxy) project, which provided the foundation for Tor integration and proxy functionality. Check out his repository for the core proxy implementation.

---

## 📋 Dependencies

| Package | Purpose |
|---------|---------|
| [PySide6](https://pypi.org/project/PySide6/) | Qt for Python — GUI framework and WebEngine |
| [PySocks](https://pypi.org/project/PySocks/) | SOCKS proxy client for Tor connections |
| [BeautifulSoup4](https://pypi.org/project/beautifulsoup4/) | HTML parsing for Tor bundle updates |
| [Requests](https://pypi.org/project/requests/) | HTTP client for downloading bundles and IP lookup |
| [stem](https://pypi.org/project/stem/) | Tor controller library for identity changes |

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**Built with ❤️ using Python & Qt**

</div>
