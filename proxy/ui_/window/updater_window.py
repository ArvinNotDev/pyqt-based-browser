
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QPushButton, QMessageBox, QLabel, QHBoxLayout
from PySide6.QtCore import QThreadPool
from proxy.ui_.worker.worker import Worker
from proxy.updater import (
    CancellationToken,
    DownloadCancelledError,
    check_bundle_compatibility,
    delete_bundle,
    download_file,
    get_bundle_links,
    get_own_bundles,
    get_tor_versions,
    get_version_by_bundle,
    list_downloaded_bundles,
)
from proxy.config import CONFIG
from proxy.config import BUNDLE_DIR
from proxy.utils import extract_tar_gz_file, resource_path
import json
import os
import logging

logger = logging.getLogger()

class UpdaterWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_ = parent
        self._closing = False
        self._cancel_event = CancellationToken()
        self.setObjectName("torBundlePage")
        self.setMinimumWidth(0)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 10, 12, 12)
        main_layout.setSpacing(9)

        self.btn_get_versions = QPushButton("Check available bundles")
        self.btn_get_versions.setObjectName("bundlePrimaryAction")
        self.btn_get_versions.clicked.connect(self.get_available_versions)
        main_layout.addWidget(self.btn_get_versions)

        self.updates_list = QListWidget()
        self.updates_list.setObjectName("bundleList")
        self.updates_list.setMinimumHeight(65)
        self.updates_list.itemClicked.connect(self.selected_version)
        main_layout.addWidget(QLabel("Available downloads"))
        main_layout.addWidget(self.updates_list, 1)

        self.lbl_status = QLabel("Select a bundle to see versions and actions.")
        self.lbl_status.setWordWrap(True)
        main_layout.addWidget(self.lbl_status)
        self.thread_pool = QThreadPool(self)
        self.thread_pool.setMaxThreadCount(2)

        main_layout.addWidget(QLabel("Installed bundles"))
        self.btn_refresh_version = QPushButton("Refresh installed bundles")
        self.btn_refresh_version.clicked.connect(self.refresh_version)
        main_layout.addWidget(self.btn_refresh_version)
        self.list_tor_versions = QListWidget()
        self.list_tor_versions.setObjectName("installedBundleList")
        self.list_tor_versions.setMinimumHeight(65)
        main_layout.addWidget(self.list_tor_versions, 1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.btn_set_default_version = QPushButton("Use selected")
        self.btn_set_default_version.clicked.connect(self.set_default_version)
        actions.addWidget(self.btn_set_default_version, 1)
        self.btn_delete_version = QPushButton("Delete")
        self.btn_delete_version.clicked.connect(self.delete_version)
        actions.addWidget(self.btn_delete_version, 1)
        main_layout.addLayout(actions)
        self.refresh_version()

    def prepare_shutdown(self):
        """Cancel network and extraction jobs before Qt destroys the thread pool."""
        if self._closing:
            return
        self._closing = True
        self._cancel_event.set()
        self.thread_pool.clear()
        if not self.thread_pool.waitForDone(2500):
            logger.warning("Tor bundle worker did not finish within the shutdown grace period")

    def refresh_version(self):
        if self._closing:
            return
        self.list_tor_versions.clear()
        for i in get_own_bundles():
            if check_bundle_compatibility(i):
                self.list_tor_versions.addItem(i)
                
    def set_default_version(self):
        if items:=self.list_tor_versions.selectedItems():
            item = items[0]
            reply = QMessageBox.question(self, 
                                        "Download", 
                                        f"Do you want set default tor?\n{item.text()}",
                                        QMessageBox.Yes| QMessageBox.No, 
                                        QMessageBox.No)
            if reply == QMessageBox.No:
                return
            
            CONFIG["tor_path"] = item.text()
            self.refresh_version()            
            

            
    def delete_version(self):
        if items:=self.list_tor_versions.selectedItems():
            item = items[0]
            reply = QMessageBox.question(self, 
                                        "Download", 
                                        f"Do you want to download?\n{item.text()}",
                                        QMessageBox.Yes| QMessageBox.No, 
                                        QMessageBox.No)
            if reply == QMessageBox.No:
                return
        delete_bundle(item.text())
        self.refresh_version()            
        
    def _start_worker(self, function, *args, finished=None, error=None):
        if self._closing or self._cancel_event.is_set():
            return None
        worker = Worker(function, *args, cancel_event=self._cancel_event)
        self.worker = worker
        if finished is not None:
            worker.signals.finished.connect(finished)
        if error is not None:
            worker.signals.error.connect(error)
        self.thread_pool.start(worker)
        return worker

    def _listing_error(self, error):
        if self._closing or self._cancel_event.is_set():
            return
        logger.warning("Tor bundle lookup failed (%s)", error)
        self.lbl_status.setText("Could not retrieve Tor versions. Check the connection and retry.")
        self.btn_get_versions.setEnabled(True)

    def get_available_versions(self):
        if self._closing:
            return
        self.btn_get_versions.setDisabled(True)
        self.lbl_status.setText("Checking the official Tor Project bundle index…")
        self._start_worker(
            get_tor_versions,
            finished=self.set_tor_versions,
            error=self._listing_error,
        )

    def set_tor_versions(self, data):
        if self._closing:
            return
        try:
            versions = json.loads(data.replace("'", '"'))
        except (json.JSONDecodeError, AttributeError, TypeError):
            versions = []
        if not isinstance(versions, list):
            versions = []
        self._start_worker(
            self.get_download_links,
            versions,
            finished=self.set_download_links,
            error=self._listing_error,
        )

    def get_download_links(self, data, cancel_event=None):
        links = []
        for version in data:
            if cancel_event is not None and cancel_event.is_set():
                raise DownloadCancelledError("Tor bundle lookup was cancelled.")
            links.extend(get_bundle_links(version, cancel_event=cancel_event))
        return links

    def set_download_links(self, data):
        if self._closing:
            return
        try:
            bundles = json.loads(data.replace("'", '"'))
        except (json.JSONDecodeError, AttributeError, TypeError):
            bundles = []
        if not isinstance(bundles, list):
            bundles = []

        downloaded = {os.path.basename(path) for path in list_downloaded_bundles()}
        self.updates_list.clear()
        for bundle in bundles:
            if bundle not in downloaded:
                self.updates_list.addItem(bundle)
        self.lbl_status.setText(
            f"{self.updates_list.count()} compatible bundle(s) available."
            if self.updates_list.count()
            else "No compatible bundles were found. Check your connection and retry."
        )
        self.btn_get_versions.setEnabled(True)

    def selected_version(self, item):
        if self._closing:
            return
        reply = QMessageBox.question(self, 
                                     "Download", 
                                     f"Do you want to download?\n{item.text()}",
                                     QMessageBox.Yes| QMessageBox.No, 
                                     QMessageBox.No)
        if reply == QMessageBox.No:
            return
        self.updates_list.setEnabled(False)
        bundle = item.text()
        version = get_version_by_bundle(bundle)
        self.lbl_status.setText(f"Downloading and verifying {bundle}")
        self._start_worker(
            self.download_bundle,
            bundle,
            version,
            finished=self._download_complete,
            error=self._download_error,
        )
    
    def download_bundle(self, bundle, version, cancel_event=None):
        if cancel_event is not None and cancel_event.is_set():
            raise DownloadCancelledError("Tor bundle download was cancelled.")
        logger.info("Downloading Tor bundle %s", bundle)
        archive = download_file(bundle, version, cancel_event=cancel_event)
        base_path = resource_path(os.path.join(
            BUNDLE_DIR, os.path.basename(bundle).replace(".tar.gz", "")
        ))
        if not os.path.isdir(base_path):
            extract_tar_gz_file(archive, base_path, cancel_event=cancel_event)
        return bundle

    def _download_complete(self, bundle):
        if self._closing:
            return
        self.lbl_status.setText(f"Downloaded and verified {bundle}")
        self.refresh_version()
        self.updates_list.setEnabled(True)

    def _download_error(self, error):
        if self._closing or self._cancel_event.is_set():
            return
        logger.warning("Tor bundle download or extraction failed (%s)", error)
        self.lbl_status.setText("Download or extraction failed; the archive was retained.")
        self.updates_list.setEnabled(True)
        

