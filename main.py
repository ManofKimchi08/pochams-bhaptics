import sys
import os
import time
import cv2
import numpy as np
from typing import Optional, List, Tuple

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QPoint, QRect, QSize
from PySide6.QtGui import QImage, QPixmap, QColor, QPainter, QPen, QBrush, QFont, QIcon, QMouseEvent
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QSlider, QProgressBar, QTextEdit,
    QGroupBox, QRadioButton, QButtonGroup, QSplitter, QFrame, QMessageBox,
    QLineEdit, QDoubleSpinBox, QScrollArea, QSizePolicy, QCheckBox
)

from config import AppConfig, HapticSinkConfig
from fusion_engine import FusionEngine
from vision_detector import VisionDetector

class BridgeSignals(QObject):
    """멀티스레드와 Qt GUI 간의 통신 시그널"""
    hp_updated = Signal(float, float, bool, str)
    haptic_status = Signal(bool, str)
    log_message = Signal(str, str)
    haptic_triggered = Signal(str, int, int)

class FloatingHapticOverlay(QWidget):
    """
    모든 창/게임/OBS 위에 항상 떠 있는 독립 플로팅 촉각슈트 HUD 오버레이
    마우스 드래그로 자유롭게 이동 가능하며 반투명 글래스 UI 지원
    """
    closed = Signal()

    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.config = config
        
        self.resize(250, 160)
        self.move(self.config.floating_overlay_x, self.config.floating_overlay_y)
        
        self._dragging = False
        self._drag_start_pos = QPoint()
        
        # 실시간 상태
        self.front_intensities: List[float] = [0.0] * 20
        self.back_intensities: List[float] = [0.0] * 20
        self.current_level: str = "none"
        self.status_text: str = "대기 중"
        self.hp_pct: float = 100.0

    def update_data(self, front: List[float], back: List[float], level: str, hp_pct: float, status_text: str):
        self.front_intensities = front
        self.back_intensities = back
        self.current_level = level
        self.hp_pct = hp_pct
        self.status_text = status_text
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        # 1. 반투명 다크 글래스 배경
        painter.setPen(QPen(QColor(60, 65, 95, 220), 1.5))
        painter.setBrush(QBrush(QColor(16, 18, 28, 230)))
        painter.drawRoundedRect(2, 2, w - 4, h - 4, 10, 10)
        
        # 2. 상단 헤더 바 (드래그 핸들)
        painter.setPen(QColor("#00e5ff"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(12, 18, "🎽 bHaptics TactSuit HUD")
        
        # 닫기 버튼 [✕]
        painter.setPen(QColor("#a0a0c0"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(w - 22, 18, "✕")
        
        # 3. 실시간 체력 및 피격 레벨 텍스트
        painter.setFont(QFont("Segoe UI", 8))
        if self.current_level != "none":
            if self.current_level == "critical":
                lvl_color = "#ff1e46"
            elif self.current_level == "heavy":
                lvl_color = "#ff8c00"
            elif self.current_level == "medium":
                lvl_color = "#ffd700"
            else:
                lvl_color = "#00e5ff"
            painter.setPen(QColor(lvl_color))
            painter.drawText(12, 34, w - 24, 14, Qt.AlignLeft, f"⚡ [{self.current_level.upper()}] 피격 발생!")
        else:
            painter.setPen(QColor("#8bb4ff"))
            painter.drawText(12, 34, w - 24, 14, Qt.AlignLeft, f"{self.status_text}")

        # 4. Front & Back 2D 모터 매트릭스 그리기
        grid_y = 48
        grid_h = h - grid_y - 8
        half_w = (w - 20) / 2.0
        
        self._draw_matrix(painter, 10, grid_y, half_w, grid_h, "전면 (Front)", self.front_intensities)
        self._draw_matrix(painter, 10 + half_w, grid_y, half_w, grid_h, "후면 (Back)", self.back_intensities)

    def _draw_matrix(self, painter: QPainter, x: float, y: float, w: float, h: float, label: str, intensities: List[float]):
        painter.setPen(QColor("#a0a0c0"))
        painter.setFont(QFont("Segoe UI", 7, QFont.Bold))
        painter.drawText(int(x), int(y + 8), int(w), 10, Qt.AlignCenter, label)
        
        grid_top = y + 16
        grid_h = h - 18
        cols = 4
        rows = 5
        cell_w = w / cols
        cell_h = grid_h / rows
        r_dot = min(cell_w, cell_h) * 0.32
        
        for idx in range(20):
            r = idx // cols
            c = idx % cols
            cx = x + c * cell_w + cell_w / 2.0
            cy = grid_top + r * cell_h + cell_h / 2.0
            
            intensity = intensities[idx] if idx < len(intensities) else 0.0
            
            if intensity > 0.0:
                if self.current_level == "critical":
                    color = QColor(255, 30, 70, int(160 + 95 * (intensity / 100.0)))
                    glow = QColor(255, 0, 50, 80)
                elif self.current_level == "heavy":
                    color = QColor(255, 140, 0, int(160 + 95 * (intensity / 100.0)))
                    glow = QColor(255, 120, 0, 70)
                elif self.current_level == "medium":
                    color = QColor(255, 215, 0, int(160 + 95 * (intensity / 100.0)))
                    glow = QColor(255, 200, 0, 60)
                else:
                    color = QColor(0, 230, 255, int(160 + 95 * (intensity / 100.0)))
                    glow = QColor(0, 200, 255, 60)
                    
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(r_dot * 1.5), int(r_dot * 1.5))
                
                painter.setPen(QPen(QColor("#fff"), 1.2))
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(r_dot), int(r_dot))
            else:
                painter.setPen(QPen(QColor("#2d2d42"), 1))
                painter.setBrush(QBrush(QColor("#181826")))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(r_dot * 0.85), int(r_dot * 0.85))

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            # 닫기 버튼 영역 클릭 확인
            if event.pos().x() >= self.width() - 28 and event.pos().y() <= 28:
                self.hide()
                self.closed.emit()
                return
                
            self._dragging = True
            self._drag_start_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging and (event.buttons() & Qt.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_start_pos
            self.move(new_pos)
            self.config.floating_overlay_x = new_pos.x()
            self.config.floating_overlay_y = new_pos.y()
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self.config.save()
            event.accept()

class VisionDebugWidget(QWidget):
    """🔍 실시간 비전 디버그 뷰어 (HP 마스크, OCR 서브영역 크롭, 1D 스캔라인 수치 모니터링)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #12121a; border: 1px solid #2d2d42; border-radius: 6px;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)
        
        # 1. HP 활성 마스크 뷰
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
        
        # 2. OCR 텍스트 서브영역 크롭 뷰
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
        
        # 3. 실시간 수치 모니터 텍스트
        v3 = QVBoxLayout()
        lbl3 = QLabel("📈 실시간 비전 진단:")
        lbl3.setStyleSheet("color: #a0a0c0; font-size: 10px; font-weight: bold;")
        v3.addWidget(lbl3)
        self.lbl_metrics = QLabel("스캔라인: 100%\nOCR: 인식 대기\n버퍼 요동: 0.0%\n상태: IDLE")
        self.lbl_metrics.setStyleSheet("color: #00e5ff; font-family: 'Consolas', monospace; font-size: 11px; line-height: 1.3;")
        v3.addWidget(self.lbl_metrics)
        layout.addLayout(v3, 1)

    def update_debug_info(self, debug_data: dict):
        if not debug_data:
            return
            
        # 1. HP 마스크 렌더링
        mask = debug_data.get("hp_mask")
        if mask is not None and mask.size > 0:
            h, w = mask.shape[:2]
            q_img = QImage(mask.data, w, h, w, QImage.Format_Grayscale8)
            pix = QPixmap.fromImage(q_img).scaled(self.lbl_hp_mask.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_hp_mask.setPixmap(pix)
            
        # 2. 텍스트 크롭 렌더링
        txt_crop = debug_data.get("text_crop")
        if txt_crop is not None and txt_crop.size > 0:
            h, w, ch = txt_crop.shape
            rgb = cv2.cvtColor(txt_crop, cv2.COLOR_BGR2RGB)
            q_img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
            pix = QPixmap.fromImage(q_img).scaled(self.lbl_text_crop.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.lbl_text_crop.setPixmap(pix)
            
        # 3. 진단 메트릭 텍스트
        raw_val = debug_data.get("scanline_val", 0.0)
        buf = debug_data.get("buffer", [])
        jitter = (max(buf) - min(buf)) if buf else 0.0
        ocr = debug_data.get("ocr_reading")
        ocr_str = f"{ocr[0]}/{ocr[1]} ({ocr[2]:.1f}%)" if ocr else "인식 대기"
        state = debug_data.get("battle_state", "IDLE")
        if debug_data.get("is_paused"):
            state = "PAUSED (일시정지)"
            
        txt = f"1D 스캔라인: {raw_val:.1f}%\nOCR 수치: {ocr_str}\n버퍼 요동폭: {jitter:.1f}%\n배틀 상태: {state}"
        self.lbl_metrics.setText(txt)

class TactSuitVisualizerWidget(QWidget):
    """우측 패널용 2D TactSuit 실시간 모터 상태 모니터"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(130)
        self.setStyleSheet("background-color: #14141e; border: 1px solid #2d2d3e; border-radius: 6px;")
        
        self.front_intensities: List[float] = [0.0] * 20
        self.back_intensities: List[float] = [0.0] * 20
        self.current_level: str = "none"

    def update_motors(self, front: List[float], back: List[float], level: str):
        self.front_intensities = front
        self.back_intensities = back
        self.current_level = level
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        painter.fillRect(0, 0, w, h, QColor("#14141e"))
        
        half_w = w / 2.0
        self._draw_vest_panel(painter, 10, 8, half_w - 20, h - 16, "전면 (Front Vest)", self.front_intensities)
        self._draw_vest_panel(painter, half_w + 10, 8, half_w - 20, h - 16, "후면 (Back Vest)", self.back_intensities)

    def _draw_vest_panel(self, painter: QPainter, x: float, y: float, w: float, h: float, title: str, intensities: List[float]):
        painter.setPen(QColor("#8bb4ff"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
        painter.drawText(int(x), int(y + 12), int(w), 16, Qt.AlignCenter, title)
        
        grid_top = y + 26
        grid_h = h - 30
        cols = 4
        rows = 5
        cell_w = w / cols
        cell_h = grid_h / rows
        radius = min(cell_w, cell_h) * 0.36
        
        for idx in range(20):
            r = idx // cols
            c = idx % cols
            cx = x + c * cell_w + cell_w / 2.0
            cy = grid_top + r * cell_h + cell_h / 2.0
            
            intensity = intensities[idx] if idx < len(intensities) else 0.0
            
            if intensity > 0.0:
                if self.current_level == "critical":
                    color = QColor(255, 30, 70, int(150 + 105 * (intensity / 100.0)))
                    glow = QColor(255, 0, 50, 80)
                elif self.current_level == "heavy":
                    color = QColor(255, 140, 0, int(150 + 105 * (intensity / 100.0)))
                    glow = QColor(255, 120, 0, 70)
                elif self.current_level == "medium":
                    color = QColor(255, 215, 0, int(150 + 105 * (intensity / 100.0)))
                    glow = QColor(255, 200, 0, 60)
                else:
                    color = QColor(0, 230, 255, int(150 + 105 * (intensity / 100.0)))
                    glow = QColor(0, 200, 255, 60)
                
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(glow))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius * 1.5), int(radius * 1.5))
                
                painter.setPen(QPen(QColor("#ffffff"), 1.5))
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius), int(radius))
            else:
                painter.setPen(QPen(QColor("#2d2d42"), 1))
                painter.setBrush(QBrush(QColor("#1e1e2d")))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(radius * 0.85), int(radius * 0.85))

class VideoWidget(QLabel):
    """ROI 드래그 선택 및 비디오 화면 내 촉각슈트 진동 오버레이를 지원하는 뷰어 위젯"""
    roi_selected = Signal(float, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(480, 270)
        self.setStyleSheet("background-color: #111; border: 2px solid #333; border-radius: 8px;")
        self.setAlignment(Qt.AlignCenter)
        self.setText("비디오 입력을 대기 중입니다...")
        
        self._dragging = False
        self._start_pos = QPoint()
        self._curr_pos = QPoint()
        self._pixmap: Optional[QPixmap] = None
        self._img_rect = QRect()
        
        self.show_overlay: bool = True
        self.front_intensities: List[float] = [0.0] * 20
        self.back_intensities: List[float] = [0.0] * 20
        self.current_level: str = "none"

    def update_frame(self, cv_img: np.ndarray):
        """OpenCV 이미지를 Qt QPixmap으로 변환하여 렌더링"""
        if cv_img is None or cv_img.size == 0:
            return
            
        h, w, ch = cv_img.shape
        bytes_per_line = ch * w
        rgb_img = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        q_img = QImage(rgb_img.data, w, h, bytes_per_line, QImage.Format_RGB888)
        
        scaled = q_img.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._pixmap = QPixmap.fromImage(scaled)
        
        pw, ph = self._pixmap.width(), self._pixmap.height()
        ox = (self.width() - pw) // 2
        oy = (self.height() - ph) // 2
        self._img_rect = QRect(ox, oy, pw, ph)
        
        self.update()

    def update_overlay_motors(self, front: List[float], back: List[float], level: str):
        self.front_intensities = front
        self.back_intensities = back
        self.current_level = level

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        if self._pixmap:
            painter.drawPixmap(self._img_rect.topLeft(), self._pixmap)
            
        if self._dragging:
            pen = QPen(QColor(0, 220, 255), 2, Qt.DashLine)
            painter.setPen(pen)
            rect = QRect(self._start_pos, self._curr_pos).normalized()
            painter.drawRect(rect)
            
        if self.show_overlay and self._pixmap and self._img_rect.width() > 200:
            self._draw_video_haptic_overlay(painter)

    def _draw_video_haptic_overlay(self, painter: QPainter):
        """비디오 우측 상단에 반투명 촉각슈트 모터 HUD 렌더링"""
        hud_w = 165
        hud_h = 105
        hud_x = self._img_rect.right() - hud_w - 12
        hud_y = self._img_rect.top() + 12
        
        painter.setPen(QPen(QColor(60, 60, 90, 180), 1.5))
        painter.setBrush(QBrush(QColor(15, 15, 25, 200)))
        painter.drawRoundedRect(hud_x, hud_y, hud_w, hud_h, 8, 8)
        
        painter.setPen(QColor("#00e5ff"))
        painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
        painter.drawText(hud_x, hud_y + 4, hud_w, 14, Qt.AlignCenter, "🎽 bHaptics TactSuit")
        
        panel_w = (hud_w - 12) / 2.0
        panel_h = hud_h - 24
        
        self._draw_mini_grid(painter, hud_x + 4, hud_y + 18, panel_w, panel_h, "앞 (Front)", self.front_intensities)
        self._draw_mini_grid(painter, hud_x + 8 + panel_w, hud_y + 18, panel_w, panel_h, "뒤 (Back)", self.back_intensities)

    def _draw_mini_grid(self, painter: QPainter, x: float, y: float, w: float, h: float, label: str, intensities: List[float]):
        painter.setPen(QColor("#a0a0c0"))
        painter.setFont(QFont("Segoe UI", 7))
        painter.drawText(int(x), int(y), int(w), 10, Qt.AlignCenter, label)
        
        grid_top = y + 12
        grid_h = h - 12
        cols = 4
        rows = 5
        cell_w = w / cols
        cell_h = grid_h / rows
        r_dot = 3.2
        
        for idx in range(20):
            r = idx // cols
            c = idx % cols
            cx = x + c * cell_w + cell_w / 2.0
            cy = grid_top + r * cell_h + cell_h / 2.0
            
            intensity = intensities[idx] if idx < len(intensities) else 0.0
            
            if intensity > 0.0:
                if self.current_level == "critical":
                    color = QColor(255, 30, 70, int(160 + 95 * (intensity / 100.0)))
                elif self.current_level == "heavy":
                    color = QColor(255, 140, 0, int(160 + 95 * (intensity / 100.0)))
                elif self.current_level == "medium":
                    color = QColor(255, 215, 0, int(160 + 95 * (intensity / 100.0)))
                else:
                    color = QColor(0, 230, 255, int(160 + 95 * (intensity / 100.0)))
                    
                painter.setPen(QPen(QColor("#fff"), 1))
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(r_dot * 1.3), int(r_dot * 1.3))
            else:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor(70, 70, 95, 160)))
                painter.drawEllipse(QPoint(int(cx), int(cy)), int(r_dot), int(r_dot))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._img_rect.contains(event.position().toPoint()):
            self._dragging = True
            self._start_pos = event.position().toPoint()
            self._curr_pos = self._start_pos
            self.update()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self._curr_pos = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._dragging:
            self._dragging = False
            self._curr_pos = event.position().toPoint()
            self.update()
            
            sel_rect = QRect(self._start_pos, self._curr_pos).normalized()
            intersected = sel_rect.intersected(self._img_rect)
            
            if intersected.width() > 10 and intersected.height() > 5 and self._img_rect.width() > 0:
                rx = (intersected.x() - self._img_rect.x()) / float(self._img_rect.width())
                ry = (intersected.y() - self._img_rect.y()) / float(self._img_rect.height())
                rw = intersected.width() / float(self._img_rect.width())
                rh = intersected.height() / float(self._img_rect.height())
                self.roi_selected.emit(rx, ry, rw, rh)

class MainWindow(QMainWindow):
    """포챔스-bHaptics 메인 GUI 창 (독립 플로팅 오버레이 창 지원)"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("포챔스 × bHaptics TactSuit 실시간 연동기 (Official SDK)")
        self.resize(1140, 800)
        self.setMinimumSize(980, 680)
        
        # 설정 및 시그널
        self.config = AppConfig.load()
        self.signals = BridgeSignals()
        self.engine = FusionEngine(self.config)
        
        # 독립 플로팅 데스크톱 오버레이 창 생성
        self.floating_overlay = FloatingHapticOverlay(self.config)
        self.floating_overlay.closed.connect(self._on_floating_overlay_closed)
        
        # UI 스타일시트 적용
        self._apply_dark_theme()
        
        # UI 구성
        self._init_ui()
        self._setup_bindings()
        
        # 프레임 갱신용 타이머 (약 30 FPS)
        self._render_timer = QTimer(self)
        self._render_timer.timeout.connect(self._on_render_tick)
        self._render_timer.start(33)

        # 초기 장치 스캔
        self._refresh_device_lists()
        
        # 엔진 시작
        self.engine.start()
        
        # 플로팅 오버레이 초기 표시 상태 반영
        if self.config.show_floating_overlay:
            self.floating_overlay.show()

    def _apply_dark_theme(self):
        """다크 테마 스타일시트"""
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1a1a24;
                color: #e0e0e0;
                font-family: 'Segoe UI', 'Malgun Gothic', sans-serif;
                font-size: 13px;
            }
            QGroupBox {
                background-color: #222230;
                border: 1px solid #333348;
                border-radius: 8px;
                margin-top: 14px;
                padding-top: 16px;
                font-weight: bold;
                color: #8bb4ff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QPushButton {
                background-color: #2e3856;
                color: #ffffff;
                border: 1px solid #45527a;
                border-radius: 6px;
                padding: 7px 14px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3b4870;
                border-color: #5c6ea4;
            }
            QPushButton:pressed {
                background-color: #242c44;
            }
            QPushButton#btn_engine_toggle {
                background-color: #1e7e34;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton#btn_engine_toggle:hover {
                background-color: #28a745;
            }
            QComboBox, QLineEdit, QDoubleSpinBox {
                background-color: #282838;
                border: 1px solid #444458;
                border-radius: 5px;
                padding: 5px 8px;
                color: #fff;
            }
            QComboBox QAbstractItemView {
                background-color: #282838;
                color: #fff;
                selection-background-color: #43548a;
            }
            QProgressBar {
                background-color: #262636;
                border: 1px solid #3a3a4e;
                border-radius: 6px;
                text-align: center;
                color: #fff;
                font-weight: bold;
            }
            QProgressBar::chunk {
                background-color: #28a745;
                border-radius: 5px;
            }
            QTextEdit {
                background-color: #14141c;
                border: 1px solid #2d2d3e;
                border-radius: 6px;
                color: #a8ffb2;
                font-family: 'Consolas', monospace;
                font-size: 12px;
            }
            QLabel {
                color: #cccccc;
            }
            QCheckBox {
                color: #e0e0e0;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

        # 1. 상단 헤더 바
        header_layout = QHBoxLayout()
        title_label = QLabel("⚡ 포챔스(PokéChamps) × bHaptics TactSuit 실시간 연동")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        # bHaptics 연결 배지
        self.badge_haptics = QLabel("🔴 bHaptics 미연결")
        self.badge_haptics.setStyleSheet("background-color: #4a1d24; color: #ff6b81; padding: 4px 10px; border-radius: 12px; font-weight: bold;")
        header_layout.addWidget(self.badge_haptics)

        # 엔진 시작/정지 버튼
        self.btn_engine_toggle = QPushButton("엔진 재시작")
        self.btn_engine_toggle.setObjectName("btn_engine_toggle")
        self.btn_engine_toggle.clicked.connect(self._on_toggle_engine)
        header_layout.addWidget(self.btn_engine_toggle)

        main_layout.addLayout(header_layout)

        # 2. 본문 분할 (좌측: 비디오/HP인식, 우측: bHaptics SDK 설정/햅틱/로그)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        # === 좌측 패널: 비디오 및 HP 게이지 ===
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 비디오 박스
        grp_video = QGroupBox("🎮 캡처보드 / OBS 화면 인식 (마우스 드래그로 HP 바 지정)")
        grp_video_layout = QVBoxLayout(grp_video)

        # 비디오 장치 선택 & 오버레이 토글 바
        v_dev_layout = QHBoxLayout()
        v_dev_layout.addWidget(QLabel("입력 카메라/캡처:"))
        self.combo_video_dev = QComboBox()
        self.combo_video_dev.currentIndexChanged.connect(self._on_video_dev_changed)
        v_dev_layout.addWidget(self.combo_video_dev, 1)
        
        self.btn_refresh_v_dev = QPushButton("새로고침")
        self.btn_refresh_v_dev.clicked.connect(self._refresh_device_lists)
        v_dev_layout.addWidget(self.btn_refresh_v_dev)
        
        # 🎽 1) 비디오 화면 내부 오버레이 토글
        self.chk_show_overlay = QCheckBox("화면 내부 오버레이")
        self.chk_show_overlay.setChecked(self.config.show_visual_overlay)
        self.chk_show_overlay.toggled.connect(self._on_toggle_overlay)
        v_dev_layout.addWidget(self.chk_show_overlay)
        
        # 🪟 2) 독립 플로팅 데스크톱 오버레이 창 토글 (창 밖으로 꺼내기)
        self.chk_show_floating = QCheckBox("🪟 독립 플로팅 창 켜기")
        self.chk_show_floating.setStyleSheet("color: #00e5ff; font-weight: bold;")
        self.chk_show_floating.setChecked(self.config.show_floating_overlay)
        self.chk_show_floating.toggled.connect(self._on_toggle_floating_overlay)
        v_dev_layout.addWidget(self.chk_show_floating)

        # 🔍 3) 실시간 비전 디버그 모니터 토글
        self.chk_show_debug = QCheckBox("🔍 비전 디버그 모니터")
        self.chk_show_debug.setStyleSheet("color: #ffd166;")
        self.chk_show_debug.setChecked(False)
        self.chk_show_debug.toggled.connect(self._on_toggle_debug)
        v_dev_layout.addWidget(self.chk_show_debug)
        
        grp_video_layout.addLayout(v_dev_layout)

        # 비디오 뷰어
        self.video_widget = VideoWidget()
        self.video_widget.show_overlay = self.config.show_visual_overlay
        self.video_widget.roi_selected.connect(self._on_roi_selected)
        grp_video_layout.addWidget(self.video_widget, 1)

        # 🔍 실시간 비전 디버그 모니터 위젯 (기본 숨김)
        self.vision_debug_widget = VisionDebugWidget()
        self.vision_debug_widget.setVisible(False)
        grp_video_layout.addWidget(self.vision_debug_widget)

        # 실시간 HP 게이지, 자동 스냅, 일시정지 및 100% 보정 버튼
        hp_bar_layout = QHBoxLayout()
        hp_bar_layout.addWidget(QLabel("아군 잔여 HP:"))
        self.progress_hp = QProgressBar()
        self.progress_hp.setRange(0, 100)
        self.progress_hp.setValue(100)
        self.progress_hp.setFormat("%v %")
        hp_bar_layout.addWidget(self.progress_hp, 1)
        
        self.btn_auto_snap = QPushButton("🎯 체력바 자동 스냅")
        self.btn_auto_snap.setStyleSheet("background-color: #6a1b9a; color: #fff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_auto_snap.setToolTip("현재 게임 화면에서 아군 체력바 카드를 0.1픽셀 단위로 자동 탐색하여 딱 맞게 스냅합니다.")
        self.btn_auto_snap.clicked.connect(self._on_auto_snap_roi)
        hp_bar_layout.addWidget(self.btn_auto_snap)

        self.btn_pause_detection = QPushButton("⏸️ 체력 감지 일시정지")
        self.btn_pause_detection.setStyleSheet("background-color: #4a3b2c; color: #ffd166; font-size: 11px; font-weight: bold; padding: 4px 10px;")
        self.btn_pause_detection.setToolTip("배틀 외 상황이나 연출 중 자동 체력 감지 및 피격 진동을 일시정지합니다.")
        self.btn_pause_detection.clicked.connect(self._on_toggle_pause)
        hp_bar_layout.addWidget(self.btn_pause_detection)

        self.btn_calib_100 = QPushButton("🔄 100% 기준 보정")
        self.btn_calib_100.setStyleSheet("background-color: #2b5876; font-size: 11px; padding: 4px 8px;")
        self.btn_calib_100.clicked.connect(self._on_calibrate_100)
        hp_bar_layout.addWidget(self.btn_calib_100)
        
        grp_video_layout.addLayout(hp_bar_layout)

        # ROI 캘리브레이션 팁
        tip_label = QLabel("💡 팁: [🎯 체력바 자동 스냅]을 누르면 화면 내 체력바 카드가 0.1픽셀 단위로 완벽하게 자동 고정됩니다.\n     [🔍 비전 디버그 모니터]를 켜면 마스크 분할 상태와 1D 스캔라인 수치를 실시간으로 진단할 수 있습니다.")
        tip_label.setStyleSheet("color: #a0a0c0; font-size: 11px; line-height: 1.4;")
        grp_video_layout.addWidget(tip_label)

        left_layout.addWidget(grp_video)
        splitter.addWidget(left_widget)

        # === 우측 패널: bHaptics SDK 설정/햅틱 테스트/로그 ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # 1) bHaptics SDK 설정 그룹
        grp_sdk = QGroupBox("🎽 bHaptics SDK 및 장치 설정")
        grp_sdk_layout = QVBoxLayout(grp_sdk)

        # 출력 방식 선택
        kind_layout = QHBoxLayout()
        kind_layout.addWidget(QLabel("출력 방식:"))
        self.combo_sink_kind = QComboBox()
        self.combo_sink_kind.addItem("공식 SDK (bhaptics-python)", "bhaptics")
        self.combo_sink_kind.addItem("레거시 WebSocket (로컬 통신)", "websocket")
        kind_idx = 0 if self.config.sink.kind == "bhaptics" else 1
        self.combo_sink_kind.setCurrentIndex(kind_idx)
        kind_layout.addWidget(self.combo_sink_kind, 1)
        grp_sdk_layout.addLayout(kind_layout)

        # App ID
        app_id_layout = QHBoxLayout()
        app_id_layout.addWidget(QLabel("App ID:"))
        self.edit_app_id = QLineEdit()
        self.edit_app_id.setPlaceholderText("bHaptics Developer Portal App ID")
        self.edit_app_id.setText(self.config.sink.app_id)
        self.edit_app_id.setEchoMode(QLineEdit.Password)
        app_id_layout.addWidget(self.edit_app_id, 1)
        self.btn_toggle_app_id = QPushButton("👁️")
        self.btn_toggle_app_id.setToolTip("App ID 보기 / 숨기기")
        self.btn_toggle_app_id.setFixedWidth(40)
        self.btn_toggle_app_id.clicked.connect(self._toggle_app_id_visibility)
        app_id_layout.addWidget(self.btn_toggle_app_id)
        grp_sdk_layout.addLayout(app_id_layout)

        # API Key
        api_key_layout = QHBoxLayout()
        api_key_layout.addWidget(QLabel("API Key:"))
        self.edit_api_key = QLineEdit()
        self.edit_api_key.setPlaceholderText("bHaptics Developer Portal API Key")
        self.edit_api_key.setText(self.config.sink.api_key)
        self.edit_api_key.setEchoMode(QLineEdit.Password)
        api_key_layout.addWidget(self.edit_api_key, 1)
        self.btn_toggle_api_key = QPushButton("👁️")
        self.btn_toggle_api_key.setToolTip("API Key 보기 / 숨기기")
        self.btn_toggle_api_key.setFixedWidth(40)
        self.btn_toggle_api_key.clicked.connect(self._toggle_api_key_visibility)
        api_key_layout.addWidget(self.btn_toggle_api_key)
        grp_sdk_layout.addLayout(api_key_layout)

        # 모터 수 및 피격 부위
        motor_layout = QHBoxLayout()
        motor_layout.addWidget(QLabel("모터 수:"))
        self.combo_motor_count = QComboBox()
        self.combo_motor_count.addItem("32개 (TactSuit Pro / X16)", 32)
        self.combo_motor_count.addItem("40개 (TactSuit X40)", 40)
        m_idx = 0 if self.config.sink.motor_count == 32 else 1
        self.combo_motor_count.setCurrentIndex(m_idx)
        motor_layout.addWidget(self.combo_motor_count, 1)

        motor_layout.addWidget(QLabel("피격 위치:"))
        self.combo_haptic_pos = QComboBox()
        self.combo_haptic_pos.addItems(["앞면 (VestFront)", "뒷면 (VestBack)", "앞+뒤 전체 (All)"])
        pos_map = {"VestFront": 0, "VestBack": 1, "All": 2}
        self.combo_haptic_pos.setCurrentIndex(pos_map.get(self.config.haptic_position, 0))
        motor_layout.addWidget(self.combo_haptic_pos, 1)
        grp_sdk_layout.addLayout(motor_layout)

        # 전면/후면 게인
        gain_layout = QHBoxLayout()
        gain_layout.addWidget(QLabel("전면 게인:"))
        self.spin_front_gain = QDoubleSpinBox()
        self.spin_front_gain.setRange(0.0, 2.0)
        self.spin_front_gain.setSingleStep(0.1)
        self.spin_front_gain.setValue(self.config.sink.front_gain)
        gain_layout.addWidget(self.spin_front_gain)

        gain_layout.addWidget(QLabel("후면 게인:"))
        self.spin_back_gain = QDoubleSpinBox()
        self.spin_back_gain.setRange(0.0, 2.0)
        self.spin_back_gain.setSingleStep(0.1)
        self.spin_back_gain.setValue(self.config.sink.back_gain)
        gain_layout.addWidget(self.spin_back_gain)

        self.btn_save_sink = QPushButton("💾 bHaptics 설정 저장 및 재연결")
        self.btn_save_sink.setStyleSheet("background-color: #3b5998; font-weight: bold;")
        self.btn_save_sink.clicked.connect(self._on_save_sink_settings)
        gain_layout.addWidget(self.btn_save_sink)
        grp_sdk_layout.addLayout(gain_layout)

        right_layout.addWidget(grp_sdk)

        # 2) 햅틱 테스트 및 2D 모터 모니터 패널 그룹
        grp_test = QGroupBox("🎯 촉각슈트 진동 수동 테스트 & 실시간 모터 모니터")
        grp_test_layout = QVBoxLayout(grp_test)

        btn_row = QHBoxLayout()
        self.btn_test_light = QPushButton("약공격 (20%)")
        self.btn_test_light.clicked.connect(lambda: self.engine.haptics.trigger_damage("light", position_mode=self.config.haptic_position))
        
        self.btn_test_med = QPushButton("중공격 (50%)")
        self.btn_test_med.clicked.connect(lambda: self.engine.haptics.trigger_damage("medium", position_mode=self.config.haptic_position))
        
        self.btn_test_heavy = QPushButton("강공격 (80%)")
        self.btn_test_heavy.clicked.connect(lambda: self.engine.haptics.trigger_damage("heavy", position_mode=self.config.haptic_position))
        
        self.btn_test_crit = QPushButton("치명타 (KO)")
        self.btn_test_crit.setStyleSheet("background-color: #8b263e; font-weight: bold;")
        self.btn_test_crit.clicked.connect(lambda: self.engine.haptics.trigger_damage("critical", position_mode=self.config.haptic_position))

        btn_row.addWidget(self.btn_test_light)
        btn_row.addWidget(self.btn_test_med)
        btn_row.addWidget(self.btn_test_heavy)
        btn_row.addWidget(self.btn_test_crit)
        grp_test_layout.addLayout(btn_row)

        # 2D 촉각슈트 모터 모니터 위젯
        self.haptic_visualizer = TactSuitVisualizerWidget()
        grp_test_layout.addWidget(self.haptic_visualizer)

        right_layout.addWidget(grp_test)

        # 3) 실시간 이벤트 로그 그룹
        grp_log = QGroupBox("📋 실시간 감지 및 진동 로그")
        grp_log_layout = QVBoxLayout(grp_log)
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        grp_log_layout.addWidget(self.txt_log)
        right_layout.addWidget(grp_log, 1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        main_layout.addWidget(splitter, 1)

        # 하단 버튼
        bottom_layout = QHBoxLayout()
        self.btn_save_config = QPushButton("💾 전체 설정 저장")
        self.btn_save_config.clicked.connect(self._on_save_all_config)
        bottom_layout.addWidget(self.btn_save_config)
        
        self.btn_clear_log = QPushButton("로그 지우기")
        self.btn_clear_log.clicked.connect(lambda: self.txt_log.clear())
        bottom_layout.addWidget(self.btn_clear_log)
        bottom_layout.addStretch()

        main_layout.addLayout(bottom_layout)

    def _setup_bindings(self):
        """엔진 콜백과 Qt 시그널 연결"""
        self.engine.vision.on_hp_update = lambda hp, delta, vis, detail: self.signals.hp_updated.emit(hp, delta, vis, detail)
        self.engine.haptics.on_status_change = lambda conn, msg: self.signals.haptic_status.emit(conn, msg)
        self.engine.on_log_event = lambda ts, msg: self.signals.log_message.emit(ts, msg)

        # 시그널 핸들러 연결
        self.signals.hp_updated.connect(self._update_hp_bar)
        self.signals.haptic_status.connect(self._update_haptic_badge)
        self.signals.log_message.connect(self._append_log)

    def _on_toggle_overlay(self, checked: bool):
        """비디오 화면 내부 오버레이 On/Off 토글"""
        self.config.show_visual_overlay = checked
        self.video_widget.show_overlay = checked
        self.video_widget.update()
        state_txt = "활성화" if checked else "비활성화"
        self._append_log(time.strftime("%H:%M:%S"), f"[UI] 비디오 내부 진동 오버레이 {state_txt}")

    def _on_toggle_floating_overlay(self, checked: bool):
        """독립 플로팅 오버레이 창 On/Off 토글"""
        self.config.show_floating_overlay = checked
        self.config.save()
        if checked:
            self.floating_overlay.show()
            self._append_log(time.strftime("%H:%M:%S"), "[UI] 🪟 독립 플로팅 진동 오버레이 창 활성화 (원하는 화면 위치로 드래그하세요)")
        else:
            self.floating_overlay.hide()
            self._append_log(time.strftime("%H:%M:%S"), "[UI] 🪟 독립 플로팅 진동 오버레이 창 비활성화")

    def _on_floating_overlay_closed(self):
        """플로팅 창의 ✕ 버튼을 눌러 닫았을 때 체크박스 동기화"""
        self.chk_show_floating.setChecked(False)

    def _on_calibrate_100(self):
        """현재 체력바 상태를 100% 기준으로 보정"""
        self.engine.vision.calibrate_100_percent()
        self._append_log(time.strftime("%H:%M:%S"), "[Vision] 현재 HP 바 너비를 100% 만피 기준으로 보정 완료!")

    def _on_toggle_debug(self, checked: bool):
        """실시간 비전 디버그 모니터 뷰어 표시 토글"""
        self.vision_debug_widget.setVisible(checked)
        if checked:
            self._append_log(time.strftime("%H:%M:%S"), "[UI] 🔍 실시간 비전 디버그 모니터 활성화 (마스크 및 스캔라인 진단)")

    def _on_auto_snap_roi(self):
        """현재 게임 화면에서 아군 체력바 카드를 자동 감지하여 ROI 스냅"""
        res = self.engine.auto_snap_roi()
        if res:
            rx, ry, rw, rh = res
            self._append_log(time.strftime("%H:%M:%S"), f"[ROI] 🎯 체력바 카드 자동 스냅 완료: X={rx:.2f}, Y={ry:.2f}, W={rw:.2f}, H={rh:.2f}")
            QMessageBox.information(self, "자동 스냅 성공", f"포챔스 아군 체력바 카드를 성공적으로 자동 감지했습니다!\n\n좌표: X={rx:.2f}, Y={ry:.2f}, W={rw:.2f}, H={rh:.2f}")
        else:
            self._append_log(time.strftime("%H:%M:%S"), "[ROI] ⚠️ 체력바 카드를 찾지 못했습니다. 배틀 화면이 켜진 상태에서 다시 시도하세요.")
            QMessageBox.warning(self, "자동 스냅 실패", "현재 화면에서 포챔스 배틀 카드를 찾지 못했습니다.\n배틀 화면이 켜진 상태에서 다시 눌러주세요.")

    def _on_toggle_pause(self):
        """수동 체력 감지 일시정지 / 재개 토글"""
        is_paused = self.engine.toggle_pause()
        if is_paused:
            self.btn_pause_detection.setText("▶️ 체력 감지 재개")
            self.btn_pause_detection.setStyleSheet("background-color: #1e7e34; color: #ffffff; font-size: 11px; font-weight: bold; padding: 4px 10px;")
            self.progress_hp.setFormat("⏸️ 체력 감지 일시정지 중")
            self.progress_hp.setStyleSheet("QProgressBar::chunk { background-color: #e67e22; border-radius: 5px; }")
        else:
            self.btn_pause_detection.setText("⏸️ 체력 감지 일시정지")
            self.btn_pause_detection.setStyleSheet("background-color: #4a3b2c; color: #ffd166; font-size: 11px; font-weight: bold; padding: 4px 10px;")

    def _refresh_device_lists(self):
        """비디오 장치 목록 갱신"""
        self.combo_video_dev.blockSignals(True)
        self.combo_video_dev.clear()
        v_devices = VisionDetector.get_video_devices()
        for dev in v_devices:
            self.combo_video_dev.addItem(dev['name'], dev['index'])
        self.combo_video_dev.blockSignals(False)

    def _on_render_tick(self):
        """비디오 프레임 및 햅틱 모터 애니메이션 렌더링 갱신"""
        frame = self.engine.vision.get_latest_frame()
        if frame is not None:
            self.video_widget.update_frame(frame)
            
        # 실시간 모터 상태 가져오기
        front, back, level = self.engine.haptics.get_current_motor_intensities()
        
        # 1. 우측 패널 모니터 갱신
        self.haptic_visualizer.update_motors(front, back, level)
        
        # 2. 비디오 내부 오버레이 갱신
        self.video_widget.update_overlay_motors(front, back, level)
        
        # 3. 독립 플로팅 오버레이 창 갱신
        if self.floating_overlay.isVisible():
            status_txt = self.progress_hp.text()
            self.floating_overlay.update_data(front, back, level, self.engine.vision.current_hp_pct, status_txt)

        # 4. 실시간 비전 디버그 모니터 갱신
        if self.vision_debug_widget.isVisible():
            dbg_data = self.engine.vision.get_debug_data()
            self.vision_debug_widget.update_debug_info(dbg_data)

    def _update_hp_bar(self, hp: float, delta: float, hud_visible: bool, status_detail: str):
        val = int(round(hp))
        self.progress_hp.setValue(val)
        
        if not hud_visible:
            self.progress_hp.setFormat(f"🎬 연출 중 ({val}% 고정)")
            color = "#e67e22"
        else:
            self.progress_hp.setFormat(f"{status_detail}")
            if val > 50:
                color = "#28a745"
            elif val > 20:
                color = "#ffc107"
            else:
                color = "#dc3545"

        self.progress_hp.setStyleSheet(f"""
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 5px;
            }}
        """)

    def _update_haptic_badge(self, connected: bool, message: str):
        if connected:
            self.badge_haptics.setText(f"🟢 {message}")
            self.badge_haptics.setStyleSheet("background-color: #194d2e; color: #55efc4; padding: 4px 10px; border-radius: 12px; font-weight: bold;")
        else:
            self.badge_haptics.setText(f"🔴 {message}")
            self.badge_haptics.setStyleSheet("background-color: #4a1d24; color: #ff6b81; padding: 4px 10px; border-radius: 12px; font-weight: bold;")

    def _append_log(self, timestamp: str, message: str):
        self.txt_log.append(f"[{timestamp}] {message}")
        sb = self.txt_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _toggle_app_id_visibility(self):
        if self.edit_app_id.echoMode() == QLineEdit.Password:
            self.edit_app_id.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_app_id.setText("🔒")
        else:
            self.edit_app_id.setEchoMode(QLineEdit.Password)
            self.btn_toggle_app_id.setText("👁️")

    def _toggle_api_key_visibility(self):
        if self.edit_api_key.echoMode() == QLineEdit.Password:
            self.edit_api_key.setEchoMode(QLineEdit.Normal)
            self.btn_toggle_api_key.setText("🔒")
        else:
            self.edit_api_key.setEchoMode(QLineEdit.Password)
            self.btn_toggle_api_key.setText("👁️")

    def _on_save_sink_settings(self):
        """bHaptics SDK 설정 저장 및 햅틱 재연결"""
        new_sink = HapticSinkConfig(
            kind=self.combo_sink_kind.currentData(),
            app_id=self.edit_app_id.text().strip(),
            api_key=self.edit_api_key.text().strip(),
            motor_count=self.combo_motor_count.currentData(),
            front_gain=self.spin_front_gain.value(),
            back_gain=self.spin_back_gain.value()
        )
        
        pos_map = {0: "VestFront", 1: "VestBack", 2: "All"}
        self.config.haptic_position = pos_map.get(self.combo_haptic_pos.currentIndex(), "VestFront")
        self.config.sink = new_sink
        self.config.save()
        
        self.engine.haptics.update_sink_config(new_sink)
        self._append_log(time.strftime("%H:%M:%S"), f"[Config] bHaptics SDK 설정 저장 및 재연결 요청 ({new_sink.kind} 모드)")
        QMessageBox.information(self, "저장 완료", "bHaptics SDK 설정이 저장되고 재연결되었습니다.")

    def _on_save_all_config(self):
        self._on_save_sink_settings()
        self.config.save()
        QMessageBox.information(self, "저장 완료", "모든 설정이 성공적으로 저장되었습니다.")

    def _on_toggle_engine(self):
        self.engine.stop()
        time.sleep(0.3)
        self.engine.start()
        self._append_log(time.strftime("%H:%M:%S"), "[System] 연동 엔진을 재시작했습니다.")

    def _on_video_dev_changed(self, idx: int):
        dev_idx = self.combo_video_dev.itemData(idx)
        if dev_idx is not None and dev_idx != self.config.video_device_index:
            self.config.video_device_index = dev_idx
            self.config.save()
            self._append_log(time.strftime("%H:%M:%S"), f"[Video] 입력 장치 변경: {dev_idx}")
            self.engine.vision.stop()
            self.engine.vision.device_index = dev_idx
            self.engine.vision.start()

    def _on_roi_selected(self, rx: float, ry: float, rw: float, rh: float):
        self.config.hp_roi = [rx, ry, rw, rh]
        self.config.save()
        self.engine.vision.set_roi(rx, ry, rw, rh)
        self._append_log(time.strftime("%H:%M:%S"), f"[ROI] 아군 HP 바 영역 갱신: X={rx:.2f}, Y={ry:.2f}, W={rw:.2f}, H={rh:.2f}")

    def closeEvent(self, event):
        self.floating_overlay.close()
        self.engine.stop()
        event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
