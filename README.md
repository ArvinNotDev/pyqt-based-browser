<div align="center">

# Privacy-Focused Desktop Browser

**A privacy-oriented desktop web browser with integrated Tor proxy support.**

A modern desktop browser built with **Python, PySide6, and Qt WebEngine**, providing tabbed browsing, configurable proxy routing, Tor integration, browser profiles, host filtering, and network monitoring.

<br>

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square\&logo=python\&logoColor=white)](https://www.python.org/)
[![PySide6](https://img.shields.io/badge/PySide6-6.10-41CD52?style=flat-square\&logo=qt\&logoColor=white)](https://doc.qt.io/qtforpython/)
[![License](https://img.shields.io/badge/License-MIT-2f80ed?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)](#installation)

<br>

<img src="assets/icons/home.png" alt="Browser Screenshot" width="900">

</div>

---

## Overview

This project is a desktop web browser designed with privacy and network configurability in mind.

It uses **Qt WebEngine** for browsing and provides an integrated local HTTP proxy capable of routing browser traffic through a local **Tor SOCKS5 proxy**.

The application also provides browser profiles, host blocking and exclusion rules, Tor bridge configuration, identity switching, network monitoring, and persistent settings.

---

## Features

### Privacy & Networking

* **Tor Routing** — Route browser traffic through the Tor network.
* **Local HTTP Proxy** — Handle browser HTTP and CONNECT requests locally before forwarding them through Tor.
* **Host Blocking** — Block specific domains or wildcard patterns such as `*.example.com`.
* **Host Exclusion** — Bypass Tor routing for selected domains.
* **Identity Switching** — Request a new Tor circuit directly from the browser.
* **Configurable Proxy Ports** — Configure HTTP, SOCKS, control, and DNS ports.

### Browser

* **Tabbed Browsing** — Multi-tab interface with tab previews and navigation controls.
* **Browser Profiles** — Maintain separate histories, cookies, and settings.
* **Profile Customization** — Upload, crop, rotate, zoom, and save profile images.
* **URL Bar Suggestions** — Search suggestions using browser history.
* **Navigation Controls** — Back, forward, reload, and home.
* **Persistent Browser Settings** — Store browser preferences between sessions.

### Tor Integration

* **Tor Process Management**
* **Tor Bootstrap Monitoring**
* **Tor Identity Changes**
* **Tor Bundle Management**
* **Tor Bridge Configuration**
* **SOCKS5 Integration**

Supported bridge transports include:

```text
obfs4
webtunnel
meek
snowflake
scramblesuit
fte
```

### Monitoring

* **Connection Status**
* **Tor Bootstrap Progress**
* **Real-time Bandwidth Usage**
* **Public IP Lookup**
* **Proxy Activity Logs**

### User Interface

* **Dark and Light Themes**
* **Configurable Settings**
* **Profile Management**
* **Dockable Proxy Panel**
* **Animated Browser Controls**

---

## Architecture

The application is divided into three main components:

| Component   | Responsibility                                                                     |
| ----------- | ---------------------------------------------------------------------------------- |
| `ui/`       | Browser interface, tabs, navigation, profiles, settings, and history               |
| `proxy/`    | HTTP proxy, Tor integration, routing, bundle management, and network configuration |
| `managers/` | History persistence and profile management                                         |

### Network Architecture

```text
┌──────────────────────────────┐
│        Qt WebEngine          │
│         Web Browser          │
└──────────────┬───────────────┘
               │
               │ HTTP / CONNECT
               ▼
┌──────────────────────────────┐
│       Local HTTP Proxy       │
│    ThreadingHTTPServer       │
└──────────────┬───────────────┘
               │
               │ SOCKS5
               ▼
┌──────────────────────────────┐
│          Tor Client          │
│       Local SOCKS Proxy      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│          Tor Network         │
└──────────────────────────────┘
```

The browser is configured to use the local HTTP proxy through Chromium's proxy configuration. The local proxy then forwards supported requests through the Tor SOCKS5 interface.

---

## Project Structure

```text
.
├── main.py
├── requirements.txt
│
├── assets/
│   └── icons/
│
├── managers/
│   ├── history_manager.py
│   └── profile_manager.py
│
├── proxy/
│   ├── config.py
│   ├── proxy.py
│   ├── set_proxy.py
│   ├── tor.py
│   ├── updater.py
│   ├── utils.py
│   ├── whatismyip.py
│   │
│   ├── bundles/
│   │
│   └── ui_/
│       ├── window/
│       ├── btn/
│       ├── worker/
│       └── emojis/
│
└── ui/
    ├── browser_window.py
    ├── navigation_bar.py
    ├── history_window.py
    ├── profile_dialog.py
    ├── settings.py
    ├── settings_window.py
    └── themes.py
```

---

## Installation

### Requirements

* Python **3.10 or newer**
* `pip`
* Windows, Linux, or macOS

### Clone the repository

```bash
git clone https://github.com/ArvinNotDev/pyqt-based-browser.git
cd pyqt-based-browser
```

### Create a virtual environment

#### Windows

```powershell
python -m venv venv
venv\Scripts\activate
```

#### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

### Install dependencies

```bash
pip install -r requirements.txt
```

Additional Tor-related dependencies:

```bash
pip install pysocks beautifulsoup4 requests stem
```

### Run

```bash
python main.py
```

The application can download a compatible Tor bundle when a Tor connection is initiated for the first time.

---

## Usage

### Connect to Tor

1. Open the proxy panel.
2. Select **Connect**.
3. Wait for the Tor bootstrap process to complete.
4. Once connected, browser traffic is routed through the configured proxy.
5. Use **Change Identity** to request a new Tor circuit.

### Browser Profiles

Profiles provide independent browser environments for different browsing contexts.

To create a profile:

1. Open the profile menu.
2. Select **Add New Profile**.
3. Configure the profile.
4. Optionally customize its profile image.

Each profile can maintain its own browsing history, cookies, and browser settings.

### Host Blocking

Domains can be blocked completely using host rules.

Examples:

```text
example.com
*.example.com
ads.example.org
```

### Host Exclusion

Specific domains can be excluded from Tor routing when direct access is required.

---

## Keyboard Shortcuts

| Shortcut         | Action                              |
| ---------------- | ----------------------------------- |
| `Ctrl + Alt + P` | Toggle window visibility on Windows |
| `Ctrl + O`       | Open image in profile editor        |
| `Ctrl + V`       | Paste image in profile editor       |
| `Ctrl + S`       | Save profile image                  |

---

## Configuration

The application supports persistent configuration for:

* Homepage
* Search engine
* Browsing history
* Cookies
* HTTP proxy port
* SOCKS port
* Tor control port
* DNS configuration
* Tor bridges
* Host blocking rules
* Host exclusion rules
* Theme
* Profile-specific settings

---

## Dependencies

| Package                                                    | Purpose                                 |
| ---------------------------------------------------------- | --------------------------------------- |
| [PySide6](https://pypi.org/project/PySide6/)               | Qt bindings and GUI framework           |
| [PySocks](https://pypi.org/project/PySocks/)               | SOCKS proxy support                     |
| [BeautifulSoup4](https://pypi.org/project/beautifulsoup4/) | HTML parsing                            |
| [Requests](https://pypi.org/project/requests/)             | HTTP requests, downloads, and IP lookup |
| [Stem](https://pypi.org/project/stem/)                     | Tor controller interface                |

---

## Acknowledgements

The Tor proxy functionality builds upon work from **[Nima Salamat](https://github.com/nima-salamat)** and the [`tor-proxy`](https://github.com/nima-salamat/tor-proxy) project.

---

## License

This project is licensed under the **MIT License**.

See [`LICENSE`](LICENSE) for the full license text.

---

<div align="center">

**Built with Python · PySide6 · Qt WebEngine · Tor**

</div>
