# profile_editor_with_clipboard.py
from PySide6.QtWidgets import (
    QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QSlider, QSizePolicy, QMessageBox, QSpinBox,
    QToolButton, QCheckBox
)
from PySide6.QtGui import (
    QPixmap, QPainter, QPainterPath, QTransform, QImage, QColor, QIcon,
    QKeySequence, QShortcut
)
from PySide6.QtCore import Qt, QPoint, QRect, Signal
import os
import sys

class ProfilePreview(QWidget):
    zoom_changed = Signal(float)
    rotation_changed = Signal(float)

    def __init__(self, diameter=300, parent=None):
        super().__init__(parent)
        self.diameter = diameter
        self.setFixedSize(diameter, diameter)
        self._pix = QPixmap()
        self._zoom = 1.0
        self._min_zoom = 0.2
        self._max_zoom = 8.0
        self._offset = QPoint(0, 0)
        self._dragging = False
        self._last_pos = QPoint()
        self._rotation = 0.0
        self._flip_h = False
        self._flip_v = False
        self.setToolTip("Drag to pan, wheel to zoom, double-click to Fit")

    def set_pixmap(self, pix: QPixmap):
        if pix.isNull():
            self._pix = QPixmap()
            self._zoom = 1.0
            self._offset = QPoint(0, 0)
            self.update()
            self.zoom_changed.emit(self._zoom)
            return
        self._pix = pix
        self.cover_out()
        self._offset = QPoint(0, 0)
        self._rotation = 0.0
        self._flip_h = False
        self._flip_v = False
        self.update()
        self.zoom_changed.emit(self._zoom)
        self.rotation_changed.emit(self._rotation)

    def set_zoom(self, z: float):
        z = max(self._min_zoom, min(self._max_zoom, z))
        if abs(z - self._zoom) < 1e-6:
            return
        self._zoom = z
        self._constrain_offset()
        self.update()
        self.zoom_changed.emit(self._zoom)

    def zoom(self) -> float:
        return self._zoom

    def set_rotation(self, angle: float):
        angle = angle % 360.0
        if abs(angle - self._rotation) < 1e-6:
            return
        self._rotation = angle
        self._constrain_offset()
        self.update()
        self.rotation_changed.emit(self._rotation)

    def rotation(self) -> float:
        return self._rotation

    def flip_horizontal(self):
        self._flip_h = not self._flip_h
        self.update()

    def flip_vertical(self):
        self._flip_v = not self._flip_v
        self.update()

    def fit_in(self):
        if self._pix.isNull():
            return
        pw, ph = self._pix.width(), self._pix.height()
        diameter = self.width()
        scale = min(diameter / max(1, pw), diameter / max(1, ph))
        self.set_zoom(max(self._min_zoom, min(self._max_zoom, scale)))
        self._offset = QPoint(0, 0)
        self.update()

    def cover_out(self):
        if self._pix.isNull():
            return
        pw, ph = self._pix.width(), self._pix.height()
        diameter = self.width()
        scale = max(diameter / max(1, pw), diameter / max(1, ph))
        self.set_zoom(max(self._min_zoom, min(self._max_zoom, scale)))
        self._offset = QPoint(0, 0)
        self.update()

    def _constrain_offset(self):
        if self._pix.isNull():
            self._offset = QPoint(0, 0)
            return
        sw = max(1, int(self._pix.width() * self._zoom))
        sh = max(1, int(self._pix.height() * self._zoom))
        scaled = self._pix.scaled(sw, sh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        transform = QTransform().rotate(self._rotation)
        if self._flip_h or self._flip_v:
            sx = -1 if self._flip_h else 1
            sy = -1 if self._flip_v else 1
            transform.scale(sx, sy)
        transformed = scaled.transformed(transform, Qt.SmoothTransformation)
        tw, th = transformed.width(), transformed.height()
        w, h = self.width(), self.height()
        max_x = max(0, int(tw / 2 - w // 2))
        max_y = max(0, int(th / 2 - h // 2))
        x = int(self._offset.x())
        y = int(self._offset.y())
        x = max(-max_x, min(max_x, x))
        y = max(-max_y, min(max_y, y))
        self._offset = QPoint(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHints(QPainter.SmoothPixmapTransform | QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30))
        path = QPainterPath()
        path.addEllipse(self.rect())
        painter.setClipPath(path)
        if self._pix.isNull():
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.darkGray)
            painter.drawEllipse(self.rect())
            return
        sw = max(1, int(self._pix.width() * self._zoom))
        sh = max(1, int(self._pix.height() * self._zoom))
        scaled = self._pix.scaled(sw, sh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        transform = QTransform().rotate(self._rotation)
        if self._flip_h or self._flip_v:
            sx = -1 if self._flip_h else 1
            sy = -1 if self._flip_v else 1
            transform.scale(sx, sy)
        transformed = scaled.transformed(transform, Qt.SmoothTransformation)
        tw, th = transformed.width(), transformed.height()
        w, h = self.width(), self.height()
        center_x = tw // 2 + self._offset.x()
        center_y = th // 2 + self._offset.y()
        src_left = center_x - w // 2
        src_top = center_y - h // 2
        src_left = max(0, min(transformed.width() - w, src_left))
        src_top = max(0, min(transformed.height() - h, src_top))
        src_rect = QRect(src_left, src_top, w, h)
        painter.drawPixmap(self.rect(), transformed, src_rect)
        painter.setClipping(False)
        painter.setPen(QColor(200, 200, 200))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(self.rect().adjusted(1, 1, -1, -1))

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        step = 0.08
        if delta > 0:
            self.set_zoom(self._zoom * (1 + step))
        else:
            self.set_zoom(self._zoom * (1 - step))
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._last_pos = event.pos()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._dragging and not self._pix.isNull():
            delta = event.pos() - self._last_pos
            self._offset += delta
            self._last_pos = event.pos()
            self._constrain_offset()
            self.update()
            event.accept()
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = False
            event.accept()
        else:
            event.ignore()

    def mouseDoubleClickEvent(self, event):
        self.fit_in()

    def get_cropped_circle(self, output_size: int = 512) -> QPixmap:
        if self._pix.isNull():
            return QPixmap()
        sw = max(1, int(self._pix.width() * self._zoom))
        sh = max(1, int(self._pix.height() * self._zoom))
        scaled = self._pix.scaled(sw, sh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        transform = QTransform().rotate(self._rotation)
        if self._flip_h or self._flip_v:
            sx = -1 if self._flip_h else 1
            sy = -1 if self._flip_v else 1
            transform.scale(sx, sy)
        transformed = scaled.transformed(transform, Qt.SmoothTransformation)
        tw, th = transformed.width(), transformed.height()
        w, h = self.width(), self.height()
        center_x = tw // 2 + self._offset.x()
        center_y = th // 2 + self._offset.y()
        src_left = center_x - w // 2
        src_top = center_y - h // 2
        src_left = max(0, min(transformed.width() - w, src_left))
        src_top = max(0, min(transformed.height() - h, src_top))
        src_rect = QRect(src_left, src_top, w, h)
        cropped = transformed.copy(src_rect)
        final = cropped.scaled(output_size, output_size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        image = QImage(final.size(), QImage.Format_ARGB32)
        image.fill(0)
        p = QPainter(image)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(0, 0, final)
        p.end()
        mask = QImage(image.width(), image.height(), QImage.Format_ARGB32)
        mask.fill(0)
        pm = QPainter(mask)
        pm.setRenderHint(QPainter.Antialiasing)
        pm.setBrush(Qt.white)
        pm.setPen(Qt.NoPen)
        pm.drawEllipse(0, 0, mask.width(), mask.height())
        pm.end()
        image.setAlphaChannel(mask)
        return QPixmap.fromImage(image)


class CustomizeProfile(QDialog):
    profile_saved = Signal(str)

    def __init__(self, username: str, parent=None):
        super().__init__(parent)
        self.username = username
        self.setWindowTitle("Profile Editor — Clipboard & Copy")
        self.setMinimumSize(760, 300)
        self._ensure_profile_dir()

        self.preview = ProfilePreview(diameter=320, parent=self)
        self.preview.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        top = QHBoxLayout()
        left_col = QVBoxLayout()
        left_col.addWidget(self.preview)
        left_col.addStretch()
        top.addLayout(left_col)

        right_col = QVBoxLayout()

        # show only filename by default
        self.filename_label = QLabel("No image loaded")
        self.filename_label.setWordWrap(True)
        right_col.addWidget(self.filename_label)

        # show full path checkbox (off by default)
        self.show_full_path_cb = QCheckBox("Show full path")
        self.show_full_path_cb.setChecked(False)
        self.show_full_path_cb.toggled.connect(self._update_filename_label)
        right_col.addWidget(self.show_full_path_cb)

        # Zoom
        zrow = QHBoxLayout()
        zrow.addWidget(QLabel("Zoom"))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(int(self.preview._min_zoom * 100), int(self.preview._max_zoom * 100))
        self.zoom_slider.setValue(int(self.preview.zoom() * 100))
        self.zoom_slider.valueChanged.connect(lambda v: self.preview.set_zoom(v / 100.0))
        zrow.addWidget(self.zoom_slider)
        self.zoom_value_lbl = QLabel(f"{int(self.preview.zoom() * 100)}%")
        zrow.addWidget(self.zoom_value_lbl)
        right_col.addLayout(zrow)

        # Rotate
        rrow = QHBoxLayout()
        rrow.addWidget(QLabel("Rotate"))
        self.rotate_slider = QSlider(Qt.Horizontal)
        self.rotate_slider.setRange(0, 359)
        self.rotate_slider.setValue(int(self.preview.rotation()))
        self.rotate_slider.valueChanged.connect(lambda v: self.preview.set_rotation(float(v)))
        rrow.addWidget(self.rotate_slider)
        self.rotate_val = QLabel(f"{int(self.preview.rotation())}°")
        rrow.addWidget(self.rotate_val)
        right_col.addLayout(rrow)

        # flips
        flip_row = QHBoxLayout()
        self.btn_flip_h = QPushButton("Flip H")
        self.btn_flip_h.setToolTip("Flip horizontally")
        self.btn_flip_h.clicked.connect(self.preview.flip_horizontal)
        flip_row.addWidget(self.btn_flip_h)
        self.btn_flip_v = QPushButton("Flip V")
        self.btn_flip_v.setToolTip("Flip vertically")
        self.btn_flip_v.clicked.connect(self.preview.flip_vertical)
        flip_row.addWidget(self.btn_flip_v)
        right_col.addLayout(flip_row)

        # util buttons
        util_row = QHBoxLayout()
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.setToolTip("Show whole image inside circle")
        self.btn_fit.clicked.connect(self.preview.fit_in)
        util_row.addWidget(self.btn_fit)
        self.btn_cover = QPushButton("Cover")
        self.btn_cover.setToolTip("Fill circle completely")
        self.btn_cover.clicked.connect(self.preview.cover_out)
        util_row.addWidget(self.btn_cover)
        self.btn_reset = QPushButton("Reset")
        self.btn_reset.clicked.connect(self._reset_view)
        util_row.addWidget(self.btn_reset)
        right_col.addLayout(util_row)

        # file actions: Open, Paste, Copy, Save, Cancel
        file_row = QHBoxLayout()
        self.btn_open = QPushButton("Open...")
        self.btn_open.clicked.connect(self.open_image)
        file_row.addWidget(self.btn_open)

        self.btn_paste = QPushButton("Paste (Ctrl+V)")
        self.btn_paste.setToolTip("Paste image from clipboard (image or local filepath)")
        self.btn_paste.clicked.connect(self.paste_image)
        file_row.addWidget(self.btn_paste)

        self.btn_copy = QPushButton("Copy Image (Ctrl+C)")
        self.btn_copy.setToolTip("Copy the cropped circular image to clipboard")
        self.btn_copy.clicked.connect(self.copy_cropped_to_clipboard)
        file_row.addWidget(self.btn_copy)

        self.btn_save = QPushButton("Save")
        self.btn_save.clicked.connect(self.save_image)
        file_row.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        file_row.addWidget(self.btn_cancel)
        right_col.addLayout(file_row)

        tips = QLabel(
            "<b>Tips:</b> Drag to pan · Wheel to zoom · Double-click preview to Fit · "
            "Shortcuts: Ctrl+O (open), Ctrl+V (paste), Ctrl+C (copy image), Ctrl+S (save), Ctrl+R (reset)"
        )
        tips.setWordWrap(True)
        right_col.addWidget(tips)
        right_col.addStretch()

        top.addLayout(right_col)
        self.setLayout(QVBoxLayout())
        self.layout().addLayout(top)

        # shortcuts
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_image)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self.save_image)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._reset_view)
        QShortcut(QKeySequence("Ctrl+V"), self, activated=self.paste_image)
        QShortcut(QKeySequence("Ctrl+C"), self, activated=self.copy_cropped_to_clipboard)

        # sync signals
        self.preview.zoom_changed.connect(self._on_zoom_changed)
        self.preview.rotation_changed.connect(self._on_rotation_changed)
        self.zoom_slider.valueChanged.connect(lambda v: self.zoom_value_lbl.setText(f"{int(v)}%"))
        self.rotate_slider.valueChanged.connect(lambda v: self.rotate_val.setText(f"{int(v)}°"))

        # load existing if present
        existing = self._profile_path()
        if os.path.exists(existing):
            pm = QPixmap(existing)
            if not pm.isNull():
                self.preview.set_pixmap(pm)
                self._set_loaded_path(existing)

    # dir helpers
    def _ensure_profile_dir(self):
        os.makedirs(os.path.join("profile_data", self.username, "profile"), exist_ok=True)

    def _profile_dir(self):
        return os.path.join("profile_data", self.username, "profile")

    def _profile_path(self):
        return os.path.join(self._profile_dir(), "image.png")

    # UI helpers
    def _on_zoom_changed(self, z: float):
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(int(z * 100))
        self.zoom_slider.blockSignals(False)
        self.zoom_value_lbl.setText(f"{int(z * 100)}%")

    def _on_rotation_changed(self, angle: float):
        self.rotate_slider.blockSignals(True)
        self.rotate_slider.setValue(int(angle) % 360)
        self.rotate_slider.blockSignals(False)
        self.rotate_val.setText(f"{int(angle)}°")

    def _set_loaded_path(self, path: str):
        self._last_loaded_path = path
        self._update_filename_label()

    def _update_filename_label(self):
        if getattr(self, "_last_loaded_path", None):
            if self.show_full_path_cb.isChecked():
                self.filename_label.setText(f"Loaded: {self._last_loaded_path}")
            else:
                self.filename_label.setText(f"Loaded: {os.path.basename(self._last_loaded_path)}")
        else:
            self.filename_label.setText("No image loaded")

    # file actions
    def open_image(self):
        file, _ = QFileDialog.getOpenFileName(self, "Open Image", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not file:
            return
        pix = QPixmap(file)
        if pix.isNull():
            QMessageBox.warning(self, "Invalid image", "Selected file is not a valid image.")
            return
        self.preview.set_pixmap(pix)
        self._set_loaded_path(file)
        QMessageBox.information(self, "Loaded", f"Image loaded: {os.path.basename(file)}")

    def paste_image(self):
        clipboard = QApplication.clipboard()
        # first try image
        img = clipboard.image()
        if not img.isNull():
            pm = QPixmap.fromImage(img)
            self.preview.set_pixmap(pm)
            self._last_loaded_path = None
            self._update_filename_label()
            QMessageBox.information(self, "Pasted", "Image pasted from clipboard.")
            return
        # then try URLs (local file)
        md = clipboard.mimeData()
        if md and md.hasUrls():
            urls = md.urls()
            if urls:
                local = urls[0].toLocalFile()
                if local and os.path.exists(local):
                    pm = QPixmap(local)
                    if not pm.isNull():
                        self.preview.set_pixmap(pm)
                        self._set_loaded_path(local)
                        QMessageBox.information(self, "Pasted", f"Image loaded from clipboard URL: {os.path.basename(local)}")
                        return
        # then try raw text path
        text = clipboard.text().strip()
        if text and os.path.exists(text):
            pm = QPixmap(text)
            if not pm.isNull():
                self.preview.set_pixmap(pm)
                self._set_loaded_path(text)
                QMessageBox.information(self, "Pasted", f"Image loaded from path text: {os.path.basename(text)}")
                return
        QMessageBox.warning(self, "Paste failed", "Clipboard does not contain an image or a valid local file path.")

    def copy_cropped_to_clipboard(self):
        pix = self.preview.get_cropped_circle(output_size=1024)
        if pix.isNull():
            QMessageBox.warning(self, "Nothing to copy", "No image to copy.")
            return
        clipboard = QApplication.clipboard()
        clipboard.setPixmap(pix)
        QMessageBox.information(self, "Copied", "Cropped circular image copied to clipboard (Ctrl+V to paste).")

    def _reset_view(self):
        self.preview._offset = QPoint(0, 0)
        self.preview.set_rotation(0.0)
        self.preview.cover_out()
        self.info_label_if_needed()

    def info_label_if_needed(self):
        # keep filename_label updated
        self._update_filename_label()

    def save_image(self):
        final = self.preview.get_cropped_circle(output_size=1024)
        if final.isNull():
            QMessageBox.warning(self, "No Image", "No image to save.")
            return
        path = self._profile_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ok = final.save(path, "PNG")
        if not ok:
            QMessageBox.warning(self, "Save failed", "Could not save image.")
            return
        self._set_loaded_path(path)
        QMessageBox.information(self, "Saved", f"Saved profile image to:\n{path}")
        self.profile_saved.emit(path)
        self.accept()

