from typing import List, Optional

import cv2
import numpy as np

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint, QPointF, QRect
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QPen, QBrush, QFont,
    QLinearGradient, QPolygonF, QPainterPath
)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QCheckBox, QSlider, QDialog
)

from config import AppConfig


class QSignalBridge(QObject):
    """엔진 백그라운드 스레드와 Qt UI 메인 스레드 간 비동기 시그널 브릿지"""
    hp_updated = Signal(float, float, bool, str)
    haptic_status = Signal(bool, str)
    camera_status = Signal(bool, str)
    log_message = Signal(str, str, str)  # timestamp, category, text


class FloatingOverlaySettingsDialog(QDialog):
    """🪟 독립 플로팅 오버레이 전용 설정 다이얼로그 (정면 / 후면 분리)"""

    def __init__(self, config: AppConfig, overlay_front: 'FloatingVestOverlay', overlay_back: 'FloatingVestOverlay', parent=None):
        super().__init__(parent)
        self.config = config
        self.overlay_front = overlay_front
        self.overlay_back = overlay_back

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(200)
        self._save_timer.timeout.connect(self.config.save)

        self.setWindowTitle("🪟 플로팅 오버레이 설정")
        self.setFixedSize(380, 230)
        self.setStyleSheet("""
            QDialog {
                background-color: #12141a;
                color: #e0e6ed;
                font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
            }
            QLabel {
                color: #c5d1de;
                font-size: 12px;
            }
            QCheckBox {
                color: #00e5ff;
                font-weight: bold;
                font-size: 12px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #2a313d;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #00e5ff;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00e5ff;
                border: 2px solid #ffffff;
                width: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QPushButton {
                background-color: #1e2530;
                color: #c5d1de;
                border: 1px solid #333f50;
                border-radius: 4px;
                padding: 6px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2b3545;
                border-color: #00e5ff;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        chk_layout = QHBoxLayout()
        self.chk_front = QCheckBox("정면(Front) 창 표시")
        self.chk_front.setChecked(self.config.overlay_show_front)
        self.chk_front.toggled.connect(self._on_front_toggled)
        chk_layout.addWidget(self.chk_front)

        self.chk_back = QCheckBox("후면(Back) 창 표시")
        self.chk_back.setChecked(self.config.overlay_show_back)
        self.chk_back.toggled.connect(self._on_back_toggled)
        chk_layout.addWidget(self.chk_back)
        layout.addLayout(chk_layout)

        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("크기 (Scale):"))
        self.sld_scale = QSlider(Qt.Horizontal)
        self.sld_scale.setRange(50, 180)
        self.sld_scale.setValue(int(self.config.overlay_scale * 100))
        self.lbl_scale_val = QLabel(f"{int(self.config.overlay_scale * 100)}%")
        self.lbl_scale_val.setFixedWidth(44)
        self.sld_scale.valueChanged.connect(self._on_scale_changed)
        scale_layout.addWidget(self.sld_scale, 1)
        scale_layout.addWidget(self.lbl_scale_val)
        layout.addLayout(scale_layout)

        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(QLabel("투명도 (Opacity):"))
        self.sld_opacity = QSlider(Qt.Horizontal)
        self.sld_opacity.setRange(20, 100)
        self.sld_opacity.setValue(int(self.config.overlay_opacity * 100))
        self.lbl_opacity_val = QLabel(f"{int(self.config.overlay_opacity * 100)}%")
        self.lbl_opacity_val.setFixedWidth(44)
        self.sld_opacity.valueChanged.connect(self._on_opacity_changed)
        opacity_layout.addWidget(self.sld_opacity, 1)
        opacity_layout.addWidget(self.lbl_opacity_val)
        layout.addLayout(opacity_layout)

        layout.addStretch()

        btn_close = QPushButton("확인 / 닫기")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, 0, Qt.AlignCenter)

    def _on_front_toggled(self, checked: bool):
        self.config.overlay_show_front = checked
        self._save_timer.stop()
        self.config.save()
        if self.config.show_floating_overlay:
            self.overlay_front.setVisible(checked)

    def _on_back_toggled(self, checked: bool):
        self.config.overlay_show_back = checked
        self._save_timer.stop()
        self.config.save()
        if self.config.show_floating_overlay:
            self.overlay_back.setVisible(checked)

    def _on_scale_changed(self, val: int):
        scale = val / 100.0
        self.lbl_scale_val.setText(f"{val}%")
        self.config.overlay_scale = scale
        self.overlay_front.set_overlay_scale(scale)
        self.overlay_back.set_overlay_scale(scale)
        self._save_timer.start()

    def _on_opacity_changed(self, val: int):
        opacity = val / 100.0
        self.lbl_opacity_val.setText(f"{val}%")
        self.config.overlay_opacity = opacity
        self.overlay_front.set_overlay_opacity(opacity)
        self.overlay_back.set_overlay_opacity(opacity)
        self._save_timer.start()

    def done(self, r: int):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.config.save()
        super().done(r)


class FloatingVestOverlay(QWidget):
    """틀 없이 진동 원과 '정면' 또는 '후면' 라벨만 표시되는 독립 개별 이동 창"""

    def __init__(self, vest_type: str, config: AppConfig, parent=None):
        super().__init__(parent)
        self.vest_type = vest_type
        self.config = config

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        self.intensities: List[float] = [0.0] * 20
        self.current_level: str = "none"

        self._is_dragging = False
        self._drag_pos = QPoint()

        self.scale_factor = self.config.overlay_scale
        self.setWindowOpacity(self.config.overlay_opacity)
        self._update_geometry()

    def _update_geometry(self):
        base_w = 125
        base_h = 150
        w = int(base_w * self.scale_factor)
        h = int(base_h * self.scale_factor)
        self.setFixedSize(w, h)

        if self.vest_type == "front":
            self.move(self.config.floating_front_x, self.config.floating_front_y)
        else:
            self.move(self.config.floating_back_x, self.config.floating_back_y)

    def set_overlay_scale(self, scale: float):
        self.scale_factor = max(0.5, min(2.0, scale))
        self._update_geometry()
        self.update()

    def set_overlay_opacity(self, opacity: float):
        op = max(0.2, min(1.0, opacity))
        self.setWindowOpacity(op)

    def update_data(self, intensities: List[float], level: str):
        self.intensities = intensities
        self.current_level = level
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and (event.buttons() & Qt.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            if self.vest_type == "front":
                self.config.floating_front_x = self.x()
                self.config.floating_front_y = self.y()
            else:
                self.config.floating_back_x = self.x()
                self.config.floating_back_y = self.y()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._is_dragging:
            self._is_dragging = False
            self.config.save()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        title = "정면" if self.vest_type == "front" else "후면"

        painter.setPen(QColor("#00e5ff"))
        painter.setFont(QFont("Segoe UI", int(10 * self.scale_factor), QFont.Bold))
        painter.drawText(0, int(14 * self.scale_factor), w, int(16 * self.scale_factor), Qt.AlignCenter, title)

        grid_top = int(24 * self.scale_factor)
        grid_h = h - grid_top - int(4 * self.scale_factor)
        cols = 4
        rows = 5
        cell_w = w / cols
        cell_h = grid_h / rows
        radius = min(cell_w, cell_h) * 0.36

        for idx in range(20):
            r = idx // cols
            c = idx % cols
            cx = c * cell_w + cell_w / 2.0
            cy = grid_top + r * cell_h + cell_h / 2.0
            intensity = self.intensities[idx] if idx < len(self.intensities) else 0.0

            if intensity > 0.0:
                if self.current_level in ["critical", "faint"]:
                    color = QColor(255, 30, 70, int(180 + 75 * (intensity / 100.0)))
                    glow = QColor(255, 0, 50, 100)
                elif self.current_level == "heavy":
                    color = QColor(255, 140, 0, int(180 + 75 * (intensity / 100.0)))
                    glow = QColor(255, 120, 0, 90)
                elif self.current_level == "medium":
                    color = QColor(255, 215, 0, int(180 + 75 * (intensity / 100.0)))
                    glow = QColor(255, 200, 0, 80)
                else:
                    color = QColor(0, 230, 255, int(180 + 75 * (intensity / 100.0)))
                    glow = QColor(0, 200, 255, 80)

                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius * 1.6), int(radius * 1.6))
                painter.setPen(QPen(QColor("#ffffff"), 1.5))
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))
            else:
                painter.setPen(QPen(QColor(80, 110, 150, 70), 1.0))
                painter.setBrush(QBrush(QColor(20, 30, 45, 50)))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))


class MiniVestPreviewWidget(QWidget):
    """우측 햅틱 제어 패널 상단에 내장되어 정면 20ch / 후면 20ch 진동 분포를 실시간 표시하는 미니 뷰어"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(96)
        self.front_intensities: List[float] = [0.0] * 20
        self.back_intensities: List[float] = [0.0] * 20
        self.current_level: str = "none"

    def update_data(self, front: List[float], back: List[float], level: str):
        if self.front_intensities != front or self.back_intensities != back or self.current_level != level:
            self.front_intensities = list(front)
            self.back_intensities = list(back)
            self.current_level = level
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()

        painter.setPen(QPen(QColor(163, 230, 53, 85), 1))
        painter.setBrush(QBrush(QColor(14, 21, 36, 235)))
        painter.drawRoundedRect(1, 1, w - 2, h - 2, 8, 8)

        level_names = {
            "light": ("🔹 경타 발동", "#22d3ee"),
            "medium": ("🔸 중타 발동", "#facc15"),
            "heavy": ("🔻 강타 발동", "#fb923c"),
            "critical": ("⚡ 치명타!", "#ff4757"),
            "faint": ("💀 기절 진동!", "#ff2e63"),
            "heartbeat": ("💓 심장박동", "#fb7185"),
            "low_hp_loop": ("🚨 빨피 상시", "#ef4444"),
        }
        status_txt, status_col = level_names.get(self.current_level, ("● VEST READY (40CH)", "#a3e635"))

        side_w = min(94, int(w * 0.32))
        self._draw_mini_grid(painter, 10, 6, side_w, h - 12, "정면 (Front)", self.front_intensities)
        self._draw_mini_grid(painter, w - side_w - 10, 6, side_w, h - 12, "후면 (Back)", self.back_intensities)

        mid_x = side_w + 14
        mid_w = max(40, w - (side_w * 2) - 28)
        painter.setPen(QColor(status_col))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(mid_x, 22, mid_w, 22, Qt.AlignCenter, status_txt)

        active_cnt = sum(1 for v in self.front_intensities + self.back_intensities if v > 0.0)
        painter.setPen(QColor("#94a3b8"))
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(mid_x, 48, mid_w, 20, Qt.AlignCenter, f"활성 모터: {active_cnt}/40")

    def _draw_mini_grid(self, painter: QPainter, x: int, y: int, gw: int, gh: int, label: str, intensities: List[float]):
        painter.setPen(QColor("#a3e635"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(x, y, gw, 14, Qt.AlignCenter, label)

        top = y + 16
        grid_h = gh - 16

        sil_poly = QPolygonF([
            QPointF(x + gw * 0.14, top + 2),
            QPointF(x + gw * 0.32, top - 1),
            QPointF(x + gw * 0.40, top + 6),
            QPointF(x + gw * 0.60, top + 6),
            QPointF(x + gw * 0.68, top - 1),
            QPointF(x + gw * 0.86, top + 2),
            QPointF(x + gw * 0.92, top + grid_h * 0.32),
            QPointF(x + gw * 0.84, top + grid_h * 0.42),
            QPointF(x + gw * 0.86, top + grid_h - 1),
            QPointF(x + gw * 0.14, top + grid_h - 1),
            QPointF(x + gw * 0.16, top + grid_h * 0.42),
            QPointF(x + gw * 0.08, top + grid_h * 0.32),
        ])
        painter.setPen(QPen(QColor(163, 230, 53, 60), 1.0))
        painter.setBrush(QBrush(QColor(20, 32, 52, 90)))
        painter.drawPolygon(sil_poly)

        cols, rows = 4, 5
        cell_w = gw / float(cols)
        cell_h = grid_h / float(rows)
        radius = min(cell_w, cell_h) * 0.34

        for idx in range(20):
            r = idx // cols
            c = idx % cols
            cx = x + c * cell_w + cell_w / 2.0
            cy = top + r * cell_h + cell_h / 2.0
            val = intensities[idx] if idx < len(intensities) else 0.0

            if val > 0.0:
                if self.current_level in ["critical", "faint"]:
                    col = QColor("#ff2e63")
                elif self.current_level == "heavy":
                    col = QColor("#fb923c")
                elif self.current_level == "medium":
                    col = QColor("#facc15")
                else:
                    col = QColor("#a3e635")
                painter.setPen(QPen(QColor("#ffffff"), 1.0))
                painter.setBrush(QBrush(col))
            else:
                painter.setPen(QPen(QColor(70, 95, 130, 100), 1.0))
                painter.setBrush(QBrush(QColor(18, 26, 42, 160)))
            painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))


class SlantedHpBarWidget(QWidget):
    """포챔스 인게임 배틀 카드 스타일의 비대칭 사선 HP 게이지 위젯"""

    def __init__(self, height: int = 26, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._value: float = 100.0
        self._text: str = "⚔️ HP: 100% (대기)"
        self._state_color: str = "lime"  # lime | yellow | red | paused | idle

    def value(self) -> float:
        return self._value

    def formatText(self) -> str:
        return self._text

    def stateColor(self) -> str:
        return self._state_color

    def setValue(self, val: float):
        clamped = max(0.0, min(100.0, float(val)))
        if clamped != self._value:
            self._value = clamped
            self.update()

    def setFormat(self, text: str):
        if text != self._text:
            self._text = text
            self.update()

    def setStateColor(self, state: str):
        if state != self._state_color:
            self._state_color = state
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        skew = min(14.0, h * 0.45)
        pad = 2.0

        track_poly = QPolygonF([
            QPointF(pad + skew, pad),
            QPointF(w - pad, pad),
            QPointF(w - pad - skew, h - pad),
            QPointF(pad, h - pad)
        ])

        border_col = QColor(163, 230, 53, 180)
        if self._state_color == "red":
            border_col = QColor(251, 113, 133, 220)
        elif self._state_color == "paused":
            border_col = QColor(245, 158, 11, 200)
        elif self._state_color == "idle":
            border_col = QColor(100, 116, 139, 150)

        painter.setPen(QPen(border_col, 1.5))
        painter.setBrush(QBrush(QColor(9, 13, 22, 235)))
        painter.drawPolygon(track_poly)

        if self._value > 0.0:
            clip_path = QPainterPath()
            clip_path.addPolygon(track_poly)
            painter.save()
            painter.setClipPath(clip_path)

            inner_w = (w - pad * 2 - skew) * (self._value / 100.0)
            fill_poly = QPolygonF([
                QPointF(pad + skew, pad),
                QPointF(pad + skew + inner_w + 2, pad),
                QPointF(pad + inner_w + 2, h - pad),
                QPointF(pad, h - pad)
            ])

            grad = QLinearGradient(0, 0, w, 0)
            if self._state_color == "paused":
                grad.setColorAt(0.0, QColor("#d97706"))
                grad.setColorAt(1.0, QColor("#f59e0b"))
            elif self._state_color == "idle":
                grad.setColorAt(0.0, QColor("#475569"))
                grad.setColorAt(1.0, QColor("#64748b"))
            elif self._value > 50.0:
                grad.setColorAt(0.0, QColor("#65a30d"))
                grad.setColorAt(0.5, QColor("#a3e635"))
                grad.setColorAt(1.0, QColor("#22d3ee"))
            elif self._value > 20.0:
                grad.setColorAt(0.0, QColor("#d97706"))
                grad.setColorAt(1.0, QColor("#facc15"))
            else:
                grad.setColorAt(0.0, QColor("#be123c"))
                grad.setColorAt(1.0, QColor("#fb7185"))

            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawPolygon(fill_poly)
            painter.restore()

        painter.setFont(QFont("Segoe UI", 9 if h <= 22 else 10, QFont.Bold))
        painter.setPen(QColor(0, 0, 0, 190))
        painter.drawText(1, 1, w, h, Qt.AlignCenter, self._text)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(0, 0, w, h, Qt.AlignCenter, self._text)


class VisionDebugWidget(QWidget):
    """🔍 실시간 비전 디버그 뷰어 (OCR 명암 강화, 원본 텍스트 크롭, 100% 순수 숫자 수치 모니터링)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #12121a; border: 1px solid #2d2d42; border-radius: 6px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        v1 = QVBoxLayout()
        lbl1 = QLabel("🔍 OCR 명암 강화:")
        lbl1.setStyleSheet("color: #a0a0c0; font-size: 10px; font-weight: bold;")
        v1.addWidget(lbl1)
        self.lbl_enhanced_crop = QLabel("대기 중...")
        self.lbl_enhanced_crop.setFixedSize(140, 50)
        self.lbl_enhanced_crop.setStyleSheet("background-color: #000; border: 1px solid #333; border-radius: 4px;")
        self.lbl_enhanced_crop.setAlignment(Qt.AlignCenter)
        v1.addWidget(self.lbl_enhanced_crop)
        layout.addLayout(v1)

        v2 = QVBoxLayout()
        lbl2 = QLabel("🔢 원본 텍스트 크롭:")
        lbl2.setStyleSheet("color: #a0a0c0; font-size: 10px; font-weight: bold;")
        v2.addWidget(lbl2)
        self.lbl_text_crop = QLabel("대기 중...")
        self.lbl_text_crop.setFixedSize(140, 50)
        self.lbl_text_crop.setStyleSheet("background-color: #000; border: 1px solid #333; border-radius: 4px;")
        self.lbl_text_crop.setAlignment(Qt.AlignCenter)
        v2.addWidget(self.lbl_text_crop)
        layout.addLayout(v2)

        v3 = QVBoxLayout()
        lbl3 = QLabel("📈 실시간 비전 진단:")
        lbl3.setStyleSheet("color: #a0a0c0; font-size: 10px; font-weight: bold;")
        v3.addWidget(lbl3)
        self.lbl_metrics = QLabel("방식: 순수 숫자(OCR)\nOCR: 인식 대기\n상태: IDLE")
        self.lbl_metrics.setStyleSheet("color: #00e5ff; font-family: 'Consolas', monospace; font-size: 11px; line-height: 1.3;")
        v3.addWidget(self.lbl_metrics)
        layout.addLayout(v3, 1)

    def update_debug_info(self, debug_data: dict):
        if not debug_data:
            return

        enhanced = debug_data.get("enhanced_crop")
        if enhanced is not None and enhanced.size > 0:
            enhanced_c = np.ascontiguousarray(enhanced)
            h, w = enhanced_c.shape[:2]
            q_img = QImage(enhanced_c.data, w, h, w, QImage.Format_Grayscale8).copy()
            pix = QPixmap.fromImage(q_img).scaled(self.lbl_enhanced_crop.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_enhanced_crop.setPixmap(pix)

        txt_crop = debug_data.get("text_crop")
        if txt_crop is not None and txt_crop.size > 0:
            rgb = np.ascontiguousarray(cv2.cvtColor(txt_crop, cv2.COLOR_BGR2RGB))
            h, w, ch = rgb.shape
            q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888).copy()
            pix = QPixmap.fromImage(q_img).scaled(self.lbl_text_crop.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_text_crop.setPixmap(pix)

        ocr = debug_data.get("ocr_reading")
        ocr_str = f"{ocr[0]}/{ocr[1]} ({ocr[2]:.1f}%)" if ocr else "인식 대기"
        state = debug_data.get("battle_state", "IDLE")
        if debug_data.get("is_paused"):
            state = "PAUSED (일시정지)"

        txt = f"감지 방식: 100% 순수 숫자(OCR)\nOCR 수치: {ocr_str}\n배틀 상태: {state}"
        self.lbl_metrics.setText(txt)


class VideoWidget(QWidget):
    """비디오 프레임 렌더링 및 마우스 드래그 ROI 선택기 (종횡비 100% 엄격 유지)"""
    roi_selected = Signal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setStyleSheet("background-color: #07080c; border-radius: 6px;")

        self.current_frame: Optional[np.ndarray] = None
        self.is_camera_connected: bool = True
        self._is_dragging = False
        self._drag_start = QPoint()
        self._drag_end = QPoint()

    def set_camera_status(self, connected: bool):
        self.is_camera_connected = connected
        self.update()

    def update_frame(self, frame: np.ndarray):
        self.current_frame = frame
        self.update()

    def get_render_rect(self) -> QRect:
        """현재 위젯 크기 내부에서 원본 영상 비율(Aspect Ratio)을 100% 유지하는 실제 렌더링 사각형 계산"""
        W = self.width()
        H = self.height()
        if self.current_frame is None or self.current_frame.size == 0:
            return self.rect()
        fh, fw = self.current_frame.shape[:2]
        aspect = fw / float(max(1, fh))
        widget_aspect = W / float(max(1, H))
        if widget_aspect > aspect:
            render_h = H
            render_w = int(H * aspect)
            offset_x = (W - render_w) // 2
            offset_y = 0
        else:
            render_w = W
            render_h = int(W / aspect)
            offset_x = 0
            offset_y = (H - render_h) // 2
        return QRect(offset_x, offset_y, render_w, render_h)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_start = event.pos()
            self._drag_end = event.pos()
            self.update()

    def mouseMoveEvent(self, event):
        if self._is_dragging:
            self._drag_end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_dragging:
            self._is_dragging = False
            self._drag_end = event.pos()
            self.update()

            target_rect = self.get_render_rect()
            if target_rect.width() <= 0 or target_rect.height() <= 0:
                return

            x1 = min(self._drag_start.x(), self._drag_end.x())
            y1 = min(self._drag_start.y(), self._drag_end.y())
            x2 = max(self._drag_start.x(), self._drag_end.x())
            y2 = max(self._drag_start.y(), self._drag_end.y())

            rx1 = max(target_rect.left(), min(target_rect.right(), x1))
            ry1 = max(target_rect.top(), min(target_rect.bottom(), y1))
            rx2 = max(target_rect.left(), min(target_rect.right(), x2))
            ry2 = max(target_rect.top(), min(target_rect.bottom(), y2))

            w = max(5, rx2 - rx1)
            h = max(5, ry2 - ry1)

            norm_x = (rx1 - target_rect.left()) / float(target_rect.width())
            norm_y = (ry1 - target_rect.top()) / float(target_rect.height())
            norm_w = w / float(target_rect.width())
            norm_h = h / float(target_rect.height())

            norm_x = max(0.0, min(1.0, norm_x))
            norm_y = max(0.0, min(1.0, norm_y))
            norm_w = max(0.01, min(1.0 - norm_x, norm_w))
            norm_h = max(0.01, min(1.0 - norm_y, norm_h))

            self.roi_selected.emit(norm_x, norm_y, norm_w, norm_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.fillRect(self.rect(), QColor("#07080c"))
        target_rect = self.get_render_rect()

        if self.current_frame is not None:
            frame_c = np.ascontiguousarray(self.current_frame)
            fh, fw, ch = frame_c.shape
            bytes_per_line = ch * fw
            q_img = QImage(frame_c.data, fw, fh, bytes_per_line, QImage.Format.Format_BGR888).copy()
            painter.drawImage(target_rect, q_img)

            if not self.is_camera_connected:
                painter.fillRect(target_rect, QColor(25, 10, 15, 205))
                painter.setPen(QColor("#ff4757"))
                painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
                painter.drawText(target_rect, Qt.AlignCenter, "⚠️ 캡처보드 신호 단절 감지\n자동 재연결 시도 중... (Switch 독 또는 OBS 확인)")
        else:
            painter.setFont(QFont("Segoe UI", 11))
            if not self.is_camera_connected:
                painter.setPen(QColor("#ff4757"))
                painter.drawText(self.rect(), Qt.AlignCenter, "⚠️ 비디오 신호 단절\n자동 재연결 대기 중...")
            else:
                painter.setPen(QColor("#4a4a60"))
                painter.drawText(self.rect(), Qt.AlignCenter, "비디오 신호 대기 중...")

        if self._is_dragging:
            x = min(self._drag_start.x(), self._drag_end.x())
            y = min(self._drag_start.y(), self._drag_end.y())
            bw = abs(self._drag_end.x() - self._drag_start.x())
            bh = abs(self._drag_end.y() - self._drag_start.y())

            painter.setPen(QPen(QColor(0, 255, 128, 220), 2, Qt.DashLine))
            painter.setBrush(QBrush(QColor(0, 255, 128, 40)))
            painter.drawRect(x, y, bw, bh)
