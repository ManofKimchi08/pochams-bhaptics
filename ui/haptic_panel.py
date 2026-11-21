from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QCheckBox, QSlider, QFrame
)

from config import AppConfig, DetailedHapticConfig, HapticDetailRow
from fusion_engine import FusionEngine


class EmbeddedHapticDetailView(QWidget):
    """햅틱 세기 제어 창 내부에 스크롤로 직접 내장되는 세부 설정 뷰어"""

    def __init__(self, config: AppConfig, engine: FusionEngine, parent=None):
        super().__init__(parent)
        self.config = config
        self.engine = engine
        self.details = config.haptic_details

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(250)
        self._save_timer.timeout.connect(self.config.save)

        self._init_ui()

    def flush_save(self):
        """대기 중인 디바운스 설정 저장이 있으면 즉시 디스크에 반영"""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.config.save()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(10)

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

            ctrl_grid = QGridLayout()
            ctrl_grid.setHorizontalSpacing(8)
            ctrl_grid.setVerticalSpacing(4)

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

        lbl_tips = QLabel(
            "• 타격횟수: 1회 피격 시 연속 진동 횟수\n"
            "• 빨피 상시: 0.35초 이상 유지 권장\n"
            "• 심장박동: 길이 증가 시 분당 박동수 조절"
        )
        lbl_tips.setStyleSheet("color: #636e72; font-size: 10px; line-height: 1.4;")
        main_layout.addWidget(lbl_tips)

        self._update_perceived_damage()

    def _set_balance_widgets_silently(self, front_val: int, back_val: int):
        w = self.row_widgets.get("balance", {})
        sld_int = w.get("sld_int")
        sld_dur = w.get("sld_dur")
        if sld_int is not None:
            sld_int.blockSignals(True)
            try:
                sld_int.setValue(front_val)
            finally:
                sld_int.blockSignals(False)
        if "lbl_int_val" in w:
            w["lbl_int_val"].setText(f"{front_val}%")
        if sld_dur is not None:
            sld_dur.blockSignals(True)
            try:
                sld_dur.setValue(back_val)
            finally:
                sld_dur.blockSignals(False)
        if "lbl_dur_val" in w:
            w["lbl_dur_val"].setText(f"{back_val}%")

    def _set_row_widgets_silently(self, key: str, row_obj: HapticDetailRow):
        w = self.row_widgets.get(key, {})
        sld_int = w.get("sld_int")
        if sld_int is not None:
            sld_int.blockSignals(True)
            try:
                sld_int.setValue(row_obj.intensity)
            finally:
                sld_int.blockSignals(False)
        if "lbl_int_val" in w:
            w["lbl_int_val"].setText(f"{row_obj.intensity}%")

        sld_dur = w.get("sld_dur")
        if sld_dur is not None:
            sld_dur.blockSignals(True)
            try:
                sld_dur.setValue(int(round(row_obj.duration * 100)))
            finally:
                sld_dur.blockSignals(False)
        if "lbl_dur_val" in w:
            w["lbl_dur_val"].setText(f"{row_obj.duration:.2f}초")

        sld_hits = w.get("sld_hits")
        if sld_hits is not None:
            sld_hits.blockSignals(True)
            try:
                sld_hits.setValue(row_obj.hit_count)
            finally:
                sld_hits.blockSignals(False)
        if "lbl_hits_val" in w:
            w["lbl_hits_val"].setText(f"{row_obj.hit_count}번")

        combo_pos = w.get("combo_pos")
        if combo_pos is not None:
            combo_pos.blockSignals(True)
            try:
                p_idx = combo_pos.findData(row_obj.position)
                combo_pos.setCurrentIndex(p_idx if p_idx >= 0 else 0)
            finally:
                combo_pos.blockSignals(False)

    def _on_intensity_changed(self, key: str, val: int, lbl: QLabel):
        lbl.setText(f"{val}%")
        if key == "balance":
            self.details.front_balance = val
        else:
            getattr(self.details, key).intensity = val
        self._apply_and_update(immediate_save=False)

    def _on_back_balance_changed(self, val: int, lbl: QLabel):
        lbl.setText(f"{val}%")
        self.details.back_balance = val
        self._apply_and_update(immediate_save=False)

    def _on_duration_changed(self, key: str, val: int, lbl: QLabel):
        sec = val / 100.0
        lbl.setText(f"{sec:.2f}초")
        getattr(self.details, key).duration = sec
        self._apply_and_update(immediate_save=False)

    def _on_hit_count_changed(self, key: str, val: int, lbl: QLabel):
        lbl.setText(f"{val}번")
        getattr(self.details, key).hit_count = val
        self._apply_and_update(immediate_save=False)

    def _on_position_changed(self, key: str, pos_val: str):
        if pos_val and key != "balance":
            getattr(self.details, key).position = pos_val
            self._apply_and_update(immediate_save=True)

    def _apply_and_update(self, immediate_save: bool = False):
        self.engine.haptics.details = self.details
        self.config.haptic_details = self.details
        self._update_perceived_damage()
        if immediate_save:
            self._save_timer.stop()
            self.config.save()
        else:
            self._save_timer.start()

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

    def _reset_row_data_and_widgets(self, key: str, default_d: DetailedHapticConfig):
        if key == "balance":
            self.details.front_balance = default_d.front_balance
            self.details.back_balance = default_d.back_balance
            self._set_balance_widgets_silently(default_d.front_balance, default_d.back_balance)
        else:
            def_row = getattr(default_d, key)
            new_row = HapticDetailRow(def_row.intensity, def_row.duration, def_row.hit_count, def_row.position)
            setattr(self.details, key, new_row)
            self._set_row_widgets_silently(key, new_row)

    def _on_reset_row(self, key: str):
        default_d = DetailedHapticConfig()
        self._reset_row_data_and_widgets(key, default_d)
        self._apply_and_update(immediate_save=True)

    def _on_ripple_toggled(self, checked: bool):
        self.details.enable_ripple_effect = checked
        self._apply_and_update(immediate_save=True)

    def _reset_all_defaults(self):
        default_d = DetailedHapticConfig()
        self.config.haptic_details = default_d
        self.details = default_d
        self.chk_ripple.blockSignals(True)
        try:
            self.chk_ripple.setChecked(self.details.enable_ripple_effect)
        finally:
            self.chk_ripple.blockSignals(False)
        for key in self.row_widgets:
            self._reset_row_data_and_widgets(key, default_d)
        self._apply_and_update(immediate_save=True)

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
        self.chk_ripple.blockSignals(True)
        try:
            self.chk_ripple.setChecked(p["ripple"])
        finally:
            self.chk_ripple.blockSignals(False)

        for row_key in ["light", "medium", "heavy", "critical", "faint", "heartbeat", "low_hp_loop"]:
            intensity, dur, hits, pos = p[row_key]
            row_obj = HapticDetailRow(intensity=intensity, duration=dur, hit_count=hits, position=pos)
            setattr(self.details, row_key, row_obj)
            self._set_row_widgets_silently(row_key, row_obj)

        self._apply_and_update(immediate_save=True)
        names = {"mild": "🍃 순한맛 (입문)", "standard": "⚖️ 표준 (밸런스)", "hardcore": "🔥 극한 (하드코어)"}
        self.engine.log("STATE", f"⚡ 햅틱 프리셋 적용: [{names.get(preset_key, preset_key)}]")
