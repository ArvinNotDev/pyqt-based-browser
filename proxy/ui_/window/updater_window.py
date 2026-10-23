
from PySide6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QPushButton, QMessageBox, QLabel, QHBoxLayout
from PySide6.QtCore import QThreadPool
from proxy.ui_.worker.worker import Worker
from proxy.updater import get_tor_versions, get_bundle_links, get_version_by_bundle, download_file, list_downloaded_bundles, delete_bundle
from proxy.updater import get_own_bundles, check_bundle_compatibility, delete_bundle
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

    def refresh_version(self):
        self.list_tor_versions.clear()
        print(get_own_bundles())
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
        
    def get_available_versions(self):
        self.btn_get_versions.setDisabled(True)
        self.worker = Worker(get_tor_versions)
        self.worker.signals.finished.connect(self.set_tor_versions)
        self.thread_pool.start(self.worker)
        
    def set_tor_versions(self, data):
        
        try:
            data = json.loads(data.replace("'", "\""))
        except json.JSONDecodeError:
            data = []
        
        
        self.worker = Worker(self.get_download_links, data)
        self.worker.signals.finished.connect(self.set_download_links)
        self.thread_pool.start(self.worker)
        
        
    
    def get_download_links(self, data):        
        lst = []
        
        for i in data:
            lst.extend(get_bundle_links(i))
        return lst
    
    def set_download_links(self, data):
        
        try:
            data = json.loads(data.replace("'", "\""))
        except json.JSONDecodeError:
            data = [] 
        
        self.updates_list.clear()
        
        downloaded_bundles = list_downloaded_bundles()
        downloaded_bundles = list(map(lambda x: os.path.basename(x), downloaded_bundles))
        print(downloaded_bundles)
        for i in data:
            if i not in downloaded_bundles:
                self.updates_list.addItem(i)
        
        self.btn_get_versions.setDisabled(False)
        

    
    def selected_version(self, item):
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
        self.worker = Worker(self.download_bundle, bundle , version)
        self.worker.signals.finished.connect(self._download_complete)
        self.worker.signals.error.connect(self._download_error)
        self.thread_pool.start(self.worker)
    
    def download_bundle(self, bundle, version):
        logger.info("Downloading Tor bundle %s", bundle)
        archive = download_file(bundle, version)
        base_path = resource_path(os.path.join(BUNDLE_DIR, os.path.basename(bundle).replace(".tar.gz", "")))
        if not os.path.isdir(base_path):
            extract_tar_gz_file(archive, base_path)
        return bundle

    def _download_complete(self, bundle):
        self.lbl_status.setText(f"Downloaded and verified {bundle}")
        self.refresh_version()
        self.updates_list.setEnabled(True)

    def _download_error(self, error):
        logger.warning("Tor bundle download or extraction failed (%s)", error)
        self.lbl_status.setText("Download or extraction failed; the archive was retained.")
        self.updates_list.setEnabled(True)
        

