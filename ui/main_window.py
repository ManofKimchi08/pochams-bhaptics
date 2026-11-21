import time
import html
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor, QKeySequence, QKeyEvent, QShortcut
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox, QSlider,
    QTextEdit, QGroupBox, QFrame, QScrollArea, QDockWidget,
    QTabWidget, QSizePolicy, QToolBar
)

from config import AppConfig
from fusion_engine import FusionEngine
from vision_detector import VisionDetector
from ui.widgets import (
    QSignalBridge, FloatingOverlaySettingsDialog, FloatingVestOverlay,
    MiniVestPreviewWidget, SlantedHpBarWidget, VisionDebugWidget, VideoWidget
)
from ui.compact_hud import CompactHudWindow
from ui.haptic_panel import EmbeddedHapticDetailView
from ui.analytics_dialog import BattleAnalyticsDialog


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

        self._in_compact_mode: bool = False
        self._last_rendered_frame = None
        self._last_fps_label_update: float = 0.0
        self._last_haptic_badge_level: Optional[str] = None

        self._ui_save_timer = QTimer(self)
        self._ui_save_timer.setSingleShot(True)
        self._ui_save_timer.setInterval(250)
        self._ui_save_timer.timeout.connect(self.config.save)

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
        central = QWidget()
        self.setCentralWidget(central)
        central_layout = QVBoxLayout(central)
        central_layout.setContentsMargins(10, 8, 10, 8)
        central_layout.setSpacing(8)

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

        self.lbl_fps = QLabel("FPS: --")
        self.lbl_fps.setStyleSheet("color: #94a3b8; font-family: Consolas, monospace; font-size: 11px; margin-left: 6px;")
        self.top_toolbar.addWidget(self.lbl_fps)

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

        self.video_widget = VideoWidget()
        self.video_widget.roi_selected.connect(self._on_roi_selected)
        grp_video_layout.addWidget(self.video_widget, 1)

        self.vision_debug_widget = VisionDebugWidget()
        self.vision_debug_widget.setVisible(False)
        grp_video_layout.addWidget(self.vision_debug_widget)

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

        # 2. 도킹 가능한 햅틱 세기 및 진동 제어 패널
        self.dock_haptics = QDockWidget("🎽 햅틱 세기 및 진동 제어", self)
        self.dock_haptics.setObjectName("DockHapticsWidget")
        self.dock_haptics.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.dock_haptics.setFeatures(QDockWidget.DockWidgetMovable | QDockWidget.DockWidgetFloatable | QDockWidget.DockWidgetClosable)

        haptics_content = QWidget()
        haptics_layout = QVBoxLayout(haptics_content)
        haptics_layout.setContentsMargins(6, 6, 6, 6)
        haptics_layout.setSpacing(6)

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

        btn_quick_test = QPushButton("🎽 bHaptics 진동 테스트")
        btn_quick_test.setStyleSheet("background-color: #0077b6; color: #ffffff; font-size: 11px; font-weight: bold; padding: 6px;")
        btn_quick_test.clicked.connect(self._on_quick_test)
        haptics_layout.addWidget(btn_quick_test)

        self.mini_vest_preview = MiniVestPreviewWidget()
        haptics_layout.addWidget(self.mini_vest_preview)

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

        # 3. 도킹 가능한 장치 설정 패널
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

        tip_box = QGroupBox("💡 팁 및 안내")
        tip_layout = QVBoxLayout(tip_box)
        lbl_tip = QLabel(
            "• 각 패널의 타이틀 바를 드래그하여 원하는 위치에 자유롭게 놓을 수 있습니다.\n"
            "• 패널을 서로의 위로 드래그하면 탭으로 결합되어 하나로 합쳐집니다.\n"
            "• 실수로 닫은 패널은 상단 메뉴의 토글 버튼이나 [🔄 배치 초기화]로 복원됩니다."
        )
        lbl_tip.setStyleSheet("color: #8395a7; font-size: 11px; line-height: 1.5;")
        tip_layout.addWidget(lbl_tip)
        device_layout.addWidget(tip_box)
        device_layout.addStretch()

        self.dock_device.setWidget(device_content)

        # 4. 도킹 가능한 이벤트 로그 패널
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

        self.shortcut_f11 = QShortcut(QKeySequence(Qt.Key_F11), self)
        self.shortcut_f11.activated.connect(self._toggle_fullscreen)

    def _toggle_fullscreen(self):
        """F11 전체 화면(Full Screen) 및 일반 창 모드 상호 전환"""
        if self.isFullScreen():
            self.showNormal()
            self.btn_fullscreen.setText("⛶ F11")
            self.engine.log("STATE", "🖥️ 일반 창 모드로 복귀했습니다. (F11: 전체 화면)")
        else:
            self.showFullScreen()
            self.btn_fullscreen.setText("🗗 창 모드")
            self.engine.log("STATE", "🖥️ 전체 화면(Full Screen) 모드로 전환되었습니다. (F11 또는 Esc로 해제)")

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self.showNormal()
            self.btn_fullscreen.setText("⛶ F11")
            self.engine.log("STATE", "🖥️ 일반 창 모드로 복귀했습니다. (F11: 전체 화면)")
        else:
            super().keyPressEvent(event)

    def _on_toggle_haptics_dock_btn(self, checked: bool):
        if checked:
            self.dock_haptics.show()
            self.dock_haptics.raise_()
        else:
            self.dock_haptics.hide()

    def _on_toggle_device_dock_btn(self, checked: bool):
        if checked:
            self.dock_device.show()
            self.dock_device.raise_()
        else:
            self.dock_device.hide()

    def _on_toggle_log_dock_btn(self, checked: bool):
        if checked:
            self.dock_log.show()
            self.dock_log.raise_()
        else:
            self.dock_log.hide()

    def _on_dock_haptics_visibility_changed(self, visible: bool):
        if self._in_compact_mode:
            return
        self.btn_toggle_haptics_dock.blockSignals(True)
        self.btn_toggle_haptics_dock.setChecked(visible)
        self.btn_toggle_haptics_dock.blockSignals(False)

    def _on_dock_device_visibility_changed(self, visible: bool):
        if self._in_compact_mode:
            return
        self.btn_toggle_device_dock.blockSignals(True)
        self.btn_toggle_device_dock.setChecked(visible)
        self.btn_toggle_device_dock.blockSignals(False)

    def _on_dock_log_visibility_changed(self, visible: bool):
        if self._in_compact_mode:
            return
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
        self._ui_save_timer.start()

    def _on_quick_test(self):
        med = self.config.haptic_details.medium
        self.engine.haptics.trigger_pattern_direct("medium", med, med.position)

    def _on_log_filter_toggle(self, cat: str, checked: bool):
        self.config.log_filter[cat] = checked
        self.config.save()

    def _on_log_font_size_changed(self, val: int):
        self.lbl_log_font_val.setText(f"{val}pt")
        self.config.log_font_size = val
        self._update_log_font_style()
        self._ui_save_timer.start()

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
        self._in_compact_mode = True
        cur_mode = self.combo_detection_mode.currentData() or getattr(self.config, "detection_mode", "balanced")
        self.compact_hud.sync_mode(cur_mode)
        self.compact_hud.sync_hp(
            self.progress_hp.value(),
            self.progress_hp.stateColor(),
            self.progress_hp.formatText()
        )
        self.compact_hud.sync_paused(self.engine.is_paused)
        self.hide()
        self.compact_hud.show()
        self.compact_hud.raise_()

    def _exit_compact_mode(self):
        """4안 컴팩트 컨트롤 바를 숨기고 3안 전체 대시보드로 복귀"""
        self.compact_hud.hide()
        self.show()
        self._in_compact_mode = False
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
            self.progress_hp.setFormat(f"⚔️ HP: {int(round(self.progress_hp.value()))}% (재개)")
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
        now_mono = time.monotonic()
        frame = self.engine.vision.get_latest_frame()
        if frame is not None:
            if self.video_widget.isVisible() and frame is not self._last_rendered_frame:
                self._last_rendered_frame = frame
                self.video_widget.update_frame(frame)
            if self.video_widget.is_camera_connected and (now_mono - self._last_fps_label_update >= 0.5):
                self._last_fps_label_update = now_mono
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
                meas_fps = self.engine.vision.get_measured_fps()
                fps_txt = f"{meas_fps:.0f}" if meas_fps > 0.1 else "--"
                self.lbl_fps.setText(f"{fw}x{fh} ({ratio_str}) | FPS: {fps_txt}")

        front, back, level = self.engine.haptics.get_current_motor_intensities()

        if hasattr(self, "mini_vest_preview") and self.mini_vest_preview.isVisible():
            self.mini_vest_preview.update_data(front, back, level)

        badge_map = {
            "light": ("🔹 경타 진동", "#1e293b", "#70a1ff", "#3b82f6"),
            "medium": ("🔸 중타 진동", "#2c2416", "#ffd166", "#f59e0b"),
            "heavy": ("🔻 강타 진동!", "#2e1a16", "#ff7f50", "#f97316"),
            "critical": ("⚡ 치명타!", "#3b1219", "#ff4757", "#ef4444"),
            "faint": ("💀 기절 진동!", "#3b0a1e", "#ff2e63", "#ec4899"),
            "heartbeat": ("💓 심장박동", "#2b1422", "#ff6b81", "#f43f5e"),
            "low_hp_loop": ("🚨 빨피 지속", "#2b1216", "#ff4757", "#dc2626"),
        }
        badge_info = badge_map.get(level)

        if hasattr(self, "lbl_active_haptic_badge") and level != self._last_haptic_badge_level:
            self._last_haptic_badge_level = level
            if badge_info is not None:
                b_txt, b_bg, b_fg, b_bd = badge_info
                self.lbl_active_haptic_badge.setText(b_txt)
                self.lbl_active_haptic_badge.setStyleSheet(
                    f"background-color: {b_bg}; color: {b_fg}; border: 1px solid {b_bd}; border-radius: 5px; padding: 4px 6px; font-weight: bold; font-size: 11px;"
                )
            else:
                self.lbl_active_haptic_badge.setText("🟢 진동 대기")
                self.lbl_active_haptic_badge.setStyleSheet(
                    "background-color: #161c28; color: #7f8fa6; border: 1px solid #2b344b; border-radius: 5px; padding: 4px 6px; font-weight: bold; font-size: 11px;"
                )

        if hasattr(self, "compact_hud") and self.compact_hud.isVisible():
            self.compact_hud.update_haptic_badge(level, badge_info)

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
                fmt = f"⏳ {status_detail}"
                state_col = "idle"
            else:
                fmt = f"⚔️ {status_detail}"
                state_col = "red" if val <= 20 else "lime"

            self.progress_hp.setStateColor(state_col)
            self.progress_hp.setFormat(fmt)
            if hasattr(self, "compact_hud") and self.compact_hud:
                self.compact_hud.sync_hp(val, state_col, fmt)
        else:
            if hasattr(self, "compact_hud") and self.compact_hud:
                self.compact_hud.hp_bar.setValue(val)

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
            "CAMERA": "#ff6b6b",
            "SYSTEM": "#a4b0be"
        }
        color = color_map.get(category, "#ced6e0")
        safe_ts = html.escape(str(timestamp))
        safe_cat = html.escape(str(category))
        safe_msg = html.escape(str(message))
        line_html = (
            f"<span style='color:#747d8c;'>[{safe_ts}]</span> "
            f"<span style='color:{color}; font-weight:bold;'>[{safe_cat}]</span> "
            f"<span style='color:#f1f2f6;'>{safe_msg}</span>"
        )
        self.txt_log.append(line_html)
        self.txt_log.moveCursor(QTextCursor.End)

    def closeEvent(self, event):
        if hasattr(self, "render_timer") and self.render_timer.isActive():
            self.render_timer.stop()
        if hasattr(self, "detail_settings_widget") and self.detail_settings_widget:
            self.detail_settings_widget.flush_save()
        if hasattr(self, "_ui_save_timer") and self._ui_save_timer.isActive():
            self._ui_save_timer.stop()

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
