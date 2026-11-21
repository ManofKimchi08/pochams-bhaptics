import html

from PySide6.QtCore import QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QApplication, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTextEdit, QFrame, QDialog, QMessageBox
)

from battle_analytics import BattleAnalytics


class BattleAnalyticsDialog(QDialog):
    """실시간 배틀 누적 대미지, 피격 등급 통계 및 디스코드 리포트 내보내기 창"""

    def __init__(self, analytics: BattleAnalytics, parent=None):
        super().__init__(parent)
        self.analytics = analytics
        self._last_events_version: int = -1

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

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self._update_stats)
        self.refresh_timer.start(500)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        title_box = QHBoxLayout()
        lbl_title = QLabel("📊 배틀 세션 실시간 분석 대시보드")
        lbl_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #00e5ff;")
        title_box.addWidget(lbl_title)
        title_box.addStretch()
        self.lbl_session_time = QLabel("진행 시간: 00:00")
        self.lbl_session_time.setStyleSheet("font-size: 12px; color: #ffd166; font-weight: bold;")
        title_box.addWidget(self.lbl_session_time)
        layout.addLayout(title_box)

        grid = QGridLayout()
        grid.setSpacing(10)

        self.card_dmg = QFrame()
        self.card_dmg.setStyleSheet("background-color: #1e141a; border: 1px solid #4a2332; border-radius: 8px; padding: 6px;")
        v_dmg = QVBoxLayout(self.card_dmg)
        v_dmg.addWidget(QLabel("💥 총 누적 대미지"))
        self.lbl_total_dmg = QLabel("0.0%")
        self.lbl_total_dmg.setStyleSheet("color: #ff4757; font-size: 20px; font-weight: bold;")
        v_dmg.addWidget(self.lbl_total_dmg)
        grid.addWidget(self.card_dmg, 0, 0)

        self.card_hits = QFrame()
        self.card_hits.setStyleSheet("background-color: #141c26; border: 1px solid #23374d; border-radius: 8px; padding: 6px;")
        v_hits = QVBoxLayout(self.card_hits)
        v_hits.addWidget(QLabel("🎯 총 피격 횟수"))
        self.lbl_total_hits = QLabel("0회")
        self.lbl_total_hits.setStyleSheet("color: #00e5ff; font-size: 20px; font-weight: bold;")
        v_hits.addWidget(self.lbl_total_hits)
        grid.addWidget(self.card_hits, 0, 1)

        self.card_max = QFrame()
        self.card_max.setStyleSheet("background-color: #1d1822; border: 1px solid #422a52; border-radius: 8px; padding: 6px;")
        v_max = QVBoxLayout(self.card_max)
        v_max.addWidget(QLabel("⚡ 최대 피격 대미지"))
        self.lbl_max_hit = QLabel("없음")
        self.lbl_max_hit.setStyleSheet("color: #e056fd; font-size: 16px; font-weight: bold;")
        v_max.addWidget(self.lbl_max_hit)
        grid.addWidget(self.card_max, 1, 0)

        self.card_surv = QFrame()
        self.card_surv.setStyleSheet("background-color: #131d1b; border: 1px solid #1e3d34; border-radius: 8px; padding: 6px;")
        v_surv = QVBoxLayout(self.card_surv)
        v_surv.addWidget(QLabel("🛡️ 최저 생존 / 기절 / 교체"))
        self.lbl_surv_stats = QLabel("HP 100% | 0기절 | 0교체")
        self.lbl_surv_stats.setStyleSheet("color: #2ed573; font-size: 14px; font-weight: bold;")
        v_surv.addWidget(self.lbl_surv_stats)
        grid.addWidget(self.card_surv, 1, 1)

        layout.addLayout(grid)

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

        lbl_events_title = QLabel("⏱️ 실시간 배틀 이벤트 타임라인:")
        lbl_events_title.setStyleSheet("font-weight: bold; color: #8bb4ff; font-size: 11px;")
        layout.addWidget(lbl_events_title)

        self.txt_events = QTextEdit()
        self.txt_events.setReadOnly(True)
        layout.addWidget(self.txt_events, 1)

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

        events_ver = s.get("events_version", -1)
        if events_ver != self._last_events_version:
            self._last_events_version = events_ver
            events = self.analytics.get_recent_events(40)
            html_lines = []
            for ev in events:
                t = html.escape(str(ev.get("time", "")))
                tp = str(ev.get("type", ""))
                tp_safe = html.escape(tp)
                desc_safe = html.escape(str(ev.get("desc", "")))
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
                html_lines.append(
                    f"<span style='color:#747d8c;'>[{t}]</span> {icon} "
                    f"<span style='color:{col}; font-weight:bold;'>[{tp_safe}]</span> "
                    f"<span style='color:#f1f2f6;'>{desc_safe}</span>"
                )

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

    def done(self, r: int):
        if hasattr(self, "refresh_timer") and self.refresh_timer.isActive():
            self.refresh_timer.stop()
        super().done(r)
