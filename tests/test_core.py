import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from battle_analytics import BattleAnalytics
from config import (
    AppConfig,
    CONFIG_FILE,
    DetailedHapticConfig,
    HapticDetailRow,
    HapticSinkConfig,
    classify_damage_magnitude,
    classify_damage_tier,
)
from fusion_engine import FusionEngine
from haptic_manager import HapticManager
from vision_detector import VisionDetector


class TestDamageTierConsistency(unittest.TestCase):
    def test_boundaries_across_all_components(self):
        cases = [
            # (delta_hp, current_hp_pct, expected_key, expected_name)
            (1.0, 99.0, "light", "경타"),
            (20.0, 80.0, "light", "경타"),
            (20.1, 79.9, "medium", "중타"),
            (50.0, 50.0, "medium", "중타"),
            (50.1, 49.9, "heavy", "강타"),
            (80.0, 20.0, "heavy", "강타"),
            (80.1, 19.9, "critical", "치명타"),
            (99.0, 1.0, "critical", "치명타"),
            (15.0, 0.0, "faint", "기절"),
            (100.0, 0.0, "faint", "기절"),
        ]

        for delta, rem_hp, exp_key, exp_name in cases:
            key, name = classify_damage_tier(delta, rem_hp)
            self.assertEqual((key, name), (exp_key, exp_name))

            analytics = BattleAnalytics()
            analytics.record_damage(delta, rem_hp, key, name)
            summary = analytics.get_summary_dict()
            if exp_key == "faint":
                self.assertEqual(summary["faint_count"], 1)
                mag_key, _ = classify_damage_magnitude(delta)
                self.assertEqual(summary["hit_counts"][mag_key], 1)
            else:
                self.assertEqual(summary["hit_counts"][exp_key], 1)

            cfg = AppConfig()
            mgr = HapticManager(cfg.sink, cfg.haptic_details)
            dispatched = []
            with patch.object(mgr, "trigger_pattern_direct", side_effect=lambda lvl, row, pos=None: dispatched.append(lvl)):
                mgr.trigger_damage_haptic(delta, rem_hp)
            self.assertEqual(dispatched, [exp_key])

            engine = FusionEngine(cfg)
            eng_dispatched = []
            with patch.object(engine.haptics, "trigger_damage_haptic", side_effect=lambda d, h: eng_dispatched.append(classify_damage_tier(d, h)[0])):
                engine._handle_vision_damage(delta, rem_hp, time.time())
            self.assertEqual(eng_dispatched, [exp_key])
            last_ev = engine.analytics.get_recent_events(1)[-1]
            self.assertEqual(last_ev["level"], exp_name)


class TestConfig(unittest.TestCase):
    def test_save_load_roundtrip_and_unknown_keys(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "config.json")
            cfg = AppConfig()
            cfg.sink.app_id = "my_app_id"
            cfg.sink.api_key = "my_secret_key"
            cfg.hp_roi = [0.1, 0.2, 0.3, 0.4]
            cfg.compact_mode_x = 321
            cfg.compact_mode_y = 123
            cfg.save(path)

            loaded = AppConfig.load(path)
            self.assertEqual(loaded.sink.app_id, "my_app_id")
            self.assertEqual(loaded.sink.api_key, "my_secret_key")
            self.assertEqual(loaded.hp_roi, [0.1, 0.2, 0.3, 0.4])
            self.assertEqual(loaded.compact_mode_x, 321)
            self.assertEqual(loaded.compact_mode_y, 123)
            self.assertIn("CAMERA", loaded.log_filter)

            # Inject unknown/legacy fields across top-level, sink, and haptic_details rows
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            raw["unknown_top_key"] = "legacy"
            raw["sink"]["unknown_sink_key"] = 999
            raw["haptic_details"]["light"]["unknown_row_key"] = True
            raw["log_filter"].pop("CAMERA", None)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(raw, f)

            recovered = AppConfig.load(path)
            self.assertEqual(recovered.sink.app_id, "my_app_id")
            self.assertEqual(recovered.sink.api_key, "my_secret_key")
            self.assertEqual(recovered.hp_roi, [0.1, 0.2, 0.3, 0.4])
            self.assertTrue(recovered.log_filter.get("CAMERA"))


class TestVisionOcrParser(unittest.TestCase):
    def test_parse_pokeechamps_hp_smart(self):
        fn = VisionDetector.parse_pokeechamps_hp_smart
        self.assertEqual(fn("126/300"), (126, 300))
        self.assertEqual(fn("0/140"), (0, 140))
        self.assertIsNone(fn("04:58"))
        self.assertIsNone(fn("⏱ 05:00"))
        self.assertEqual(fn("197 1197"), (197, 197))
        self.assertEqual(fn("197 7197"), (197, 197))
        self.assertEqual(fn("781207"), (78, 207))
        self.assertEqual(fn("9197"), (9, 197))
        self.assertEqual(fn("91197", known_max_hp=197, known_curr_hp=19), (9, 197))
        self.assertIsNone(fn("08/207"))


class TestFusionEngine(unittest.TestCase):
    def test_faint_bypasses_debounce_and_normal_hit_respects_debounce(self):
        cfg = AppConfig()
        cfg.detection_mode = "balanced"
        engine = FusionEngine(cfg)
        triggered = []

        with patch.object(engine.haptics, "trigger_damage_haptic", side_effect=lambda d, h: triggered.append((d, h))):
            base_t = 1000.0
            engine._handle_vision_damage(25.0, 75.0, base_t)
            self.assertEqual(len(triggered), 1)

            # Non-faint hit 0.01s later should be debounced
            engine._handle_vision_damage(10.0, 65.0, base_t + 0.01)
            self.assertEqual(len(triggered), 1)

            # Faint 0.02s later MUST bypass debounce
            engine._handle_vision_damage(65.0, 0.0, base_t + 0.02)
            self.assertEqual(len(triggered), 2)
            self.assertEqual(triggered[-1][1], 0.0)
            self.assertFalse(engine._is_red_hp_active)

    def test_red_hp_state_transitions(self):
        cfg = AppConfig()
        cfg.red_hp_threshold = 20.0
        engine = FusionEngine(cfg)

        with patch.object(engine.haptics, "trigger_damage_haptic"):
            engine._handle_vision_damage(85.0, 15.0, 100.0)
            self.assertTrue(engine._is_red_hp_active)

            engine._handle_vision_heal(15.0, 30.0)
            self.assertFalse(engine._is_red_hp_active)

            engine._handle_pokemon_switched(200, 180, 12.0)
            self.assertTrue(engine._is_red_hp_active)

            engine._handle_pokemon_switched(180, 220, 100.0)
            self.assertFalse(engine._is_red_hp_active)


class TestHapticManager(unittest.TestCase):
    def test_stop_joins_workers_cleanly(self):
        cfg = AppConfig()
        mgr = HapticManager(cfg.sink, cfg.haptic_details)
        mgr.start()
        self.assertIsNotNone(mgr._worker_thread)
        self.assertIsNotNone(mgr._burst_worker_thread)
        time.sleep(0.05)
        mgr.stop()
        self.assertIsNone(mgr._worker_thread)
        self.assertIsNone(mgr._burst_worker_thread)

    def test_ripple_burst_preempts_early_when_new_burst_queued(self):
        cfg = AppConfig()
        mgr = HapticManager(cfg.sink, cfg.haptic_details)
        mgr._is_running = True
        sent_phases = []

        original_put = mgr._send_queue.put_nowait

        def intercept_put(item):
            sent_phases.append(item)
            original_put(item)
            if len(sent_phases) == 1:
                # Queue a newer burst while critical ripple phase 1 finishes
                mgr._burst_queue.put_nowait(("faint", cfg.haptic_details.faint, "All"))

        with patch.object(mgr._send_queue, "put_nowait", side_effect=intercept_put):
            mgr._exec_ripple_burst("critical", 100, 520, "All")

        # Critical ripple has 4 phases; preemption after phase 1 must cut it short to 1 phase
        self.assertEqual(len(sent_phases), 1)
        mgr._is_running = False


class TestBattleAnalytics(unittest.TestCase):
    def test_thread_safety_bounded_maxlen_and_versioning(self):
        analytics = BattleAnalytics()
        v0 = analytics.get_summary_dict()["events_version"]

        errors = []

        def writer(worker_id: int):
            try:
                for i in range(150):
                    analytics.record_damage(10.0, 90.0 - (i % 80), "light", "경타")
                    if i % 10 == 0:
                        analytics.record_heal(5.0, 95.0)
                    if i % 25 == 0:
                        analytics.record_switch(200, 210, 100.0)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(120):
                    analytics.get_summary_dict()
                    analytics.get_recent_events(40)
                    analytics.generate_clipboard_report()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)] + [
            threading.Thread(target=reader) for _ in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        self.assertEqual(errors, [])
        summary = analytics.get_summary_dict()
        # 4 writers * 150 damage = 600 hits; total events > 500 capped at maxlen=500
        self.assertEqual(summary["total_hits"], 600)
        self.assertEqual(summary["events_count"], 500)
        self.assertGreater(summary["events_version"], v0)

        v_before_reset = summary["events_version"]
        analytics.reset_session()
        self.assertEqual(analytics.get_summary_dict()["events_count"], 0)
        self.assertEqual(analytics.get_summary_dict()["events_version"], v_before_reset + 1)


class TestMainWindowOffscreen(unittest.TestCase):
    def test_main_window_ui_behaviors(self):
        from PySide6.QtWidgets import QApplication
        import main as app_main

        cfg_exists = os.path.exists(CONFIG_FILE)
        bak_path = f"{CONFIG_FILE}.bak_unittest"
        if cfg_exists:
            shutil.copy2(CONFIG_FILE, bak_path)

        win = None
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            with patch("vision_detector.VisionDetector.get_video_devices", return_value=[{"index": 0, "name": "Mock Device"}]), \
                 patch("vision_detector.VisionDetector.start", return_value=True):
                win = app_main.MainWindow()
                win.show()
                app.processEvents()

                # 1. Preset applies and triggers config.save() only ONCE
                with patch.object(win.config, "save") as mock_save:
                    win.detail_settings_widget._apply_preset("mild")
                    app.processEvents()
                    self.assertEqual(mock_save.call_count, 1)

                # 2. _append_log escapes '<=' properly
                win.txt_log.clear()
                win._append_log("12:00:00", "HP", "체력 <= 20% 경고 & 카메라 <확인>")
                app.processEvents()
                plain = win.txt_log.toPlainText()
                self.assertIn("체력 <= 20% 경고 & 카메라 <확인>", plain)

                # 3. Compact mode preserves dock button check state and syncs HP / mode / pause
                self.assertTrue(win.btn_toggle_haptics_dock.isChecked())
                win._update_hp_bar(18.0, 12.0, True, "HP: 18% (54/300)")
                win._enter_compact_mode()
                app.processEvents()
                self.assertTrue(win._in_compact_mode)
                self.assertTrue(win.compact_hud.isVisible())
                self.assertFalse(win.isVisible())
                self.assertEqual(win.compact_hud.hp_bar.value(), 18.0)
                self.assertTrue(win.btn_toggle_haptics_dock.isChecked())

                win.compact_hud.mode_changed_requested.emit("fast")
                app.processEvents()
                self.assertEqual(win.combo_detection_mode.currentData(), "fast")

                win._on_toggle_pause()
                app.processEvents()
                self.assertEqual(win.compact_hud.hp_bar.stateColor(), "paused")
                win._on_toggle_pause()
                app.processEvents()

                win._exit_compact_mode()
                app.processEvents()
                self.assertFalse(win._in_compact_mode)
                self.assertTrue(win.isVisible())

                # 4. BattleAnalyticsDialog only updates txt_events HTML when events_version changes
                dlg = app_main.BattleAnalyticsDialog(win.engine.analytics, win)
                try:
                    dlg._update_stats()
                    with patch.object(dlg.txt_events, "setHtml") as mock_set_html:
                        dlg._update_stats()
                        self.assertEqual(mock_set_html.call_count, 0)
                        win.engine.analytics.record_damage(25.0, 75.0, "medium", "중타")
                        dlg._update_stats()
                        self.assertEqual(mock_set_html.call_count, 1)
                finally:
                    dlg.close()

                # 5. Clean shutdown sets _allow_force_close and stops timers/threads
                win.close()
                app.processEvents()
                self.assertTrue(win.compact_hud._allow_force_close)
                win = None
        finally:
            if win is not None:
                win.close()
            if cfg_exists and os.path.exists(bak_path):
                shutil.move(bak_path, CONFIG_FILE)
            elif not cfg_exists and os.path.exists(CONFIG_FILE):
                os.remove(CONFIG_FILE)


if __name__ == "__main__":
    unittest.main()
