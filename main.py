import sys
import os
import time
import math
from typing import List, Dict, Optional, Tuple

import cv2
import numpy as np

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint, QRectF
from PySide6.QtGui import (
    QImage, QPixmap, QPainter, QColor, QPen, QBrush, QFont,
    QLinearGradient, QRadialGradient, QIcon, QTextCursor,
    QKeySequence, QKeyEvent, QShortcut
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox, QSlider,
    QProgressBar, QTextEdit, QGroupBox, QSplitter, QMessageBox, QFrame,
    QDialog, QGridLayout, QScrollArea, QDockWidget, QTabWidget, QSizePolicy
)

from config import AppConfig, HapticSinkConfig, DetailedHapticConfig, HapticDetailRow
from fusion_engine import FusionEngine
from vision_detector import VisionDetector

class QSignalBridge(QObject):
    """엔진 백그라운드 스레드와 Qt UI 메인 스레드 간 비동기 시그널 브릿지"""
    hp_updated = Signal(float, float, bool, str)
    haptic_status = Signal(bool, str)
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
# 🔍 3. 실시간 비전 디버그 모니터 위젯
# =============================================================================
class VisionDebugWidget(QWidget):
    """🔍 실시간 비전 디버그 뷰어 (HP 마스크, OCR 서브영역 크롭, 1D 스캔라인 수치 모니터링)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #12121a; border: 1px solid #2d2d42; border-radius: 6px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)
        
        v1 = QVBoxLayout()
        lbl1 = QLabel("📊 HP 게이지 마스크:")
        lbl1.setStyleSheet("color: #a0a0c0; font-size: 10px; font-weight: bold;")
        v1.addWidget(lbl1)
        self.lbl_hp_mask = QLabel("대기 중...")
        self.lbl_hp_mask.setFixedSize(140, 50)
        self.lbl_hp_mask.setStyleSheet("background-color: #000; border: 1px solid #333; border-radius: 4px;")
        self.lbl_hp_mask.setAlignment(Qt.AlignCenter)
        v1.addWidget(self.lbl_hp_mask)
        layout.addLayout(v1)
        
        v2 = QVBoxLayout()
        lbl2 = QLabel("🔢 OCR 텍스트 크롭:")
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
        self.lbl_metrics = QLabel("스캔라인: 100%\nOCR: 인식 대기\n상태: IDLE")
        self.lbl_metrics.setStyleSheet("color: #00e5ff; font-family: 'Consolas', monospace; font-size: 11px; line-height: 1.3;")
        v3.addWidget(self.lbl_metrics)
        layout.addLayout(v3, 1)

    def update_debug_info(self, debug_data: dict):
        if not debug_data:
            return
            
        mask = debug_data.get("hp_mask")
        if mask is not None and mask.size > 0:
            h, w = mask.shape[:2]
            q_img = QImage(mask.data, w, h, w, QImage.Format_Grayscale8)
            pix = QPixmap.fromImage(q_img).scaled(self.lbl_hp_mask.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_hp_mask.setPixmap(pix)
            
        txt_crop = debug_data.get("text_crop")
        if txt_crop is not None and txt_crop.size > 0:
            h, w, ch = txt_crop.shape
            rgb = cv2.cvtColor(txt_crop, cv2.COLOR_BGR2RGB)
            q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pix = QPixmap.fromImage(q_img).scaled(self.lbl_text_crop.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_text_crop.setPixmap(pix)
            
        raw_val = debug_data.get("scanline_val", 0.0)
        ocr = debug_data.get("ocr_reading")
        ocr_str = f"{ocr[0]}/{ocr[1]} ({ocr[2]:.1f}%)" if ocr else "인식 대기"
        state = debug_data.get("battle_state", "IDLE")
        if debug_data.get("is_paused"):
            state = "PAUSED (일시정지)"
            
        txt = f"1D 스캔라인: {raw_val:.1f}%\nOCR 수치: {ocr_str}\n배틀 상태: {state}"
        self.lbl_metrics.setText(txt)

# =============================================================================
# 🎥 4. 비디오 뷰어 위젯 (순수 게임 화면 및 ROI 선택)
# =============================================================================
class VideoWidget(QWidget):
    """비디오 프레임 렌더링 및 마우스 드래그 ROI 선택기"""
    roi_selected = Signal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setStyleSheet("background-color: #0b0b10; border-radius: 6px;")
        
        self.current_frame: Optional[np.ndarray] = None
        self._is_dragging = False
        self._drag_start = QPoint()
        self._drag_end = QPoint()
        
    def update_frame(self, frame: np.ndarray):
        self.current_frame = frame
        self.update()

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
            
            x1 = min(self._drag_start.x(), self._drag_end.x())
            y1 = min(self._drag_start.y(), self._drag_end.y())
            x2 = max(self._drag_start.x(), self._drag_end.x())
            y2 = max(self._drag_start.y(), self._drag_end.y())
            
            w = max(5, x2 - x1)
            h = max(5, y2 - y1)
            
            norm_x = x1 / float(self.width())
            norm_y = y1 / float(self.height())
            norm_w = w / float(self.width())
            norm_h = h / float(self.height())
            
            self.roi_selected.emit(norm_x, norm_y, norm_w, norm_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        if self.current_frame is not None:
            fh, fw, ch = self.current_frame.shape
            rgb_frame = cv2.cvtColor(self.current_frame, cv2.COLOR_BGR2RGB)
            bytes_per_line = ch * fw
            q_img = QImage(rgb_frame.data, fw, fh, bytes_per_line, QImage.Format_RGB888)
            painter.drawImage(self.rect(), q_img)
        else:
            painter.fillRect(0, 0, w, h, QColor("#0b0b10"))
            painter.setPen(QColor("#4a4a60"))
            painter.setFont(QFont("Segoe UI", 11))
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

        # 1. 상단 안내 및 전부 기본값으로 버튼
        top_bar = QHBoxLayout()
        lbl_info = QLabel("슬라이더 조작 시 즉시 적용됩니다.")
        lbl_info.setStyleSheet("color: #7f8fa6; font-size: 11px;")
        top_bar.addWidget(lbl_info)
        top_bar.addStretch()

        btn_reset_all = QPushButton("전부 기본값으로")
        btn_reset_all.setStyleSheet("background-color: #1e2530; color: #a4b0be; padding: 4px 10px; font-size: 11px; border-radius: 4px; border: 1px solid #333f50;")
        btn_reset_all.clicked.connect(self._reset_all_defaults)
        top_bar.addWidget(btn_reset_all)
        main_layout.addLayout(top_bar)

        # 2. 8개 카드 리스트 (독·화상 제외)
        self.rows_def = [
            ("light", "경타", "체력 1~20% 깎임", True, True, True),
            ("medium", "중타", "21~50% 깎임", True, True, True),
            ("heavy", "강타", "51~80% 깎임", True, True, True),
            ("critical", "치명타", "81~100% 깎임", True, True, True),
            ("faint", "기절", "쓰러졌을 때", True, True, True),
            ("heartbeat", "심장박동", "빨간 체력 60~171 BPM", True, True, False),
            ("low_hp_loop", "빨피 상시", "빨간 체력 지속딜", True, True, False),
            ("balance", "앞뒤 균형", "앞면 / 뒷면 세기", True, True, False)
        ]

        self.row_widgets = {}

        for key, title, desc, has_int, has_dur, has_hits in self.rows_def:
            card = QFrame()
            card.setStyleSheet("""
                QFrame {
                    background-color: #141824;
                    border: 1px solid #232a3b;
                    border-radius: 6px;
                }
            """)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(8, 8, 8, 8)
            card_layout.setSpacing(6)

            # 카드 상단: 제목 + 설명 + 시험/되돌리기 버튼
            card_top = QHBoxLayout()
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("color: #00e5ff; font-size: 12px; font-weight: bold;")
            card_top.addWidget(lbl_title)

            lbl_desc = QLabel(f"({desc})")
            lbl_desc.setStyleSheet("color: #7f8fa6; font-size: 11px;")
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

    def _reset_all_defaults(self):
        self.config.haptic_details = DetailedHapticConfig()
        self.details = self.config.haptic_details
        for key, w in self.row_widgets.items():
            self._on_reset_row(key)
        self._apply_and_update()

# =============================================================================
# 🚀 6. 메인 윈도우 대시보드 (자유 도킹 & 탭 결합 가능한 QDockWidget 시스템)
# =============================================================================
class MainWindow(QMainWindow):
    """PokéChamps x bHaptics 메인 대시보드"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PokéChamps x bHaptics Tactile Link (포챔스 햅틱 연동 시스템)")
        self.setMinimumSize(1080, 720)
        self.resize(1240, 800)

        self.config = AppConfig.load()
        self.engine = FusionEngine(self.config)
        self.signals = QSignalBridge()
        
        # 정면 및 후면 개별 독립 플로팅 창 생성
        self.overlay_front = FloatingVestOverlay("front", self.config)
        self.overlay_back = FloatingVestOverlay("back", self.config)
        
        if self.config.show_floating_overlay:
            if self.config.overlay_show_front:
                self.overlay_front.show()
            if self.config.overlay_show_back:
                self.overlay_back.show()

        self.setStyleSheet("""
            QMainWindow {
                background-color: #0d0e15;
                font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
            }
            QWidget {
                color: #e2e8f0;
                font-size: 12px;
            }
            QGroupBox {
                background-color: #141622;
                border: 1px solid #232738;
                border-radius: 8px;
                margin-top: 10px;
                font-weight: bold;
                font-size: 12px;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                color: #8bb4ff;
            }
            QPushButton {
                background-color: #232738;
                border: 1px solid #333a52;
                border-radius: 5px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2d344b;
                border-color: #00e5ff;
            }
            QComboBox, QLineEdit {
                background-color: #1a1d2c;
                border: 1px solid #2b3147;
                border-radius: 4px;
                padding: 5px 8px;
            }
            QProgressBar {
                background-color: #1a1d2c;
                border: 1px solid #2b3147;
                border-radius: 5px;
                text-align: center;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #00ff88;
                border-radius: 5px;
            }
            QSlider::groove:horizontal {
                height: 5px;
                background: #2b3147;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #00e5ff;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #00e5ff;
                border: 1px solid #ffffff;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QDockWidget {
                color: #8bb4ff;
                font-weight: bold;
                font-size: 12px;
            }
            QDockWidget::title {
                background: #171b26;
                padding: 8px 12px;
                border-radius: 5px;
                border: 1px solid #283042;
                text-align: left;
            }
            QDockWidget::close-button, QDockWidget::float-button {
                background: #232738;
                border: 1px solid #333a52;
                border-radius: 3px;
                padding: 2px;
            }
            QDockWidget::close-button:hover, QDockWidget::float-button:hover {
                background: #00e5ff;
            }
            QTabBar::tab {
                background: #171b26;
                color: #8bb4ff;
                border: 1px solid #283042;
                border-bottom: none;
                padding: 7px 18px;
                margin-right: 2px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QTabBar::tab:selected {
                background: #232738;
                color: #00e5ff;
                border-bottom: 2px solid #00e5ff;
            }
            QTabBar::tab:hover {
                background: #1e2535;
                color: #ffffff;
            }
            QScrollBar:vertical {
                background: #0e111a;
                width: 8px;
                margin: 0px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #28334a;
                min-height: 20px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #00e5ff;
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
        self.setTabPosition(Qt.AllDockWidgetAreas, QTabWidget.South)

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

        # 상단 상태 헤더 바 및 패널 복원 툴바
        header = QHBoxLayout()
        title = QLabel("🎮 PokéChamps x bHaptics Tactile Link")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00e5ff;")
        header.addWidget(title)

        header.addSpacing(15)

        # 닫힌 패널을 언제든 다시 켤 수 있는 퀵 토글 버튼들
        self.btn_toggle_haptics_dock = QPushButton("🎽 햅틱 세기 제어")
        self.btn_toggle_haptics_dock.setCheckable(True)
        self.btn_toggle_haptics_dock.setChecked(True)
        self.btn_toggle_haptics_dock.setStyleSheet("""
            QPushButton { background-color: #1a2233; color: #8bb4ff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: 1px solid #283042; }
            QPushButton:checked { background-color: #0077b6; color: #ffffff; border: 1px solid #0096c7; font-weight: bold; }
        """)
        self.btn_toggle_haptics_dock.toggled.connect(self._on_toggle_haptics_dock_btn)
        header.addWidget(self.btn_toggle_haptics_dock)

        self.btn_toggle_device_dock = QPushButton("🔌 장치 설정")
        self.btn_toggle_device_dock.setCheckable(True)
        self.btn_toggle_device_dock.setChecked(True)
        self.btn_toggle_device_dock.setStyleSheet("""
            QPushButton { background-color: #1a2233; color: #8bb4ff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: 1px solid #283042; }
            QPushButton:checked { background-color: #0077b6; color: #ffffff; border: 1px solid #0096c7; font-weight: bold; }
        """)
        self.btn_toggle_device_dock.toggled.connect(self._on_toggle_device_dock_btn)
        header.addWidget(self.btn_toggle_device_dock)

        self.btn_toggle_log_dock = QPushButton("📜 로그 패널")
        self.btn_toggle_log_dock.setCheckable(True)
        self.btn_toggle_log_dock.setChecked(True)
        self.btn_toggle_log_dock.setStyleSheet("""
            QPushButton { background-color: #1a2233; color: #8bb4ff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: 1px solid #283042; }
            QPushButton:checked { background-color: #0077b6; color: #ffffff; border: 1px solid #0096c7; font-weight: bold; }
        """)
        self.btn_toggle_log_dock.toggled.connect(self._on_toggle_log_dock_btn)
        header.addWidget(self.btn_toggle_log_dock)

        self.btn_reset_layout = QPushButton("🔄 창 배치 초기화")
        self.btn_reset_layout.setStyleSheet("background-color: #232738; color: #ffd166; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: 1px solid #4a3b2c;")
        self.btn_reset_layout.setToolTip("닫힌 패널들을 즉시 모두 다시 켜고 기본 우측 배치로 깔끔하게 되돌립니다.")
        self.btn_reset_layout.clicked.connect(self._reset_dock_layout)
        header.addWidget(self.btn_reset_layout)

        self.btn_fullscreen = QPushButton("⛶ 전체 화면 (F11)")
        self.btn_fullscreen.setStyleSheet("background-color: #1a2233; color: #00e5ff; font-size: 11px; padding: 4px 10px; border-radius: 4px; border: 1px solid #283042;")
        self.btn_fullscreen.setToolTip("F11 키를 눌러 창을 화면 전체로 꽉 채우거나 원래 크기로 복귀합니다. (Esc 키로도 해제 가능)")
        self.btn_fullscreen.clicked.connect(self._toggle_fullscreen)
        header.addWidget(self.btn_fullscreen)

        header.addStretch()

        self.lbl_haptic_badge = QLabel("bHaptics: 연결 대기 중")
        self.lbl_haptic_badge.setStyleSheet("background-color: #3d2c1d; color: #f39c12; padding: 4px 10px; border-radius: 12px; font-weight: bold; font-size: 11px;")
        header.addWidget(self.lbl_haptic_badge)

        self.lbl_fps = QLabel("FPS: 60")
        self.lbl_fps.setStyleSheet("color: #718093; font-family: monospace; font-size: 11px; margin-left: 8px;")
        header.addWidget(self.lbl_fps)
        central_layout.addLayout(header)

        # 비디오 및 화면 캡처 그룹
        grp_video = QGroupBox("🎮 캡처보드 / OBS 화면 입력")
        grp_video_layout = QVBoxLayout(grp_video)
        grp_video_layout.setContentsMargins(10, 10, 10, 8)
        grp_video_layout.setSpacing(6)

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
        hp_bar_layout.addWidget(QLabel("아군 잔여 HP:"))
        self.progress_hp = QProgressBar()
        self.progress_hp.setRange(0, 100)
        self.progress_hp.setValue(100)
        self.progress_hp.setFormat("%v %")
        hp_bar_layout.addWidget(self.progress_hp, 1)

        self.btn_auto_snap = QPushButton("🎯 체력바 자동 스냅")
        self.btn_auto_snap.setStyleSheet("background-color: #6a1b9a; color: #fff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_auto_snap.setToolTip("배틀 화면에서 아군 체력바 카드를 0.1픽셀 단위로 자동 탐색하여 딱 맞게 스냅합니다.")
        self.btn_auto_snap.clicked.connect(self._on_auto_snap_roi)
        hp_bar_layout.addWidget(self.btn_auto_snap)

        self.btn_pause_detection = QPushButton("⏸️ 체력 감지 일시정지")
        self.btn_pause_detection.setStyleSheet("background-color: #4a3b2c; color: #ffd166; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_pause_detection.clicked.connect(self._on_toggle_pause)
        hp_bar_layout.addWidget(self.btn_pause_detection)

        self.btn_calib_100 = QPushButton("🔄 100% 보정")
        self.btn_calib_100.setStyleSheet("background-color: #2b5876; font-size: 11px; padding: 4px 8px;")
        self.btn_calib_100.clicked.connect(self._on_calibrate_100)
        hp_bar_layout.addWidget(self.btn_calib_100)

        grp_video_layout.addLayout(hp_bar_layout)
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

        # 스크롤 영역으로 내장된 진동 세부 설정 (9개 패턴)
        self.scroll_haptic_details = QScrollArea()
        self.scroll_haptic_details.setWidgetResizable(True)
        self.scroll_haptic_details.setFrameShape(QFrame.NoFrame)
        self.detail_settings_widget = EmbeddedHapticDetailView(self.config, self.engine)
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
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_device)

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
        self._update_log_font_style()
        dock_layout.addWidget(self.txt_log)

        self.dock_log.setWidget(dock_content)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_log)

        # 기본 레이아웃: 우측에 햅틱 세기 제어(상), 장치 설정(중), 이벤트 로그(하) 3단 분할
        self.splitDockWidget(self.dock_haptics, self.dock_device, Qt.Vertical)
        self.splitDockWidget(self.dock_device, self.dock_log, Qt.Vertical)

    def _setup_bindings(self):
        self.engine.vision.on_hp_update = lambda hp, delta, vis, detail: self.signals.hp_updated.emit(hp, delta, vis, detail)
        self.engine.haptics.on_status_change = lambda conn, msg: self.signals.haptic_status.emit(conn, msg)
        self.engine.on_log_event = lambda ts, cat, msg: self.signals.log_message.emit(ts, cat, msg)

        self.signals.hp_updated.connect(self._update_hp_bar)
        self.signals.haptic_status.connect(self._update_haptic_badge)
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
        """닫힌 패널을 모두 다시 열고 기본 위치(우측 3단 분할)로 초기화"""
        self.dock_haptics.show()
        self.dock_device.show()
        self.dock_log.show()
        self.dock_haptics.setFloating(False)
        self.dock_device.setFloating(False)
        self.dock_log.setFloating(False)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_haptics)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_device)
        self.addDockWidget(Qt.RightDockWidgetArea, self.dock_log)
        self.splitDockWidget(self.dock_haptics, self.dock_device, Qt.Vertical)
        self.splitDockWidget(self.dock_device, self.dock_log, Qt.Vertical)
        self.btn_toggle_haptics_dock.setChecked(True)
        self.btn_toggle_device_dock.setChecked(True)
        self.btn_toggle_log_dock.setChecked(True)

    def _open_overlay_settings_dialog(self):
        dlg = FloatingOverlaySettingsDialog(self.config, self.overlay_front, self.overlay_back, self)
        dlg.exec()

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
            QMessageBox.information(self, "자동 스냅 성공", f"포챔스 체력바 카드를 자동 스냅했습니다!\n\n좌표: X={rx:.2f}, Y={ry:.2f}, W={rw:.2f}, H={rh:.2f}")
        else:
            QMessageBox.warning(self, "자동 스냅 실패", "화면에서 포챔스 배틀 카드를 찾지 못했습니다.\n배틀 화면이 켜진 상태에서 다시 눌러주세요.")

    def _on_toggle_pause(self):
        is_paused = self.engine.toggle_pause()
        if is_paused:
            self.btn_pause_detection.setText("▶️ 체력 감지 재개")
            self.btn_pause_detection.setStyleSheet("background-color: #1e7e34; color: #ffffff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
            self.progress_hp.setFormat("⏸️ 체력 감지 일시정지 중")
            self.progress_hp.setStyleSheet("QProgressBar::chunk { background-color: #e67e22; border-radius: 5px; }")
        else:
            self.btn_pause_detection.setText("⏸️ 체력 감지 일시정지")
            self.btn_pause_detection.setStyleSheet("background-color: #4a3b2c; color: #ffd166; font-size: 11px; font-weight: bold; padding: 4px 10px;")

    def _on_calibrate_100(self):
        self.engine.vision.calibrate_100_percent()

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
        for dev in v_devices:
            self.combo_video_dev.addItem(dev['name'], dev['index'])
        self.combo_video_dev.blockSignals(False)

    def _on_render_tick(self):
        frame = self.engine.vision.get_latest_frame()
        if frame is not None:
            self.video_widget.update_frame(frame)
            
        front, back, level = self.engine.haptics.get_current_motor_intensities()
        
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
        
        if not self.engine.is_paused:
            if not hud_visible:
                self.progress_hp.setFormat(f"⏳ {status_detail}")
                self.progress_hp.setStyleSheet("QProgressBar::chunk { background-color: #7f8fa6; border-radius: 5px; }")
            else:
                self.progress_hp.setFormat(f"⚔️ {status_detail}")
                if val > 50:
                    self.progress_hp.setStyleSheet("QProgressBar::chunk { background-color: #00ff88; border-radius: 5px; }")
                elif val > 20:
                    self.progress_hp.setStyleSheet("QProgressBar::chunk { background-color: #f1c40f; border-radius: 5px; }")
                else:
                    self.progress_hp.setStyleSheet("QProgressBar::chunk { background-color: #e74c3c; border-radius: 5px; }")

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
