from typing import Optional, Tuple

from PySide6.QtCore import Qt, Signal, QPoint
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox, QFrame

from config import AppConfig
from ui.widgets import SlantedHpBarWidget


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
        self._last_badge_level: Optional[str] = None

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

        self.lbl_brand = QLabel("POKE\nHAPTIC")
        self.lbl_brand.setStyleSheet("color: #a3e635; font-weight: 900; font-size: 11px; border: none; background: transparent;")
        self.lbl_brand.setToolTip("드래그하여 원하는 화면 위치로 이동할 수 있습니다.")
        row.addWidget(self.lbl_brand)

        self.hp_bar = SlantedHpBarWidget(height=24)
        self.hp_bar.setMinimumWidth(260)
        row.addWidget(self.hp_bar, 1)

        self.lbl_haptic = QLabel("● 대기 중")
        self.lbl_haptic.setFixedWidth(104)
        self.lbl_haptic.setAlignment(Qt.AlignCenter)
        self.lbl_haptic.setStyleSheet("background-color: #132030; color: #a3e635; border: 1px solid #2b445e; border-radius: 8px; padding: 4px 6px; font-size: 11px; font-weight: bold;")
        row.addWidget(self.lbl_haptic)

        self.combo_mode = QComboBox()
        self.combo_mode.addItem("⚡ 초고속", "fast")
        self.combo_mode.addItem("⚖️ 균형", "balanced")
        self.combo_mode.addItem("🎯 고정밀", "accurate")
        cur_mode = getattr(self.config, "detection_mode", "balanced")
        mode_map = {"fast": 0, "balanced": 1, "accurate": 2}
        self.combo_mode.setCurrentIndex(mode_map.get(cur_mode, 1))
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        row.addWidget(self.combo_mode)

        self.btn_pause = QPushButton("⏸ 일시정지")
        self.btn_pause.clicked.connect(self.pause_requested.emit)
        row.addWidget(self.btn_pause)

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

    def sync_hp(self, val: float, state_color: str, fmt: str):
        self.hp_bar.setValue(val)
        self.hp_bar.setStateColor(state_color)
        self.hp_bar.setFormat(fmt)

    def update_haptic_badge(self, level: str, badge_info: Optional[Tuple[str, str, str, str]]):
        if level == self._last_badge_level:
            return
        self._last_badge_level = level
        if badge_info is not None:
            b_txt, b_bg, b_fg, b_bd = badge_info
            self.lbl_haptic.setText(b_txt)
            self.lbl_haptic.setStyleSheet(
                f"background-color: {b_bg}; color: {b_fg}; border: 1px solid {b_bd}; border-radius: 8px; padding: 4px 6px; font-size: 11px; font-weight: bold;"
            )
        else:
            self.lbl_haptic.setText("● 대기 중")
            self.lbl_haptic.setStyleSheet(
                "background-color: #132030; color: #a3e635; border: 1px solid #2b445e; border-radius: 8px; padding: 4px 6px; font-size: 11px; font-weight: bold;"
            )

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
