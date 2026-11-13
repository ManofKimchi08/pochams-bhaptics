import sys
import os
import time
import math
from typing import List, Dict, Optional, Tuple

import cv2
import numpy as np

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint, QPointF, QRect, QRectF
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QPen, QBrush, QFont,
    QLinearGradient, QRadialGradient, QIcon, QTextCursor,
    QKeySequence, QKeyEvent, QShortcut, QPolygonF, QPainterPath
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox, QSlider,
    QProgressBar, QTextEdit, QGroupBox, QSplitter, QMessageBox, QFrame,
    QDialog, QGridLayout, QScrollArea, QDockWidget, QTabWidget, QSizePolicy,
    QToolBar
)

from config import AppConfig, HapticSinkConfig, DetailedHapticConfig, HapticDetailRow
from fusion_engine import FusionEngine
from vision_detector import VisionDetector
from battle_analytics import BattleAnalytics

class QSignalBridge(QObject):
    """엔진 백그라운드 스레드와 Qt UI 메인 스레드 간 비동기 시그널 브릿지"""
    hp_updated = Signal(float, float, bool, str)
    haptic_status = Signal(bool, str)
    camera_status = Signal(bool, str)
    log_message = Signal(str, str, str) # timestamp, category, text

# =============================================================================
# 🪟 1. 독립 플로팅 오버레이 설정 다이얼로그
# =============================================================================
class FloatingOverlaySettingsDialog(QDialog):
    """🪟 독립 플로팅 오버레이 전용 설정 다이얼로그 (정면 / 후면 분리)"""

    def __init__(self, config: AppConfig, overlay_front: 'FloatingVestOverlay', overlay_back: 'FloatingVestOverlay', parent=None):
        super().__init__(parent)
        self.config = config
        self.overlay_front = overlay_front
        self.overlay_back = overlay_back
        
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

        # 1. 정면 / 후면 표시 체크박스
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

        # 2. 크기 조절 슬라이더
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

        # 3. 투명도 조절 슬라이더
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
        self.config.save()
        if self.config.show_floating_overlay:
            self.overlay_front.setVisible(checked)

    def _on_back_toggled(self, checked: bool):
        self.config.overlay_show_back = checked
        self.config.save()
        if self.config.show_floating_overlay:
            self.overlay_back.setVisible(checked)

    def _on_scale_changed(self, val: int):
        scale = val / 100.0
        self.lbl_scale_val.setText(f"{val}%")
        self.config.overlay_scale = scale
        self.config.save()
        self.overlay_front.set_overlay_scale(scale)
        self.overlay_back.set_overlay_scale(scale)

    def _on_opacity_changed(self, val: int):
        opacity = val / 100.0
        self.lbl_opacity_val.setText(f"{val}%")
        self.config.overlay_opacity = opacity
        self.config.save()
        self.overlay_front.set_overlay_opacity(opacity)
        self.overlay_back.set_overlay_opacity(opacity)

# =============================================================================
# 🪟 2. 독립 분리 가능한 순수 원형 플로팅 HUD 창 (정면 또는 후면 단독)
# =============================================================================
class FloatingVestOverlay(QWidget):
    """틀 없이 진동 원과 '정면' 또는 '후면' 라벨만 표시되는 독립 개별 이동 창"""

    def __init__(self, vest_type: str, config: AppConfig, parent=None):
        super().__init__(parent)
        self.vest_type = vest_type  # "front" 또는 "back"
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
        self._is_dragging = False
        self.config.save()
        event.accept()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        title = "정면" if self.vest_type == "front" else "후면"

        # 1. 상단 라벨
        painter.setPen(QColor("#00e5ff"))
        painter.setFont(QFont("Segoe UI", int(10 * self.scale_factor), QFont.Bold))
        painter.drawText(0, int(14 * self.scale_factor), w, int(16 * self.scale_factor), Qt.AlignCenter, title)

        # 2. 4x5 원형 모터 그리드
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
                # 대기 상태
                painter.setPen(QPen(QColor(80, 110, 150, 70), 1.0))
                painter.setBrush(QBrush(QColor(20, 30, 45, 50)))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))

# =============================================================================
# 🎽 2-B. 메인 대시보드 내장형 실시간 정면/후면 미니 조끼 LED 모니터
# =============================================================================
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

        # 배경 카드 (포챔스 글래스모피즘 + 라임/시안 테두리)
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

        # 중앙 상태 배지 및 좌우 정면/후면 그리드 배치
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

        # 전술 조끼 외곽선 실루엣
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

# =============================================================================
# ⚡ 2-C. 포켓몬 챔피언스(SV) 사선(Slanted) 글래스모피즘 HP 게이지 위젯
# =============================================================================
class SlantedHpBarWidget(QWidget):
    """포챔스 인게임 배틀 카드 스타일의 비대칭 사선 HP 게이지 위젯"""

    def __init__(self, height: int = 26, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._value: float = 100.0
        self._text: str = "⚔️ HP: 100% (대기)"
        self._state_color: str = "lime"  # lime | yellow | red | paused | idle

    def setValue(self, val: float):
        self._value = max(0.0, min(100.0, float(val)))
        self.update()

    def setFormat(self, text: str):
        self._text = text
        self.update()

    def setStateColor(self, state: str):
        self._state_color = state
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        skew = min(14.0, h * 0.45)
        pad = 2.0

        # 1. 외곽 사선 트랙
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

        # 2. 내부 채워지는 사선 게이지 (트랙 내부에 클리핑)
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

        # 3. 중앙 텍스트 (그림자 + 선명한 화이트)
        painter.setFont(QFont("Segoe UI", 9 if h <= 22 else 10, QFont.Bold))
        painter.setPen(QColor(0, 0, 0, 190))
        painter.drawText(1, 1, w, h, Qt.AlignCenter, self._text)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(0, 0, w, h, Qt.AlignCenter, self._text)

# =============================================================================
# 🎯 2-D. 4안: 실전 집중 초슬림 컴팩트 모드 컨트롤 바 (CompactHudWindow)
# =============================================================================
class CompactHudWindow(QWidget):
    """게임 화면 위에 작게 띄워 실시간 HP, 진동 상태, 모드 전환, 일시정지만 빠르게 제어하는 컴팩트 창"""
    expand_requested = Signal()
    pause_requested = Signal()
    mode_changed_requested = Signal(str)

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._is_dragging = False
        self._drag_pos = QPoint()
        self._allow_force_close = False

        self.setWindowTitle("PokéChamps Compact HUD")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(850, 68)
        self.move(getattr(self.config, "compact_mode_x", 180), getattr(self.config, "compact_mode_y", 36))

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setStyleSheet("""
            QFrame#CompactFrame {
                background-color: rgba(11, 16, 27, 235);
                border: 1.5px solid rgba(163, 230, 53, 180);
                border-radius: 14px;
            }
            QPushButton {
                background-color: rgba(30, 41, 59, 220);
                color: #e2e8f0;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                border-color: #a3e635;
                color: #ffffff;
            }
            QComboBox {
                background-color: #162033;
                color: #bef264;
                border: 1px solid rgba(163, 230, 53, 140);
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        self.frame.setObjectName("CompactFrame")
        outer.addWidget(self.frame)

        row = QHBoxLayout(self.frame)
        row.setContentsMargins(14, 8, 14, 8)
        row.setSpacing(10)

        # 브랜드 태그 (드래그 핸들)
        self.lbl_brand = QLabel("POKE\nHAPTIC")
        self.lbl_brand.setStyleSheet("color: #a3e635; font-weight: 900; font-size: 11px; border: none; background: transparent;")
        self.lbl_brand.setToolTip("드래그하여 원하는 화면 위치로 이동할 수 있습니다.")
        row.addWidget(self.lbl_brand)

        # 사선 HP 게이지
        self.hp_bar = SlantedHpBarWidget(height=24)
        self.hp_bar.setMinimumWidth(260)
        row.addWidget(self.hp_bar, 1)

        # 현재 진동 상태 배지
        self.lbl_haptic = QLabel("● 대기 중")
        self.lbl_haptic.setFixedWidth(104)
        self.lbl_haptic.setAlignment(Qt.AlignCenter)
        self.lbl_haptic.setStyleSheet("background-color: #132030; color: #a3e635; border: 1px solid #2b445e; border-radius: 8px; padding: 4px 6px; font-size: 11px; font-weight: bold;")
        row.addWidget(self.lbl_haptic)

        # 빠른 감지 모드 콤보
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("⚡ 초고속", "fast")
        self.combo_mode.addItem("⚖️ 균형", "balanced")
        self.combo_mode.addItem("🎯 고정밀", "accurate")
        cur_mode = getattr(self.config, "detection_mode", "balanced")
        mode_map = {"fast": 0, "balanced": 1, "accurate": 2}
        self.combo_mode.setCurrentIndex(mode_map.get(cur_mode, 1))
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        row.addWidget(self.combo_mode)

        # 일시정지 버튼
        self.btn_pause = QPushButton("⏸ 일시정지")
        self.btn_pause.clicked.connect(self.pause_requested.emit)
        row.addWidget(self.btn_pause)

        # 전체 창 펼치기 버튼
        self.btn_expand = QPushButton("⊞ 전체 창 펼치기")
        self.btn_expand.setStyleSheet("background-color: rgba(163, 230, 53, 35); color: #bef264; border: 1px solid #a3e635; border-radius: 8px; padding: 5px 12px; font-size: 11px; font-weight: bold;")
        self.btn_expand.clicked.connect(self.expand_requested.emit)
        row.addWidget(self.btn_expand)

    def _on_mode_changed(self):
        mode = self.combo_mode.currentData()
        if mode:
            self.mode_changed_requested.emit(mode)

    def sync_mode(self, mode: str):
        self.combo_mode.blockSignals(True)
        mode_map = {"fast": 0, "balanced": 1, "accurate": 2}
        self.combo_mode.setCurrentIndex(mode_map.get(mode, 1))
        self.combo_mode.blockSignals(False)

    def sync_paused(self, is_paused: bool):
        if is_paused:
            self.btn_pause.setText("▶️ 재개")
            self.btn_pause.setStyleSheet("background-color: #15803d; color: #ffffff; border: 1px solid #22c55e; border-radius: 8px; padding: 5px 10px; font-size: 11px; font-weight: bold;")
            self.hp_bar.setStateColor("paused")
            self.hp_bar.setFormat("⏸️ 일시정지 중")
        else:
            self.btn_pause.setText("⏸ 일시정지")
            self.btn_pause.setStyleSheet("")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._is_dragging and (event.buttons() & Qt.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            self.config.compact_mode_x = self.x()
            self.config.compact_mode_y = self.y()
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._is_dragging:
            self._is_dragging = False
            self.config.save()
        event.accept()

    def closeEvent(self, event):
        if self._allow_force_close:
            event.accept()
            return
        self.expand_requested.emit()
        event.ignore()

# =============================================================================
# 🔍 3. 실시간 비전 디버그 모니터 위젯
# =============================================================================
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
            h, w = enhanced.shape[:2]
            q_img = QImage(enhanced.data, w, h, w, QImage.Format_Grayscale8)
            pix = QPixmap.fromImage(q_img).scaled(self.lbl_enhanced_crop.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_enhanced_crop.setPixmap(pix)
            
        txt_crop = debug_data.get("text_crop")
        if txt_crop is not None and txt_crop.size > 0:
            h, w, ch = txt_crop.shape
            rgb = cv2.cvtColor(txt_crop, cv2.COLOR_BGR2RGB)
            q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pix = QPixmap.fromImage(q_img).scaled(self.lbl_text_crop.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_text_crop.setPixmap(pix)
            
        ocr = debug_data.get("ocr_reading")
        ocr_str = f"{ocr[0]}/{ocr[1]} ({ocr[2]:.1f}%)" if ocr else "인식 대기"
        state = debug_data.get("battle_state", "IDLE")
        if debug_data.get("is_paused"):
            state = "PAUSED (일시정지)"
            
        txt = f"감지 방식: 100% 순수 숫자(OCR)\nOCR 수치: {ocr_str}\n배틀 상태: {state}"
        self.lbl_metrics.setText(txt)

# =============================================================================
# 🎥 4. 비디오 뷰어 위젯 (순수 게임 화면 및 ROI 선택)
# =============================================================================
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
            # 위젯이 영상보다 더 넓음 -> 좌우 필러박스(Pillarbox) 여백 생성
            render_h = H
            render_w = int(H * aspect)
            offset_x = (W - render_w) // 2
            offset_y = 0
        else:
            # 위젯이 영상보다 더 높음 -> 상하 레터박스(Letterbox) 여백 생성
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
            
            # 실제 영상 표시 영역(target_rect) 내부로 마우스 좌표 클램핑
            rx1 = max(target_rect.left(), min(target_rect.right(), x1))
            ry1 = max(target_rect.top(), min(target_rect.bottom(), y1))
            rx2 = max(target_rect.left(), min(target_rect.right(), x2))
            ry2 = max(target_rect.top(), min(target_rect.bottom(), y2))
            
            w = max(5, rx2 - rx1)
            h = max(5, ry2 - ry1)
            
            # 실제 영상 기준 정규화 비율 (0.0 ~ 1.0) 계산 (레터박스 오차 100% 보정)
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
        
        # 1. 캔버스 전체를 레터박스 배경색(#07080c)으로 깔끔하게 채움
        painter.fillRect(self.rect(), QColor("#07080c"))
        
        target_rect = self.get_render_rect()
        
        if self.current_frame is not None:
            fh, fw, ch = self.current_frame.shape
            bytes_per_line = ch * fw
            # 🚀 원본 종횡비(Aspect Ratio)를 100% 엄격 유지하여 왜곡 없이 렌더링
            q_img = QImage(self.current_frame.data, fw, fh, bytes_per_line, QImage.Format.Format_BGR888)
            painter.drawImage(target_rect, q_img)
            
            # 🔄 신호 단절 시 반투명 경고 오버레이 렌더링
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

# =============================================================================
# 🎛️ 5. 진동 세부 설정 스크롤 내장 컴포넌트 (9개 항목 + 체감 데미지)
# =============================================================================
class EmbeddedHapticDetailView(QWidget):
    """햅틱 세기 제어 창 내부에 스크롤로 직접 내장되는 세부 설정 뷰어"""

    def __init__(self, config: AppConfig, engine: FusionEngine, parent=None):
        super().__init__(parent)
        self.config = config
        self.engine = engine
        self.details = config.haptic_details
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(10)

        # 0. ⚡ 원클릭 체감 진동 프리셋 카드 (3안 포챔스 테마)
        preset_card = QFrame()
        preset_card.setStyleSheet("""
            QFrame {
                background-color: rgba(17, 25, 42, 230);
                border: 1px solid rgba(163, 230, 53, 95);
                border-radius: 8px;
            }
        """)
        preset_v = QVBoxLayout(preset_card)
        preset_v.setContentsMargins(10, 8, 10, 8)
        preset_v.setSpacing(6)

        lbl_preset = QLabel("⚡ 원클릭 체감 진동 프리셋")
        lbl_preset.setStyleSheet("color: #a3e635; font-size: 11px; font-weight: bold; border: none; background: transparent;")
        preset_v.addWidget(lbl_preset)

        preset_btn_row = QHBoxLayout()
        preset_btn_row.setSpacing(6)
        self.btn_preset_mild = QPushButton("🍃 순한맛 (입문)")
        self.btn_preset_std = QPushButton("⚖️ 표준 (밸런스)")
        self.btn_preset_hard = QPushButton("🔥 극한 (하드코어)")

        for p_btn, p_key, p_style in [
            (self.btn_preset_mild, "mild", "background-color: #132a24; color: #6ee7b7; border: 1px solid #059669; border-radius: 6px; padding: 5px 6px; font-size: 11px; font-weight: bold;"),
            (self.btn_preset_std, "standard", "background-color: #1d2d18; color: #bef264; border: 1px solid #a3e635; border-radius: 6px; padding: 5px 6px; font-size: 11px; font-weight: bold;"),
            (self.btn_preset_hard, "hardcore", "background-color: #2f151d; color: #fda4af; border: 1px solid #f43f5e; border-radius: 6px; padding: 5px 6px; font-size: 11px; font-weight: bold;"),
        ]:
            p_btn.setStyleSheet(p_style)
            p_btn.clicked.connect(lambda _, k=p_key: self._apply_preset(k))
            preset_btn_row.addWidget(p_btn)
        preset_v.addLayout(preset_btn_row)
        main_layout.addWidget(preset_card)

        # 1. 상단 안내 및 전부 기본값으로 버튼
        top_bar = QHBoxLayout()
        lbl_info = QLabel("슬라이더 조작 시 즉시 적용됩니다.")
        lbl_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        top_bar.addWidget(lbl_info)
        top_bar.addStretch()

        btn_reset_all = QPushButton("전부 기본값으로")
        btn_reset_all.setStyleSheet("background-color: #162033; color: #cbd5e1; padding: 4px 10px; font-size: 11px; border-radius: 6px; border: 1px solid #334155;")
        btn_reset_all.clicked.connect(self._reset_all_defaults)
        top_bar.addWidget(btn_reset_all)
        main_layout.addLayout(top_bar)

        # 🌊 피격 충격파(Ripple) 분산 햅틱 스위치 카드
        ripple_card = QFrame()
        ripple_card.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 28, 46, 220);
                border: 1px solid rgba(34, 211, 238, 100);
                border-radius: 8px;
            }
        """)
        ripple_layout = QHBoxLayout(ripple_card)
        ripple_layout.setContentsMargins(10, 6, 10, 6)
        
        self.chk_ripple = QCheckBox("🌊 피격 충격파(Ripple) 분산 효과")
        self.chk_ripple.setStyleSheet("color: #22d3ee; font-weight: bold; font-size: 11px;")
        self.chk_ripple.setChecked(getattr(self.details, "enable_ripple_effect", True))
        self.chk_ripple.toggled.connect(self._on_ripple_toggled)
        ripple_layout.addWidget(self.chk_ripple)
        ripple_layout.addStretch()
        
        lbl_ripple_desc = QLabel("가슴 타격 → 외곽 확산 → 등 관통")
        lbl_ripple_desc.setStyleSheet("color: #94a3b8; font-size: 10px;")
        ripple_layout.addWidget(lbl_ripple_desc)
        main_layout.addWidget(ripple_card)

        # 2. 8개 카드 리스트 (독·화상 제외) + 등급별 컬러 악센트
        self.rows_def = [
            ("light", "경타", "체력 1~20% 깎임", True, True, True),
            ("medium", "중타", "21~50% 깎임", True, True, True),
            ("heavy", "강타", "51~80% 깎임", True, True, True),
            ("critical", "치명타", "81~100% 깎임", True, True, True),
            ("faint", "기절", "쓰러졌을 때", True, True, True),
            ("heartbeat", "심장박동", "빨간 체력 가변 66~158 BPM", True, True, False),
            ("low_hp_loop", "빨피 상시", "빨간 체력 지속딜", True, True, False),
            ("balance", "앞뒤 균형", "앞면 / 뒷면 세기", True, True, False)
        ]

        accent_colors = {
            "light": "#22d3ee",
            "medium": "#facc15",
            "heavy": "#fb923c",
            "critical": "#ff4757",
            "faint": "#f43f5e",
            "heartbeat": "#fb7185",
            "low_hp_loop": "#ef4444",
            "balance": "#a3e635",
        }

        self.row_widgets = {}

        for key, title, desc, has_int, has_dur, has_hits in self.rows_def:
            acc_col = accent_colors.get(key, "#22d3ee")
            card = QFrame()
            card.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(15, 23, 42, 220);
                    border: 1px solid rgba(148, 163, 184, 45);
                    border-left: 4px solid {acc_col};
                    border-radius: 8px;
                }}
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 8, 8, 8)
            card_layout.setSpacing(6)

            # 카드 상단: 제목 + 설명 + 시험/되돌리기 버튼
            card_top = QHBoxLayout()
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet(f"color: {acc_col}; font-size: 12px; font-weight: bold; border: none;")
            card_top.addWidget(lbl_title)

            lbl_desc = QLabel(f"({desc})")
            lbl_desc.setStyleSheet("color: #94a3b8; font-size: 11px; border: none;")
            card_top.addWidget(lbl_desc)
            card_top.addStretch()

            widgets = {}

            if key != "balance":
                btn_test = QPushButton("시험")
                btn_test.setStyleSheet("background-color: #0077b6; color: #fff; padding: 2px 8px; font-size: 10px; border-radius: 3px;")
                btn_test.clicked.connect(lambda _, k=key: self._on_test_row(k))
                card_top.addWidget(btn_test)

            btn_reset = QPushButton("되돌리기")
            btn_reset.setStyleSheet("background-color: #1f2736; color: #8bb4ff; padding: 2px 8px; font-size: 10px; border-radius: 3px; border: 1px solid #333f50;")
            btn_reset.clicked.connect(lambda _, k=key: self._on_reset_row(k))
            card_top.addWidget(btn_reset)
            card_layout.addLayout(card_top)

            # 슬라이더 컨트롤들
            ctrl_grid = QGridLayout()
            ctrl_grid.setHorizontalSpacing(8)
            ctrl_grid.setVerticalSpacing(4)
            ctrl_col = 0

            # 세기
            if has_int:
                lbl_tag = QLabel("앞면:" if key == "balance" else "세기:")
                lbl_tag.setStyleSheet("color: #a4b0be; font-size: 11px;")
                cur_int = self.details.front_balance if key == "balance" else getattr(self.details, key).intensity
                sld_int = QSlider(Qt.Horizontal)
                sld_int.setRange(0, 100)
                sld_int.setValue(cur_int)
                lbl_int_val = QLabel(f"{cur_int}%")
                lbl_int_val.setFixedWidth(38)
                lbl_int_val.setStyleSheet("color: #f1f2f6; font-family: monospace; font-size: 11px;")
                sld_int.valueChanged.connect(lambda v, k=key, l=lbl_int_val: self._on_intensity_changed(k, v, l))
                
                ctrl_grid.addWidget(lbl_tag, 0, 0)
                ctrl_grid.addWidget(sld_int, 0, 1)
                ctrl_grid.addWidget(lbl_int_val, 0, 2)
                widgets["sld_int"] = sld_int
                widgets["lbl_int_val"] = lbl_int_val

            # 길이 (앞뒤 균형의 경우 뒷면)
            if has_dur:
                if key == "balance":
                    lbl_tag2 = QLabel("뒷면:")
                    lbl_tag2.setStyleSheet("color: #a4b0be; font-size: 11px;")
                    cur_back = self.details.back_balance
                    sld_dur = QSlider(Qt.Horizontal)
                    sld_dur.setRange(0, 100)
                    sld_dur.setValue(cur_back)
                    lbl_dur_val = QLabel(f"{cur_back}%")
                    lbl_dur_val.setFixedWidth(44)
                    lbl_dur_val.setStyleSheet("color: #f1f2f6; font-family: monospace; font-size: 11px;")
                    sld_dur.valueChanged.connect(lambda v, l=lbl_dur_val: self._on_back_balance_changed(v, l))
                else:
                    lbl_tag2 = QLabel("길이:")
                    lbl_tag2.setStyleSheet("color: #a4b0be; font-size: 11px;")
                    cur_dur = getattr(self.details, key).duration
                    sld_dur = QSlider(Qt.Horizontal)
                    min_d = 35 if key == "low_hp_loop" else 5
                    sld_dur.setRange(min_d, 150)
                    sld_dur.setValue(int(cur_dur * 100))
                    lbl_dur_val = QLabel(f"{cur_dur:.2f}초")
                    lbl_dur_val.setFixedWidth(44)
                    lbl_dur_val.setStyleSheet("color: #f1f2f6; font-family: monospace; font-size: 11px;")
                    sld_dur.valueChanged.connect(lambda v, k=key, l=lbl_dur_val: self._on_duration_changed(k, v, l))

                ctrl_grid.addWidget(lbl_tag2, 0, 3)
                ctrl_grid.addWidget(sld_dur, 0, 4)
                ctrl_grid.addWidget(lbl_dur_val, 0, 5)
                widgets["sld_dur"] = sld_dur
                widgets["lbl_dur_val"] = lbl_dur_val

            # 타격횟수
            if has_hits:
                lbl_tag3 = QLabel("타격:")
                lbl_tag3.setStyleSheet("color: #a4b0be; font-size: 11px;")
                cur_hits = getattr(self.details, key).hit_count
                sld_hits = QSlider(Qt.Horizontal)
                sld_hits.setRange(1, 5)
                sld_hits.setValue(cur_hits)
                lbl_hits_val = QLabel(f"{cur_hits}번")
                lbl_hits_val.setFixedWidth(32)
                lbl_hits_val.setStyleSheet("color: #f1f2f6; font-family: monospace; font-size: 11px;")
                sld_hits.valueChanged.connect(lambda v, k=key, l=lbl_hits_val: self._on_hit_count_changed(k, v, l))

                ctrl_grid.addWidget(lbl_tag3, 1, 0)
                ctrl_grid.addWidget(sld_hits, 1, 1)
                ctrl_grid.addWidget(lbl_hits_val, 1, 2)
                widgets["sld_hits"] = sld_hits
                widgets["lbl_hits_val"] = lbl_hits_val

            # 피격 부위 선택기 (정+후, 정면만, 후면만)
            if key != "balance":
                lbl_pos = QLabel("부위:")
                lbl_pos.setStyleSheet("color: #a4b0be; font-size: 11px;")
                combo_pos = QComboBox()
                combo_pos.setStyleSheet("background-color: #1a2234; color: #00e5ff; font-size: 11px; padding: 2px 4px; border: 1px solid #2d3d5a; border-radius: 3px;")
                combo_pos.addItem("정+후 (기본)", "All")
                combo_pos.addItem("정면만", "VestFront")
                combo_pos.addItem("후면만", "VestBack")
                
                cur_pos = getattr(self.details, key).position
                p_idx = combo_pos.findData(cur_pos)
                combo_pos.setCurrentIndex(p_idx if p_idx >= 0 else 0)
                combo_pos.currentIndexChanged.connect(lambda idx, k=key, cb=combo_pos: self._on_position_changed(k, cb.currentData()))
                
                if has_hits:
                    ctrl_grid.addWidget(lbl_pos, 1, 3)
                    ctrl_grid.addWidget(combo_pos, 1, 4, 1, 2)
                else:
                    ctrl_grid.addWidget(lbl_pos, 1, 0)
                    ctrl_grid.addWidget(combo_pos, 1, 1, 1, 2)
                widgets["combo_pos"] = combo_pos

            card_layout.addLayout(ctrl_grid)
            main_layout.addWidget(card)
            self.row_widgets[key] = widgets

        # 3. 하단 체감 데미지 지표 (형광 녹색)
        damage_box = QFrame()
        damage_box.setStyleSheet("background-color: #0b1118; border: 1px solid #1a3344; border-radius: 6px; padding: 6px;")
        dmg_layout = QVBoxLayout(damage_box)
        dmg_layout.setContentsMargins(6, 4, 6, 4)
        
        lbl_dmg_title = QLabel("📊 실시간 계산 체감 데미지:")
        lbl_dmg_title.setStyleSheet("color: #7f8fa6; font-size: 11px; font-weight: bold;")
        dmg_layout.addWidget(lbl_dmg_title)

        self.lbl_perceived_damage = QLabel("경타 31  <  중타 78  <  강타 134  <  기절 157  <  치명타 172")
        self.lbl_perceived_damage.setStyleSheet("color: #00ff88; font-size: 12px; font-weight: bold; font-family: monospace;")
        dmg_layout.addWidget(self.lbl_perceived_damage)
        main_layout.addWidget(damage_box)

        # 4. 팁 텍스트
        lbl_tips = QLabel(
            "• 타격횟수: 1회 피격 시 연속 진동 횟수\n"
            "• 빨피 상시: 0.35초 이상 유지 권장\n"
            "• 심장박동: 길이 증가 시 분당 박동수 조절"
        )
        lbl_tips.setStyleSheet("color: #636e72; font-size: 10px; line-height: 1.4;")
        main_layout.addWidget(lbl_tips)
        
        self._update_perceived_damage()

    def _on_intensity_changed(self, key: str, val: int, lbl: QLabel):
        lbl.setText(f"{val}%")
        if key == "balance":
            self.details.front_balance = val
        else:
            getattr(self.details, key).intensity = val
        self._apply_and_update()

    def _on_back_balance_changed(self, val: int, lbl: QLabel):
        lbl.setText(f"{val}%")
        self.details.back_balance = val
        self._apply_and_update()

    def _on_duration_changed(self, key: str, val: int, lbl: QLabel):
        sec = val / 100.0
        lbl.setText(f"{sec:.2f}초")
        getattr(self.details, key).duration = sec
        self._apply_and_update()

    def _on_hit_count_changed(self, key: str, val: int, lbl: QLabel):
        lbl.setText(f"{val}번")
        getattr(self.details, key).hit_count = val
        self._apply_and_update()

    def _on_position_changed(self, key: str, pos_val: str):
        if pos_val and key != "balance":
            getattr(self.details, key).position = pos_val
            self._apply_and_update()

    def _apply_and_update(self):
        self.engine.haptics.details = self.details
        self.config.haptic_details = self.details
        self.config.save()
        self._update_perceived_damage()

    def _update_perceived_damage(self):
        d = self.details
        p_light = int(d.light.intensity * d.light.duration * d.light.hit_count * 1.2)
        p_med = int(d.medium.intensity * d.medium.duration * d.medium.hit_count * 1.2)
        p_heavy = int(d.heavy.intensity * d.heavy.duration * d.heavy.hit_count * 1.2)
        p_faint = int(d.faint.intensity * d.faint.duration * d.faint.hit_count * 1.2)
        p_crit = int(d.critical.intensity * d.critical.duration * d.critical.hit_count * 1.2)
        self.lbl_perceived_damage.setText(f"경타 {p_light}  <  중타 {p_med}  <  강타 {p_heavy}  <  기절 {p_faint}  <  치명타 {p_crit}")

    def _on_test_row(self, key: str):
        if key == "balance":
            row = self.details.medium
            self.engine.haptics.trigger_pattern_direct("medium", row, "All")
        else:
            row = getattr(self.details, key)
            self.engine.haptics.trigger_pattern_direct(key, row, row.position)

    def _on_reset_row(self, key: str):
        default_d = DetailedHapticConfig()
        if key == "balance":
            self.details.front_balance = default_d.front_balance
            self.details.back_balance = default_d.back_balance
            w = self.row_widgets["balance"]
            w["sld_int"].setValue(self.details.front_balance)
            w["sld_dur"].setValue(self.details.back_balance)
        else:
            def_row = getattr(default_d, key)
            setattr(self.details, key, HapticDetailRow(def_row.intensity, def_row.duration, def_row.hit_count, def_row.position))
            w = self.row_widgets[key]
            w["sld_int"].setValue(def_row.intensity)
            w["sld_dur"].setValue(int(def_row.duration * 100))
            if "sld_hits" in w:
                w["sld_hits"].setValue(def_row.hit_count)
            if "combo_pos" in w:
                p_idx = w["combo_pos"].findData(def_row.position)
                w["combo_pos"].setCurrentIndex(p_idx if p_idx >= 0 else 0)
        self._apply_and_update()

    def _on_ripple_toggled(self, checked: bool):
        self.details.enable_ripple_effect = checked
        self._apply_and_update()

    def _reset_all_defaults(self):
        self.config.haptic_details = DetailedHapticConfig()
        self.details = self.config.haptic_details
        self.chk_ripple.setChecked(self.details.enable_ripple_effect)
        for key, w in self.row_widgets.items():
            self._on_reset_row(key)
        self._apply_and_update()

    def _apply_preset(self, preset_key: str):
        """원클릭 진동 프리셋 적용 ('mild': 순한맛, 'standard': 표준, 'hardcore': 극한)"""
        presets = {
            "mild": {
                "ripple": True,
                "light": (45, 0.14, 1, "All"),
                "medium": (65, 0.22, 1, "All"),
                "heavy": (80, 0.28, 2, "All"),
                "critical": (90, 0.34, 2, "All"),
                "faint": (90, 0.55, 1, "All"),
                "heartbeat": (55, 0.14, 1, "VestFront"),
                "low_hp_loop": (45, 0.40, 1, "All"),
            },
            "standard": {
                "ripple": True,
                "light": (100, 0.26, 1, "All"),
                "medium": (100, 0.42, 2, "All"),
                "heavy": (100, 0.48, 3, "All"),
                "critical": (100, 0.52, 4, "All"),
                "faint": (100, 0.90, 2, "All"),
                "heartbeat": (100, 0.15, 1, "All"),
                "low_hp_loop": (100, 0.42, 1, "All"),
            },
            "hardcore": {
                "ripple": True,
                "light": (100, 0.32, 1, "All"),
                "medium": (100, 0.50, 2, "All"),
                "heavy": (100, 0.62, 4, "All"),
                "critical": (100, 0.75, 5, "All"),
                "faint": (100, 1.15, 3, "All"),
                "heartbeat": (100, 0.13, 1, "All"),
                "low_hp_loop": (100, 0.45, 1, "All"),
            },
        }
        p = presets.get(preset_key)
        if not p:
            return
        self.details.enable_ripple_effect = p["ripple"]
        self.chk_ripple.setChecked(p["ripple"])
        for row_key in ["light", "medium", "heavy", "critical", "faint", "heartbeat", "low_hp_loop"]:
            intensity, dur, hits, pos = p[row_key]
            row_obj = HapticDetailRow(intensity=intensity, duration=dur, hit_count=hits, position=pos)
            setattr(self.details, row_key, row_obj)
            w = self.row_widgets.get(row_key, {})
            if "sld_int" in w:
                w["sld_int"].setValue(intensity)
            if "sld_dur" in w:
                w["sld_dur"].setValue(int(dur * 100))
            if "sld_hits" in w:
                w["sld_hits"].setValue(hits)
            if "combo_pos" in w:
                p_idx = w["combo_pos"].findData(pos)
                w["combo_pos"].setCurrentIndex(p_idx if p_idx >= 0 else 0)
        self._apply_and_update()
        names = {"mild": "🍃 순한맛 (입문)", "standard": "⚖️ 표준 (밸런스)", "hardcore": "🔥 극한 (하드코어)"}
        self.engine.log("STATE", f"⚡ 햅틱 프리셋 적용: [{names.get(preset_key, preset_key)}]")

# =============================================================================
# 📊 6. 배틀 통계 및 대미지 로그 리포트 다이얼로그 (Battle Analytics)
# =============================================================================
class BattleAnalyticsDialog(QDialog):
    """실시간 배틀 누적 대미지, 피격 등급 통계 및 디스코드 리포트 내보내기 창"""

    def __init__(self, analytics: BattleAnalytics, parent=None):
        super().__init__(parent)
        self.analytics = analytics
        self.setWindowTitle("📊 포챔스 배틀 통계 및 대미지 분석 (Battle Analytics)")
        self.setMinimumSize(620, 540)
        self.resize(680, 580)
        self.setStyleSheet("""
            QDialog {
                background-color: #0f121a;
                color: #e2e8f0;
                font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
            }
            QLabel {
                color: #c5d1de;
                font-size: 12px;
            }
            QPushButton {
                background-color: #1f2736;
                color: #e2e8f0;
                border: 1px solid #333f52;
                border-radius: 5px;
                padding: 6px 14px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2b364a;
                border-color: #00e5ff;
            }
            QTextEdit {
                background-color: #0b0d13;
                color: #a4b0be;
                font-family: 'Consolas', monospace;
                border: 1px solid #232a3b;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        self._init_ui()
        self._update_stats()
        
        # 0.5초 주기 실시간 갱신 타이머
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_stats)
        self.refresh_timer.start(500)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        # 상단 타이틀
        title_box = QHBoxLayout()
        lbl_title = QLabel("📊 배틀 세션 실시간 분석 대시보드")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00e5ff;")
        title_box.addWidget(lbl_title)
        title_box.addStretch()
        self.lbl_session_time = QLabel("진행 시간: 00:00")
        self.lbl_session_time.setStyleSheet("font-size: 12px; color: #ffd166; font-weight: bold;")
        title_box.addWidget(self.lbl_session_time)
        layout.addLayout(title_box)

        # 핵심 지표 카드 4분할 그리드
        grid = QGridLayout()
        grid.setSpacing(10)

        # 1) 총 누적 피해량
        self.card_dmg = QFrame()
        self.card_dmg.setStyleSheet("background-color: #1e141a; border: 1px solid #4a2332; border-radius: 8px; padding: 6px;")
        v_dmg = QVBoxLayout(self.card_dmg)
        v_dmg.addWidget(QLabel("💥 총 누적 대미지"))
        self.lbl_total_dmg = QLabel("0.0%")
        self.lbl_total_dmg.setStyleSheet("color: #ff4757; font-size: 20px; font-weight: bold;")
        v_dmg.addWidget(self.lbl_total_dmg)
        grid.addWidget(self.card_dmg, 0, 0)

        # 2) 총 피격 횟수
        self.card_hits = QFrame()
        self.card_hits.setStyleSheet("background-color: #141c26; border: 1px solid #23374d; border-radius: 8px; padding: 6px;")
        v_hits = QVBoxLayout(self.card_hits)
        v_hits.addWidget(QLabel("🎯 총 피격 횟수"))
        self.lbl_total_hits = QLabel("0회")
        self.lbl_total_hits.setStyleSheet("color: #00e5ff; font-size: 20px; font-weight: bold;")
        v_hits.addWidget(self.lbl_total_hits)
        grid.addWidget(self.card_hits, 0, 1)

        # 3) 최대 단일 피해
        self.card_max = QFrame()
        self.card_max.setStyleSheet("background-color: #1d1822; border: 1px solid #422a52; border-radius: 8px; padding: 6px;")
        v_max = QVBoxLayout(self.card_max)
        v_max.addWidget(QLabel("⚡ 최대 피격 대미지"))
        self.lbl_max_hit = QLabel("없음")
        self.lbl_max_hit.setStyleSheet("color: #e056fd; font-size: 16px; font-weight: bold;")
        v_max.addWidget(self.lbl_max_hit)
        grid.addWidget(self.card_max, 1, 0)

        # 4) 최저 생존 HP / 기절 / 교체
        self.card_surv = QFrame()
        self.card_surv.setStyleSheet("background-color: #131d1b; border: 1px solid #1e3d34; border-radius: 8px; padding: 6px;")
        v_surv = QVBoxLayout(self.card_surv)
        v_surv.addWidget(QLabel("🛡️ 최저 생존 / 기절 / 교체"))
        self.lbl_surv_stats = QLabel("HP 100% | 0기절 | 0교체")
        self.lbl_surv_stats.setStyleSheet("color: #2ed573; font-size: 14px; font-weight: bold;")
        v_surv.addWidget(self.lbl_surv_stats)
        grid.addWidget(self.card_surv, 1, 1)

        layout.addLayout(grid)

        # 피격 등급별 상세 바 (경타 / 중타 / 강타 / 치명타)
        grp_breakdown = QFrame()
        grp_breakdown.setStyleSheet("background-color: #141824; border: 1px solid #232a3b; border-radius: 8px; padding: 8px;")
        v_bk = QVBoxLayout(grp_breakdown)
        v_bk.setSpacing(4)
        lbl_bk_title = QLabel("피격 등급별 상세 분포:")
        lbl_bk_title.setStyleSheet("font-weight: bold; color: #8bb4ff; font-size: 11px;")
        v_bk.addWidget(lbl_bk_title)

        h_bk = QHBoxLayout()
        self.lbl_cnt_light = QLabel("🔹 경타: 0회")
        self.lbl_cnt_light.setStyleSheet("color: #70a1ff; font-weight: bold;")
        self.lbl_cnt_medium = QLabel("🔸 중타: 0회")
        self.lbl_cnt_medium.setStyleSheet("color: #eccc68; font-weight: bold;")
        self.lbl_cnt_heavy = QLabel("🔻 강타: 0회")
        self.lbl_cnt_heavy.setStyleSheet("color: #ff7f50; font-weight: bold;")
        self.lbl_cnt_critical = QLabel("⚡ 치명타: 0회")
        self.lbl_cnt_critical.setStyleSheet("color: #ff4757; font-weight: bold;")

        h_bk.addWidget(self.lbl_cnt_light)
        h_bk.addWidget(self.lbl_cnt_medium)
        h_bk.addWidget(self.lbl_cnt_heavy)
        h_bk.addWidget(self.lbl_cnt_critical)
        v_bk.addLayout(h_bk)
        layout.addWidget(grp_breakdown)

        # 상세 이벤트 타임라인
        lbl_events_title = QLabel("⏱️ 실시간 배틀 이벤트 타임라인:")
        lbl_events_title.setStyleSheet("font-weight: bold; color: #8bb4ff; font-size: 11px;")
        layout.addWidget(lbl_events_title)

        self.txt_events = QTextEdit()
        self.txt_events.setReadOnly(True)
        layout.addWidget(self.txt_events, 1)

        # 하단 컨트롤 바
        bottom_box = QHBoxLayout()
        self.lbl_copy_notify = QLabel("")
        self.lbl_copy_notify.setStyleSheet("color: #2ed573; font-weight: bold; font-size: 11px;")
        bottom_box.addWidget(self.lbl_copy_notify)
        bottom_box.addStretch()

        self.btn_reset = QPushButton("🔄 세션 초기화 (새 배틀)")
        self.btn_reset.setStyleSheet("background-color: #3d232a; color: #ff7675; border-color: #572935;")
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        bottom_box.addWidget(self.btn_reset)

        self.btn_copy_report = QPushButton("📋 디스코드 리포트 복사")
        self.btn_copy_report.setStyleSheet("background-color: #1e3d59; color: #00e5ff; border-color: #17b978; font-weight: bold; padding: 6px 16px;")
        self.btn_copy_report.clicked.connect(self._on_copy_report)
        bottom_box.addWidget(self.btn_copy_report)

        btn_close = QPushButton("닫기")
        btn_close.clicked.connect(self.accept)
        bottom_box.addWidget(btn_close)

        layout.addLayout(bottom_box)

    def _update_stats(self):
        s = self.analytics.get_summary_dict()
        self.lbl_session_time.setText(f"진행 시간: {s['elapsed_str']}")
        
        bars = s['total_damage'] / 100.0
        self.lbl_total_dmg.setText(f"{s['total_damage']:.1f}% ({bars:.1f}줄)")
        self.lbl_total_hits.setText(f"{s['total_hits']}회")
        
        if s['max_hit_damage'] > 0:
            self.lbl_max_hit.setText(f"-{s['max_hit_damage']:.1f}% [{s['max_hit_level']}] ({s['max_hit_time']})")
        else:
            self.lbl_max_hit.setText("없음")
            
        surv_str = f"{s['min_hp_survived']:.1f}%" if s['min_hp_survived'] < 100.0 else "100%"
        self.lbl_surv_stats.setText(f"최저 HP {surv_str} | {s['faint_count']}기절 | {s['switches_count']}교체")
        
        c = s['hit_counts']
        self.lbl_cnt_light.setText(f"🔹 경타: {c['light']}회")
        self.lbl_cnt_medium.setText(f"🔸 중타: {c['medium']}회")
        self.lbl_cnt_heavy.setText(f"🔻 강타: {c['heavy']}회")
        self.lbl_cnt_critical.setText(f"⚡ 치명타: {c['critical']}회")

        # 이벤트 타임라인 업데이트 (마지막 40건)
        events = self.analytics.events[-40:]
        html_lines = []
        for ev in events:
            t = ev.get("time", "")
            tp = ev.get("type", "")
            desc = ev.get("desc", "")
            if tp == "DAMAGE":
                col = "#ff4757"
                icon = "💥"
            elif tp == "HEAL":
                col = "#2ed573"
                icon = "💚"
            elif tp == "SWITCH":
                col = "#70a1ff"
                icon = "🔄"
            else:
                col = "#ced6e0"
                icon = "•"
            html_lines.append(f"<span style='color:#747d8c;'>[{t}]</span> {icon} <span style='color:{col}; font-weight:bold;'>[{tp}]</span> <span style='color:#f1f2f6;'>{desc}</span>")
            
        self.txt_events.setHtml("<br>".join(html_lines) if html_lines else "<span style='color:#57606f;'>기록된 배틀 이벤트가 없습니다.</span>")
        self.txt_events.moveCursor(QTextCursor.End)

    def _on_copy_report(self):
        report = self.analytics.generate_clipboard_report()
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(report)
            self.lbl_copy_notify.setText("✅ 리포트가 클립보드에 복사되었습니다! (Ctrl+V)")
            QTimer.singleShot(3000, lambda: self.lbl_copy_notify.setText(""))

    def _on_reset_clicked(self):
        reply = QMessageBox.question(
            self,
            "세션 초기화 확인",
            "현재 배틀 통계와 타임라인 기록을 모두 초기화하고\n새로운 배틀 세션을 시작하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.analytics.reset_session()
            self._update_stats()
            self.lbl_copy_notify.setText("🔄 세션 통계가 초기화되었습니다.")
            QTimer.singleShot(3000, lambda: self.lbl_copy_notify.setText(""))

# =============================================================================
# 🚀 7. 메인 윈도우 대시보드 (자유 도킹 & 탭 결합 가능한 QDockWidget 시스템)
# =============================================================================
class MainWindow(QMainWindow):
    """PokéChamps x bHaptics 메인 대시보드"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PokéChamps x bHaptics Tactile Link (포챔스 햅틱 연동 시스템)")
        self.setMinimumSize(960, 600)
        self.resize(1380, 860)

        self.config = AppConfig.load()
        self.engine = FusionEngine(self.config)
        self.signals = QSignalBridge()
        
        # 정면 및 후면 개별 독립 플로팅 창 생성
        self.overlay_front = FloatingVestOverlay("front", self.config)
        self.overlay_back = FloatingVestOverlay("back", self.config)

        # 4안: 실전 집중 초슬림 컴팩트 모드 컨트롤 바 생성 (기본 숨김, 모드 버튼으로 전환)
        self.compact_hud = CompactHudWindow(self.config)
        self.compact_hud.expand_requested.connect(self._exit_compact_mode)
        self.compact_hud.pause_requested.connect(self._on_toggle_pause)
        self.compact_hud.mode_changed_requested.connect(self._on_compact_mode_changed)
        
        if self.config.show_floating_overlay:
            if self.config.overlay_show_front:
                self.overlay_front.show()
            if self.config.overlay_show_back:
                self.overlay_back.show()

        self.setStyleSheet("""
            QMainWindow {
                background-color: #090d16;
                font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
            }
            QWidget {
                color: #f1f5f9;
                font-size: 12px;
            }
            QGroupBox {
                background-color: rgba(15, 23, 42, 220);
                border: 1px solid rgba(163, 230, 53, 75);
                border-radius: 10px;
                margin-top: 10px;
                font-weight: bold;
                font-size: 12px;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: #a3e635;
            }
            QPushButton {
                background-color: rgba(30, 41, 59, 200);
                border: 1px solid rgba(148, 163, 184, 70);
                border-radius: 8px;
                padding: 5px 12px;
                font-weight: bold;
                color: #e2e8f0;
            }
            QPushButton:hover {
                background-color: rgba(34, 52, 78, 230);
                border-color: #a3e635;
                color: #ffffff;
            }
            QComboBox, QLineEdit {
                background-color: #11192a;
                border: 1px solid rgba(148, 163, 184, 75);
                border-radius: 6px;
                padding: 5px 8px;
                color: #f1f5f9;
            }
            QComboBox:hover, QLineEdit:focus {
                border-color: #a3e635;
            }
            QSlider::groove:horizontal {
                height: 5px;
                background: #1e293b;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a3e635, stop:1 #22d3ee);
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #a3e635;
                border: 1.5px solid #ffffff;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QDockWidget {
                color: #a3e635;
                font-weight: bold;
                font-size: 12px;
            }
            QDockWidget::title {
                background: #101726;
                padding: 8px 12px;
                border-radius: 6px;
                border: 1px solid rgba(163, 230, 53, 60);
                text-align: left;
            }
            QDockWidget::close-button, QDockWidget::float-button {
                background: #1e293b;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 2px;
            }
            QDockWidget::close-button:hover, QDockWidget::float-button:hover {
                background: #a3e635;
            }
            QTabBar::tab {
                background: #101726;
                color: #94a3b8;
                border: 1px solid #1e293b;
                border-bottom: none;
                padding: 7px 16px;
                margin-right: 3px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                font-weight: bold;
                font-size: 11px;
            }
            QTabBar::tab:selected {
                background: #172338;
                color: #a3e635;
                border-bottom: 2px solid #a3e635;
            }
            QTabBar::tab:hover {
                background: #1a253b;
                color: #ffffff;
            }
            QScrollBar:vertical {
                background: #0b101b;
                width: 8px;
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2a3954;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #a3e635;
            }
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # 도킹 시스템 설정 (상하좌우 이동 + 탭 결합 지원)
        self.setDockOptions(
            QMainWindow.AllowNestedDocks |
            QMainWindow.AnimatedDocks |
            QMainWindow.AllowTabbedDocks |
            QMainWindow.GroupedDragging
        )
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)

        self._init_ui()
        self._setup_bindings()
        
        self.render_timer = QTimer(self)
        self.render_timer.timeout.connect(self._on_render_tick)
        self.render_timer.start(16)
        
        self.engine.start()

    def _init_ui(self):
        # 1. 중앙 위젯: 상단 상태바 + 비디오 뷰어 + 체력바 & 툴바
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(10, 8, 10, 8)
        central_layout.setSpacing(8)

        # 상단 전역 툴바 (포챔스 SV 스타일 슬림 바 + 컴팩트 모드 전환)
        self.top_toolbar = QToolBar("시스템 툴바", self)
        self.top_toolbar.setMovable(False)
        self.top_toolbar.setFloatable(False)
        self.top_toolbar.setStyleSheet("""
            QToolBar {
                background-color: #0d1322;
                border-bottom: 1px solid rgba(163, 230, 53, 85);
                padding: 5px 12px;
                spacing: 8px;
            }
        """)
        self.addToolBar(Qt.TopToolBarArea, self.top_toolbar)

        title = QLabel("  POKÉCHAMPS × bHAPTICS  ")
        title.setStyleSheet("""
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #a3e635, stop:1 #22d3ee);
            color: #090d16;
            font-size: 12px;
            font-weight: 900;
            padding: 5px 10px;
            border-radius: 6px;
            margin-right: 6px;
        """)
        self.top_toolbar.addWidget(title)

        dock_btn_css = """
            QPushButton { background-color: rgba(23, 33, 54, 210); color: #94a3b8; font-size: 11px; padding: 5px 11px; border-radius: 999px; border: 1px solid #2b3952; }
            QPushButton:checked { background-color: rgba(163, 230, 53, 35); color: #bef264; border: 1px solid #a3e635; font-weight: bold; }
        """

        # 닫힌 패널을 언제든 다시 켤 수 있는 퀵 토글 버튼들
        self.btn_toggle_haptics_dock = QPushButton("🎽 햅틱 세기")
        self.btn_toggle_haptics_dock.setCheckable(True)
        self.btn_toggle_haptics_dock.setChecked(True)
        self.btn_toggle_haptics_dock.setStyleSheet(dock_btn_css)
        self.btn_toggle_haptics_dock.toggled.connect(self._on_toggle_haptics_dock_btn)
        self.top_toolbar.addWidget(self.btn_toggle_haptics_dock)

        self.btn_toggle_device_dock = QPushButton("🔌 장치/SDK")
        self.btn_toggle_device_dock.setCheckable(True)
        self.btn_toggle_device_dock.setChecked(True)
        self.btn_toggle_device_dock.setStyleSheet(dock_btn_css)
        self.btn_toggle_device_dock.toggled.connect(self._on_toggle_device_dock_btn)
        self.top_toolbar.addWidget(self.btn_toggle_device_dock)

        self.btn_toggle_log_dock = QPushButton("📜 로그")
        self.btn_toggle_log_dock.setCheckable(True)
        self.btn_toggle_log_dock.setChecked(True)
        self.btn_toggle_log_dock.setStyleSheet(dock_btn_css)
        self.btn_toggle_log_dock.toggled.connect(self._on_toggle_log_dock_btn)
        self.top_toolbar.addWidget(self.btn_toggle_log_dock)

        self.btn_reset_layout = QPushButton("🔄 배치 초기화")
        self.btn_reset_layout.setStyleSheet("background-color: rgba(30,41,59,180); color: #fde047; font-size: 11px; padding: 5px 11px; border-radius: 999px; border: 1px solid rgba(250,204,21,80);")
        self.btn_reset_layout.setToolTip("닫힌 패널들을 모두 켜고 깔끔한 2단 탭 레이아웃으로 되돌립니다.")
        self.btn_reset_layout.clicked.connect(self._reset_dock_layout)
        self.top_toolbar.addWidget(self.btn_reset_layout)

        self.btn_analytics = QPushButton("📊 배틀 통계")
        self.btn_analytics.setStyleSheet("background-color: rgba(34,211,238,25); color: #67e8f9; font-size: 11px; padding: 5px 11px; border-radius: 999px; border: 1px solid rgba(34,211,238,110); font-weight: bold;")
        self.btn_analytics.setToolTip("현재 배틀의 누적 피해량, 피격 등급별 통계 및 리포트 복사 창을 엽니다.")
        self.btn_analytics.clicked.connect(self._open_battle_analytics_dialog)
        self.top_toolbar.addWidget(self.btn_analytics)

        # 4안: 실전 집중 컴팩트 모드 전환 버튼
        self.btn_compact_mode = QPushButton("🎯 컴팩트 모드")
        self.btn_compact_mode.setStyleSheet("background-color: rgba(163,230,53,35); color: #bef264; font-size: 11px; padding: 5px 12px; border-radius: 999px; border: 1px solid #a3e635; font-weight: bold;")
        self.btn_compact_mode.setToolTip("큰 대시보드 창을 숨기고 화면 상단에 초슬림 컴팩트 컨트롤 바만 띄워 게임 화면에 집중합니다.")
        self.btn_compact_mode.clicked.connect(self._enter_compact_mode)
        self.top_toolbar.addWidget(self.btn_compact_mode)

        self.btn_fullscreen = QPushButton("⛶ F11")
        self.btn_fullscreen.setStyleSheet("background-color: rgba(30,41,59,180); color: #cbd5e1; font-size: 11px; padding: 5px 10px; border-radius: 999px; border: 1px solid #334155;")
        self.btn_fullscreen.setToolTip("F11 키를 눌러 전체 화면으로 전환하거나 복귀합니다.")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        self.top_toolbar.addWidget(self.btn_fullscreen)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.top_toolbar.addWidget(spacer)

        self.lbl_haptic_badge = QLabel("bHaptics: 연결 대기 중")
        self.lbl_haptic_badge.setStyleSheet("background-color: #2c2015; color: #fbbf24; border: 1px solid rgba(251,191,36,100); padding: 4px 12px; border-radius: 999px; font-weight: bold; font-size: 11px;")
        self.top_toolbar.addWidget(self.lbl_haptic_badge)

        self.lbl_fps = QLabel("FPS: 60")
        self.lbl_fps.setStyleSheet("color: #94a3b8; font-family: Consolas, monospace; font-size: 11px; margin-left: 6px;")
        self.top_toolbar.addWidget(self.lbl_fps)

        # 비디오 및 화면 캡처 글래스 카드 (보더리스 + 라임 글래스 라인)
        grp_video = QFrame()
        grp_video.setObjectName("VideoGlassCard")
        grp_video.setStyleSheet("""
            QFrame#VideoGlassCard {
                background-color: rgba(17, 25, 40, 215);
                border: 1px solid rgba(163, 230, 53, 85);
                border-radius: 12px;
            }
        """)
        grp_video_layout = QVBoxLayout(grp_video)
        grp_video_layout.setContentsMargins(12, 10, 12, 10)
        grp_video_layout.setSpacing(8)

        # 비디오 장치 선택 툴바
        v_dev_layout = QHBoxLayout()
        v_dev_layout.addWidget(QLabel("입력 장치:"))
        self.combo_video_dev = QComboBox()
        self._refresh_device_lists()
        self.combo_video_dev.currentIndexChanged.connect(self._on_video_dev_changed)
        v_dev_layout.addWidget(self.combo_video_dev, 1)

        self.btn_refresh_v_dev = QPushButton("새로고침")
        self.btn_refresh_v_dev.clicked.connect(self._refresh_device_lists)
        v_dev_layout.addWidget(self.btn_refresh_v_dev)

        self.chk_show_floating = QCheckBox("🪟 독립 플로팅 창")
        self.chk_show_floating.setStyleSheet("color: #00e5ff; font-weight: bold;")
        self.chk_show_floating.setChecked(self.config.show_floating_overlay)
        self.chk_show_floating.toggled.connect(self._on_toggle_floating_overlay)
        v_dev_layout.addWidget(self.chk_show_floating)

        self.btn_open_overlay_settings = QPushButton("⚙️ 오버레이 설정")
        self.btn_open_overlay_settings.setStyleSheet("background-color: #1a3344; color: #00e5ff; font-size: 11px; padding: 4px 8px;")
        self.btn_open_overlay_settings.setToolTip("독립 플로팅 오버레이 창의 정면/후면 분리, 크기 및 투명도를 설정합니다.")
        self.btn_open_overlay_settings.clicked.connect(self._open_overlay_settings_dialog)
        v_dev_layout.addWidget(self.btn_open_overlay_settings)

        self.chk_show_debug = QCheckBox("🔍 디버그 모니터")
        self.chk_show_debug.setStyleSheet("color: #ffd166;")
        self.chk_show_debug.setChecked(False)
        self.chk_show_debug.toggled.connect(self._on_toggle_debug)
        v_dev_layout.addWidget(self.chk_show_debug)
        grp_video_layout.addLayout(v_dev_layout)

        # 비디오 뷰어
        self.video_widget = VideoWidget()
        self.video_widget.roi_selected.connect(self._on_roi_selected)
        grp_video_layout.addWidget(self.video_widget, 1)

        # 실시간 비전 디버그 위젯 (기본 숨김)
        self.vision_debug_widget = VisionDebugWidget()
        self.vision_debug_widget.setVisible(False)
        grp_video_layout.addWidget(self.vision_debug_widget)

        # 체력바 및 조작 버튼
        hp_bar_layout = QHBoxLayout()
        lbl_hp_tag = QLabel("아군 잔여 HP:")
        lbl_hp_tag.setStyleSheet("font-weight: bold; color: #c5d1de; border: none; background: transparent;")
        hp_bar_layout.addWidget(lbl_hp_tag)

        self.progress_hp = SlantedHpBarWidget(height=28)
        self.progress_hp.setMinimumWidth(220)
        self.progress_hp.setValue(100)
        self.progress_hp.setFormat("⚔️ HP: 100% (대기)")
        self.progress_hp.setStateColor("lime")
        hp_bar_layout.addWidget(self.progress_hp, 1)

        # 실시간 진동 등급 플래시 배지
        self.lbl_active_haptic_badge = QLabel("🟢 진동 대기")
        self.lbl_active_haptic_badge.setFixedWidth(106)
        self.lbl_active_haptic_badge.setAlignment(Qt.AlignCenter)
        self.lbl_active_haptic_badge.setStyleSheet("background-color: #161c28; color: #7f8fa6; border: 1px solid #2b344b; border-radius: 5px; padding: 4px 6px; font-weight: bold; font-size: 11px;")
        hp_bar_layout.addWidget(self.lbl_active_haptic_badge)

        self.btn_auto_snap = QPushButton("🎯 체력바 자동 스냅")
        self.btn_auto_snap.setStyleSheet("background-color: #6a1b9a; color: #fff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_auto_snap.setToolTip("배틀 화면에서 아군 체력바 카드를 자동 탐색하여 스냅하고 좌표를 즉시 저장합니다.")
        self.btn_auto_snap.clicked.connect(self._on_auto_snap_roi)
        hp_bar_layout.addWidget(self.btn_auto_snap)

        self.btn_pause_detection = QPushButton("⏸️ 체력 감지 일시정지")
        self.btn_pause_detection.setStyleSheet("background-color: #4a3b2c; color: #ffd166; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_pause_detection.clicked.connect(self._on_toggle_pause)
        hp_bar_layout.addWidget(self.btn_pause_detection)

        self.btn_calib_100 = QPushButton("🔄 상태 리셋")
        self.btn_calib_100.setStyleSheet("background-color: #2b5876; color: #e0f2fe; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_calib_100.setToolTip("현재 잠금된 최대 체력(Max HP)과 빨간 체력 루프를 즉시 초기화하여 새 배틀 상태로 리셋합니다.")
        self.btn_calib_100.clicked.connect(self._on_calibrate_100)
        hp_bar_layout.addWidget(self.btn_calib_100)

        grp_video_layout.addLayout(hp_bar_layout)

        # 🎛️ 감지 모드 프로필 선택 바 (초고속 / 균형 6:4 / 고정밀 8.5:1.5)
        mode_bar_layout = QHBoxLayout()
        lbl_mode_title = QLabel("⚡ 감지 프로필:")
        lbl_mode_title.setStyleSheet("font-weight: bold; color: #00e5ff; font-size: 11px;")
        mode_bar_layout.addWidget(lbl_mode_title)

        self.combo_detection_mode = QComboBox()
        self.combo_detection_mode.addItem("⚡ 초고속 반응 모드 (반응 7 : 정확 3) - 0.05초 칼반응 / 연타 극대화", "fast")
        self.combo_detection_mode.addItem("⚖️ 균형 모드 (반응 4 : 정확 6) [권장] - 일치 수치 즉각 발동 & 누락 0% 최적화", "balanced")
        self.combo_detection_mode.addItem("🎯 고정밀 안정 모드 (반응 1.5 : 정확 8.5) - 2프레임 연속 합의 락", "accurate")

        cur_mode = getattr(self.config, "detection_mode", "balanced")
        mode_map = {"fast": 0, "balanced": 1, "accurate": 2}
        self.combo_detection_mode.setCurrentIndex(mode_map.get(cur_mode, 1))
        self.combo_detection_mode.setStyleSheet("""
            QComboBox {
                background-color: #171b26;
                border: 1px solid #0077b6;
                border-radius: 4px;
                padding: 4px 8px;
                color: #e0f2fe;
                font-weight: bold;
                font-size: 11px;
            }
            QComboBox:hover {
                border-color: #00e5ff;
            }
        """)
        self.combo_detection_mode.currentIndexChanged.connect(self._on_detection_mode_changed)
        mode_bar_layout.addWidget(self.combo_detection_mode, 1)

        self.lbl_mode_desc = QLabel()
        self.lbl_mode_desc.setStyleSheet("color: #7dd3fc; font-size: 11px; margin-left: 6px;")
        mode_bar_layout.addWidget(self.lbl_mode_desc)
        self._update_mode_desc_label(cur_mode)

        grp_video_layout.addLayout(mode_bar_layout)
        central_layout.addWidget(grp_video, 1)

        # =====================================================================
        # 🎽 2. 도킹 가능한 햅틱 세기 및 진동 제어 패널 (스크롤 내장형 세부 설정)
        # =====================================================================
        self.dock_haptics = QDockWidget("🎽 햅틱 세기 및 진동 제어", self)
        self.dock_haptics.setObjectName("DockHapticsWidget")
        self.dock_haptics.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.dock_haptics.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)

        haptics_content = QWidget()
        haptics_layout = QVBoxLayout(haptics_content)
        haptics_layout.setContentsMargins(6, 6, 6, 6)
        haptics_layout.setSpacing(6)

        # 상단 마스터 진동 세기 제어 바
        master_bar = QHBoxLayout()
        master_bar.addWidget(QLabel("마스터 진동 세기:"))
        self.slider_master_intensity = QSlider(Qt.Horizontal)
        self.slider_master_intensity.setRange(0, 100)
        self.slider_master_intensity.setValue(self.config.master_intensity)
        self.lbl_master_intensity_val = QLabel(f"{self.config.master_intensity}%")
        self.lbl_master_intensity_val.setFixedWidth(38)
        self.slider_master_intensity.valueChanged.connect(self._on_master_intensity_changed)
        master_bar.addWidget(self.slider_master_intensity, 1)
        master_bar.addWidget(self.lbl_master_intensity_val)
        haptics_layout.addLayout(master_bar)

        # 퀵 테스트 버튼
        btn_quick_test = QPushButton("🎽 bHaptics 진동 테스트")
        btn_quick_test.setStyleSheet("background-color: #0077b6; color: #ffffff; font-size: 11px; font-weight: bold; padding: 6px;")
        btn_quick_test.clicked.connect(self._on_quick_test)
        haptics_layout.addWidget(btn_quick_test)

        # 실시간 내장형 미니 조끼(정면/후면 40채널) LED 프리뷰
        self.mini_vest_preview = MiniVestPreviewWidget()
        haptics_layout.addWidget(self.mini_vest_preview)

        # 스크롤 영역으로 내장된 진동 세부 설정 (9개 패턴)
        self.scroll_haptic_details = QScrollArea()
        self.scroll_haptic_details.setWidgetResizable(True)
        self.scroll_haptic_details.setFrameShape(QFrame.NoFrame)
        self.scroll_haptic_details.setStyleSheet("QScrollArea { background-color: transparent; }")
        self.detail_settings_widget = EmbeddedHapticDetailView(self.config, self.engine)
        self.detail_settings_widget.setStyleSheet("background-color: transparent;")
        self.scroll_haptic_details.setWidget(self.detail_settings_widget)
        haptics_layout.addWidget(self.scroll_haptic_details, 1)

        self.dock_haptics.setWidget(haptics_content)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_haptics)

        # =====================================================================
        # 🔌 3. 독립 분리된 도킹 가능 장치 설정 패널 (bHaptics SDK 설정)
        # =====================================================================
        self.dock_device = QDockWidget("🔌 bHaptics SDK 및 장치 설정", self)
        self.dock_device.setObjectName("DockDeviceWidget")
        self.dock_device.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.dock_device.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)

        device_content = QWidget()
        device_layout = QVBoxLayout(device_content)
        device_layout.setContentsMargins(8, 8, 8, 8)
        device_layout.setSpacing(10)

        app_id_layout = QHBoxLayout()
        app_id_layout.addWidget(QLabel("App ID:"))
        self.edit_app_id = QLineEdit(self.config.sink.app_id)
        self.edit_app_id.setPlaceholderText("bHaptics App ID")
        app_id_layout.addWidget(self.edit_app_id)
        device_layout.addLayout(app_id_layout)

        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(QLabel("API Key:"))
        self.edit_api_key = QLineEdit(self.config.sink.api_key)
        self.edit_api_key.setPlaceholderText("bHaptics API Key")
        self.edit_api_key.setEchoMode(QLineEdit.Password)
        api_key_layout.addWidget(self.edit_api_key)
        device_layout.addLayout(api_key_layout)

        self.btn_save_sdk = QPushButton("💾 bHaptics SDK 설정 적용 및 재연결")
        self.btn_save_sdk.setStyleSheet("background-color: #232738; color: #00e5ff; font-weight: bold; padding: 6px;")
        self.btn_save_sdk.clicked.connect(self._on_save_sdk_config)
        device_layout.addWidget(self.btn_save_sdk)

        # 팁 안내 박스
        tip_box = QGroupBox("💡 팁 및 안내")
        tip_layout = QVBoxLayout(tip_box)
        lbl_tip = QLabel(
            "• 각 패널의 타이틀 바를 드래그하여 원하는 위치에 자유롭게 놓을 수 있습니다.\n"
            "• 패널을 서로의 위로 드래그하면 탭으로 결합되어 하나로 합쳐집니다.\n"
            "• 실수로 닫은 패널은 상단 메뉴의 토글 버튼이나 [🔄 창 배치 초기화]로 복원됩니다."
        )
        lbl_tip.setStyleSheet("color: #8395a7; font-size: 11px; line-height: 1.5;")
        tip_layout.addWidget(lbl_tip)
        device_layout.addWidget(tip_box)
        device_layout.addStretch()

        self.dock_device.setWidget(device_content)

        # =====================================================================
        # 📜 4. 도킹 가능한 이벤트 로그 패널 (QDockWidget)
        # =====================================================================
        self.dock_log = QDockWidget("📜 실시간 시스템 및 피격 이벤트 로그", self)
        self.dock_log.setObjectName("DockLogWidget")
        self.dock_log.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.dock_log.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)

        dock_content = QWidget()
        dock_layout = QVBoxLayout(dock_content)
        dock_layout.setContentsMargins(8, 6, 8, 6)
        dock_layout.setSpacing(6)

        log_filter_layout = QHBoxLayout()
        log_filter_layout.addWidget(QLabel("출력 필터:"))

        self.chk_log_damage = QCheckBox("💥 피격")
        self.chk_log_damage.setChecked(self.config.log_filter.get("DAMAGE", True))
        self.chk_log_damage.toggled.connect(lambda v: self._on_log_filter_toggle("DAMAGE", v))
        log_filter_layout.addWidget(self.chk_log_damage)

        self.chk_log_hp = QCheckBox("💚 HP변동")
        self.chk_log_hp.setChecked(self.config.log_filter.get("HP", True))
        self.chk_log_hp.toggled.connect(lambda v: self._on_log_filter_toggle("HP", v))
        log_filter_layout.addWidget(self.chk_log_hp)

        self.chk_log_state = QCheckBox("⚔️ 배틀")
        self.chk_log_state.setChecked(self.config.log_filter.get("STATE", True))
        self.chk_log_state.toggled.connect(lambda v: self._on_log_filter_toggle("STATE", v))
        log_filter_layout.addWidget(self.chk_log_state)

        self.chk_log_haptic = QCheckBox("🎽 햅틱")
        self.chk_log_haptic.setChecked(self.config.log_filter.get("HAPTIC", True))
        self.chk_log_haptic.toggled.connect(lambda v: self._on_log_filter_toggle("HAPTIC", v))
        log_filter_layout.addWidget(self.chk_log_haptic)

        self.chk_log_system = QCheckBox("⚙️ 시스템")
        self.chk_log_system.setChecked(self.config.log_filter.get("SYSTEM", True))
        self.chk_log_system.toggled.connect(lambda v: self._on_log_filter_toggle("SYSTEM", v))
        log_filter_layout.addWidget(self.chk_log_system)

        dock_layout.addLayout(log_filter_layout)

        # 2. 글자 크기 조절 슬라이더 및 로그 지우기
        log_tools_layout = QHBoxLayout()
        log_tools_layout.addWidget(QLabel("글자 크기:"))
        
        self.slider_log_font = QSlider(Qt.Horizontal)
        self.slider_log_font.setRange(8, 22)
        self.slider_log_font.setValue(self.config.log_font_size)
        self.lbl_log_font_val = QLabel(f"{self.config.log_font_size}pt")
        self.lbl_log_font_val.setFixedWidth(34)
        self.lbl_log_font_val.setStyleSheet("color: #00e5ff; font-family: monospace; font-size: 11px;")
        self.slider_log_font.valueChanged.connect(self._on_log_font_size_changed)
        
        log_tools_layout.addWidget(self.slider_log_font, 1)
        log_tools_layout.addWidget(self.lbl_log_font_val)
        log_tools_layout.addSpacing(10)

        self.btn_clear_log = QPushButton("로그 지우기")
        self.btn_clear_log.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        self.btn_clear_log.clicked.connect(lambda: self.txt_log.clear())
        log_tools_layout.addWidget(self.btn_clear_log)

        dock_layout.addLayout(log_tools_layout)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMinimumHeight(100)
        # 🚀 장시간 플레이 시 메모리 누수 방지 (최근 500줄 로그 유지)
        self.txt_log.document().setMaximumBlockCount(500)
        self._update_log_font_style()
        dock_layout.addWidget(self.txt_log)

        self.dock_log.setWidget(dock_content)

        # 기본 레이아웃 (3안): 우측 상단(햅틱 세기 + 장치 설정 탭 결합), 하단(이벤트 로그) 2단 분할
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.North)
        self.splitDockWidget(self.dock_haptics, self.dock_log, Qt.Vertical)
        self.tabifyDockWidget(self.dock_haptics, self.dock_device)
        self.dock_haptics.raise_()
        self.resizeDocks([self.dock_haptics, self.dock_log], [560, 230], Qt.Vertical)
        self.resizeDocks([self.dock_haptics, self.dock_log], [540, 230], Qt.Vertical)

    def _setup_bindings(self):
        self.engine.vision.on_hp_update = lambda hp, delta, vis, detail: self.signals.hp_updated.emit(hp, delta, vis, detail)
        self.engine.haptics.on_status_change = lambda conn, msg: self.signals.haptic_status.emit(conn, msg)
        self.engine.on_camera_status = lambda conn, msg: self.signals.camera_status.emit(conn, msg)
        self.engine.on_log_event = lambda ts, cat, msg: self.signals.log_message.emit(ts, cat, msg)

        self.signals.hp_updated.connect(self._update_hp_bar)
        self.signals.haptic_status.connect(self._update_haptic_badge)
        self.signals.camera_status.connect(self._on_camera_status_changed)
        self.signals.log_message.connect(self._append_log)

        self.dock_haptics.visibilityChanged.connect(self._on_dock_haptics_visibility_changed)
        self.dock_device.visibilityChanged.connect(self._on_dock_device_visibility_changed)
        self.dock_log.visibilityChanged.connect(self._on_dock_log_visibility_changed)

        # F11 전체 화면 토글 단축키 바인딩
        self.shortcut_f11 = QShortcut(QKeySequence(Qt.Key_F11), self)
        self.shortcut_f11.activated.connect(self._toggle_fullscreen)

    def _toggle_fullscreen(self):
        """F11 전체 화면(Full Screen) 및 일반 창 모드 상호 전환"""
        if self.isFullScreen():
            self.showNormal()
            self.btn_fullscreen.setText("⛶ 전체 화면 (F11)")
            self.engine.log("STATE", "🖥️ 일반 창 모드로 복귀했습니다. (F11: 전체 화면)")
        else:
            self.showFullScreen()
            self.btn_fullscreen.setText("🗗 창 모드 (F11)")
            self.engine.log("STATE", "🖥️ 전체 화면(Full Screen) 모드로 전환되었습니다. (F11 또는 Esc로 해제)")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_F11:
            self._toggle_fullscreen()
        elif event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
            self.btn_fullscreen.setText("⛶ 전체 화면 (F11)")
            self.engine.log("STATE", "🖥️ 일반 창 모드로 복귀했습니다. (F11: 전체 화면)")
        else:
            super().keyPressEvent(event)

    def _on_toggle_haptics_dock_btn(self, checked: bool):
        self.dock_haptics.setVisible(checked)

    def _on_toggle_device_dock_btn(self, checked: bool):
        self.dock_device.setVisible(checked)

    def _on_toggle_log_dock_btn(self, checked: bool):
        self.dock_log.setVisible(checked)

    def _on_dock_haptics_visibility_changed(self, visible: bool):
        self.btn_toggle_haptics_dock.blockSignals(True)
        self.btn_toggle_haptics_dock.setChecked(visible)
        self.btn_toggle_haptics_dock.blockSignals(False)

    def _on_dock_device_visibility_changed(self, visible: bool):
        self.btn_toggle_device_dock.blockSignals(True)
        self.btn_toggle_device_dock.setChecked(visible)
        self.btn_toggle_device_dock.blockSignals(False)

    def _on_dock_log_visibility_changed(self, visible: bool):
        self.btn_toggle_log_dock.blockSignals(True)
        self.btn_toggle_log_dock.setChecked(visible)
        self.btn_toggle_log_dock.blockSignals(False)

    def _reset_dock_layout(self):
        """닫힌 패널을 모두 다시 열고 기본 위치(우측 상단 탭 결합 + 하단 로그 2단 분할)로 초기화"""
        self.dock_haptics.setFloating(False)
        self.dock_device.setFloating(False)
        self.dock_log.setFloating(False)
        self.removeDockWidget(self.dock_haptics)
        self.removeDockWidget(self.dock_device)
        self.removeDockWidget(self.dock_log)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_haptics)
        self.splitDockWidget(self.dock_haptics, self.dock_log, Qt.Vertical)
        self.tabifyDockWidget(self.dock_haptics, self.dock_device)
        self.dock_haptics.show()
        self.dock_device.show()
        self.dock_log.show()
        self.dock_haptics.raise_()
        self.resizeDocks([self.dock_haptics, self.dock_log], [560, 230], Qt.Vertical)
        self.btn_toggle_haptics_dock.setChecked(True)
        self.btn_toggle_device_dock.setChecked(True)
        self.btn_toggle_log_dock.setChecked(True)

    def _open_overlay_settings_dialog(self):
        dlg = FloatingOverlaySettingsDialog(self.config, self.overlay_front, self.overlay_back, self)
        dlg.exec()

    def _open_battle_analytics_dialog(self):
        dlg = BattleAnalyticsDialog(self.engine.analytics, self)
        dlg.exec()

    def _on_camera_status_changed(self, connected: bool, message: str):
        self.video_widget.set_camera_status(connected)
        if not connected:
            self.lbl_fps.setText("⚠️ 신호 단절 | 재연결 시도 중...")

    def _on_master_intensity_changed(self, val: int):
        self.lbl_master_intensity_val.setText(f"{val}%")
        self.engine.haptics.master_intensity = val
        self.config.master_intensity = val
        self.config.save()

    def _on_quick_test(self):
        med = self.config.haptic_details.medium
        self.engine.haptics.trigger_pattern_direct("medium", med, med.position)

    def _on_log_filter_toggle(self, cat: str, checked: bool):
        self.config.log_filter[cat] = checked
        self.config.save()

    def _on_log_font_size_changed(self, val: int):
        self.lbl_log_font_val.setText(f"{val}pt")
        self.config.log_font_size = val
        self.config.save()
        self._update_log_font_style()

    def _update_log_font_style(self):
        size = self.config.log_font_size
        self.txt_log.setStyleSheet(
            f"background-color: #0b0c12; color: #a4b0be; font-family: 'Consolas', monospace; font-size: {size}pt; border: 1px solid #232738; border-radius: 4px;"
        )

    def _on_toggle_floating_overlay(self, checked: bool):
        self.config.show_floating_overlay = checked
        self.config.save()
        if checked:
            if self.config.overlay_show_front:
                self.overlay_front.show()
            if self.config.overlay_show_back:
                self.overlay_back.show()
        else:
            self.overlay_front.hide()
            self.overlay_back.hide()

    def _on_toggle_debug(self, checked: bool):
        self.vision_debug_widget.setVisible(checked)

    def _on_auto_snap_roi(self):
        res = self.engine.auto_snap_roi()
        if res:
            rx, ry, rw, rh = res
            self.btn_auto_snap.setText("✅ 스냅 저장됨!")
            self.btn_auto_snap.setStyleSheet("background-color: #00b894; color: #fff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
            QTimer.singleShot(2000, lambda: (
                self.btn_auto_snap.setText("🎯 체력바 자동 스냅"),
                self.btn_auto_snap.setStyleSheet("background-color: #6a1b9a; color: #fff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
            ))
        else:
            self.btn_auto_snap.setText("⚠️ 배틀 화면 필요")
            self.btn_auto_snap.setStyleSheet("background-color: #d63031; color: #fff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
            QTimer.singleShot(2000, lambda: (
                self.btn_auto_snap.setText("🎯 체력바 자동 스냅"),
                self.btn_auto_snap.setStyleSheet("background-color: #6a1b9a; color: #fff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
            ))

    def _enter_compact_mode(self):
        """3안 전체 대시보드를 숨기고 4안 초슬림 컴팩트 컨트롤 바로 전환"""
        cur_mode = self.combo_detection_mode.currentData() or getattr(self.config, "detection_mode", "balanced")
        self.compact_hud.sync_mode(cur_mode)
        self.compact_hud.hp_bar.setValue(self.progress_hp._value)
        self.compact_hud.hp_bar.setStateColor(self.progress_hp._state_color)
        self.compact_hud.hp_bar.setFormat(self.progress_hp._text)
        self.compact_hud.sync_paused(self.engine.is_paused)
        self.hide()
        self.compact_hud.show()
        self.compact_hud.raise_()

    def _exit_compact_mode(self):
        """4안 컴팩트 컨트롤 바를 숨기고 3안 전체 대시보드로 복귀"""
        self.compact_hud.hide()
        self.show()
        self.raise_()
        self.activateWindow()

    def _on_compact_mode_changed(self, mode: str):
        """컴팩트 HUD에서 감지 프로필을 변경했을 때 메인 UI와 엔진 동기화"""
        if not mode:
            mode = "balanced"
        mode_map = {"fast": 0, "balanced": 1, "accurate": 2}
        self.combo_detection_mode.blockSignals(True)
        self.combo_detection_mode.setCurrentIndex(mode_map.get(mode, 1))
        self.combo_detection_mode.blockSignals(False)
        self.engine.set_detection_mode(mode)
        self._update_mode_desc_label(mode)

    def _on_toggle_pause(self):
        is_paused = self.engine.toggle_pause()
        if is_paused:
            self.btn_pause_detection.setText("▶️ 체력 감지 재개")
            self.btn_pause_detection.setStyleSheet("background-color: #1e7e34; color: #ffffff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
            self.progress_hp.setStateColor("paused")
            self.progress_hp.setFormat("⏸️ 체력 감지 일시정지 중")
        else:
            self.btn_pause_detection.setText("⏸️ 체력 감지 일시정지")
            self.btn_pause_detection.setStyleSheet("background-color: #4a3b2c; color: #ffd166; font-size: 11px; font-weight: bold; padding: 4px 10px;")
            self.progress_hp.setStateColor("lime")
            self.progress_hp.setFormat(f"⚔️ HP: {int(round(self.progress_hp._value))}% (재개)")
        if hasattr(self, "compact_hud") and self.compact_hud:
            self.compact_hud.sync_paused(is_paused)

    def _on_detection_mode_changed(self, index: int):
        mode = self.combo_detection_mode.currentData()
        if not mode:
            mode = "balanced"
        self.engine.set_detection_mode(mode)
        self._update_mode_desc_label(mode)
        if hasattr(self, "compact_hud") and self.compact_hud:
            self.compact_hud.sync_mode(mode)

    def _update_mode_desc_label(self, mode: str):
        descs = {
            "fast": "⚡ 숫자 1프레임 즉시 타격감 (0.05초 칼반응 / 씨기관총 등 다단히트 최적화)",
            "balanced": "⚖️ 최대HP 일치 시 1프레임 즉각 발동 & 교체 2프레임 보호 (누락 0% 권장)",
            "accurate": "🎯 모든 체력 변동을 2프레임 연속 합의 확인 후 발동 (오작동 0% 대회/중계용)"
        }
        self.lbl_mode_desc.setText(descs.get(mode, ""))

    def _on_calibrate_100(self):
        self.engine.reset_battle_state()
        self.btn_calib_100.setText("✅ 리셋 완료")
        QTimer.singleShot(1500, lambda: self.btn_calib_100.setText("🔄 상태 리셋"))

    def _on_roi_selected(self, x: float, y: float, w: float, h: float):
        self.engine.vision.set_roi(x, y, w, h)
        self.config.hp_roi = [x, y, w, h]
        self.config.save()

    def _on_video_dev_changed(self, idx: int):
        dev_idx = self.combo_video_dev.currentData()
        if dev_idx is not None and dev_idx != self.config.video_device_index:
            self.config.video_device_index = dev_idx
            self.config.save()
            self.engine.vision.stop()
            self.engine.vision.device_index = dev_idx
            self.engine.vision.start()

    def _on_save_sdk_config(self):
        self.config.sink.app_id = self.edit_app_id.text().strip()
        self.config.sink.api_key = self.edit_api_key.text().strip()
        self.config.save()
        self.engine.haptics.update_sink_config(self.config.sink)

    def _refresh_device_lists(self):
        self.combo_video_dev.blockSignals(True)
        self.combo_video_dev.clear()
        v_devices = VisionDetector.get_video_devices()
        saved_idx = getattr(self.config, "video_device_index", 0)
        selected_combo_idx = 0
        for i, dev in enumerate(v_devices):
            self.combo_video_dev.addItem(dev['name'], dev['index'])
            if dev['index'] == saved_idx:
                selected_combo_idx = i
        self.combo_video_dev.setCurrentIndex(selected_combo_idx)
        self.combo_video_dev.blockSignals(False)

    def _on_render_tick(self):
        frame = self.engine.vision.get_latest_frame()
        if frame is not None:
            self.video_widget.update_frame(frame)
            fh, fw = frame.shape[:2]
            aspect = fw / float(max(1, fh))
            if abs(aspect - 16/9) < 0.05:
                ratio_str = "16:9"
            elif abs(aspect - 16/10) < 0.05:
                ratio_str = "16:10"
            elif abs(aspect - 21/9) < 0.08:
                ratio_str = "21:9"
            elif abs(aspect - 4/3) < 0.05:
                ratio_str = "4:3"
            else:
                ratio_str = f"{aspect:.2f}:1"
            self.lbl_fps.setText(f"{fw}x{fh} ({ratio_str}) | FPS: 60")
            
        front, back, level = self.engine.haptics.get_current_motor_intensities()
        
        if hasattr(self, "mini_vest_preview") and self.mini_vest_preview.isVisible():
            self.mini_vest_preview.update_data(front, back, level)

        if hasattr(self, "lbl_active_haptic_badge"):
            badge_map = {
                "light": ("🔹 경타 진동", "#1e293b", "#70a1ff", "#3b82f6"),
                "medium": ("🔸 중타 진동", "#2c2416", "#ffd166", "#f59e0b"),
                "heavy": ("🔻 강타 진동!", "#2e1a16", "#ff7f50", "#f97316"),
                "critical": ("⚡ 치명타!", "#3b1219", "#ff4757", "#ef4444"),
                "faint": ("💀 기절 진동!", "#3b0a1e", "#ff2e63", "#ec4899"),
                "heartbeat": ("💓 심장박동", "#2b1422", "#ff6b81", "#f43f5e"),
                "low_hp_loop": ("🚨 빨피 지속", "#2b1216", "#ff4757", "#dc2626"),
            }
            if level in badge_map:
                b_txt, b_bg, b_fg, b_bd = badge_map[level]
                self.lbl_active_haptic_badge.setText(b_txt)
                self.lbl_active_haptic_badge.setStyleSheet(
                    f"background-color: {b_bg}; color: {b_fg}; border: 1px solid {b_bd}; border-radius: 5px; padding: 4px 6px; font-weight: bold; font-size: 11px;"
                )
                if hasattr(self, "compact_hud") and self.compact_hud.isVisible():
                    self.compact_hud.lbl_haptic.setText(b_txt)
                    self.compact_hud.lbl_haptic.setStyleSheet(
                        f"background-color: {b_bg}; color: {b_fg}; border: 1px solid {b_bd}; border-radius: 8px; padding: 4px 6px; font-size: 11px; font-weight: bold;"
                    )
            else:
                self.lbl_active_haptic_badge.setText("🟢 진동 대기")
                self.lbl_active_haptic_badge.setStyleSheet(
                    "background-color: #161c28; color: #7f8fa6; border: 1px solid #2b344b; border-radius: 5px; padding: 4px 6px; font-weight: bold; font-size: 11px;"
                )
                if hasattr(self, "compact_hud") and self.compact_hud.isVisible():
                    self.compact_hud.lbl_haptic.setText("● 대기 중")
                    self.compact_hud.lbl_haptic.setStyleSheet(
                        "background-color: #132030; color: #a3e635; border: 1px solid #2b445e; border-radius: 8px; padding: 4px 6px; font-size: 11px; font-weight: bold;"
                    )

        if self.overlay_front.isVisible():
            self.overlay_front.update_data(front, level)
        if self.overlay_back.isVisible():
            self.overlay_back.update_data(back, level)

        if self.vision_debug_widget.isVisible():
            dbg_data = self.engine.vision.get_debug_data()
            self.vision_debug_widget.update_debug_info(dbg_data)

    def _update_hp_bar(self, hp: float, delta: float, hud_visible: bool, status_detail: str):
        val = int(round(hp))
        self.progress_hp.setValue(val)
        if hasattr(self, "compact_hud") and self.compact_hud:
            self.compact_hud.hp_bar.setValue(val)
        
        if not self.engine.is_paused:
            if not hud_visible:
                fmt = f"⏳ {status_detail}"
                state_col = "idle"
            else:
                fmt = f"⚔️ {status_detail}"
                state_col = "red" if val <= 20 else "lime"

            self.progress_hp.setStateColor(state_col)
            self.progress_hp.setFormat(fmt)
            if hasattr(self, "compact_hud") and self.compact_hud:
                self.compact_hud.hp_bar.setStateColor(state_col)
                self.compact_hud.hp_bar.setFormat(fmt)

    def _update_haptic_badge(self, connected: bool, message: str):
        if connected:
            self.lbl_haptic_badge.setText(f"bHaptics: 연결됨 ({message})")
            self.lbl_haptic_badge.setStyleSheet("background-color: #1b4332; color: #2ecc71; padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;")
        else:
            self.lbl_haptic_badge.setText(f"bHaptics: 미연결 ({message})")
            self.lbl_haptic_badge.setStyleSheet("background-color: #3d2c1d; color: #f39c12; padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;")

    def _append_log(self, timestamp: str, category: str, message: str):
        if not self.config.log_filter.get(category, True):
            return
        
        color_map = {
            "DAMAGE": "#ff4757",
            "HP": "#2ed573",
            "STATE": "#ffa502",
            "HAPTIC": "#1e90ff",
            "SYSTEM": "#a4b0be"
        }
        color = color_map.get(category, "#ced6e0")
        line_html = f"<span style='color:#747d8c;'>[{timestamp}]</span> <span style='color:{color}; font-weight:bold;'>[{category}]</span> <span style='color:#f1f2f6;'>{message}</span>"
        self.txt_log.append(line_html)
        self.txt_log.moveCursor(QTextCursor.End)

    def closeEvent(self, event):
        self.engine.stop()
        if hasattr(self, 'overlay_front') and self.overlay_front:
            self.overlay_front.close()
        if hasattr(self, 'overlay_back') and self.overlay_back:
            self.overlay_back.close()
        if hasattr(self, 'compact_hud') and self.compact_hud:
            self.compact_hud._allow_force_close = True
            self.compact_hud.close()
        self.config.save()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
