import time
import threading
from typing import Callable, Optional, List, Dict
from config import AppConfig
from haptic_manager import HapticManager
from vision_detector import VisionDetector

class FusionEngine:
    """비전 분석 및 bHaptics 출력을 결합하는 전용 연동 엔진 (OCR + 포켓몬 교체 감지 + 실시간 햅틱 로깅)"""

    def __init__(self, config: AppConfig):
        self.config = config
        
        # 서브 모듈 초기화
        self.haptics = HapticManager(sink_config=self.config.sink, ws_url=self.config.bhaptics_ws_url)
        self.vision = VisionDetector(
            device_index=self.config.video_device_index,
            width=self.config.video_width,
            height=self.config.video_height,
            roi=self.config.hp_roi,
            min_damage_threshold=self.config.min_damage_threshold,
            buffer_size=self.config.hp_confirm_frames,
            max_jitter_percent=self.config.deadband_percent
        )
        
        # 내부 상태
        self._is_running = False
        self._last_haptic_trigger_time: float = 0.0
        
        # 이벤트 로그 콜백
        self.on_log_event: Optional[Callable[[str, str], None]] = None

        # 비전 및 햅틱 이벤트 바인딩
        self.vision.on_damage_detected = self._handle_vision_damage
        self.vision.on_pokemon_switched = self._handle_pokemon_switched
        self.haptics.on_haptic_trigger = self._handle_haptic_event

    def start(self) -> None:
        """엔진 컴포넌트 시작"""
        self._is_running = True
        self.haptics.start()
        self.vision.start()
        self.log("INFO", "포챔스-bHaptics 실시간 연동 엔진 가동 (OCR 숫자 인식 & 교체 감지)")

    def stop(self) -> None:
        """엔진 컴포넌트 정지"""
        self._is_running = False
        self.vision.stop()
        self.haptics.stop()
        self.log("INFO", "연동 엔진이 정지되었습니다.")

    @property
    def is_paused(self) -> bool:
        return self.vision.is_paused

    def toggle_pause(self) -> bool:
        paused = self.vision.toggle_pause()
        state_str = "일시정지" if paused else "재개"
        self.log("PAUSE" if paused else "RESUME", f"체력 감지 및 자동 진동이 수동으로 {state_str}되었습니다.")
        return paused

    def auto_snap_roi(self) -> Optional[List[float]]:
        """화면에서 포챔스 아군 체력바 카드를 자동 감지하여 ROI 스냅"""
        new_roi = self.vision.auto_snap_card_roi()
        if new_roi:
            self.config.hp_roi = new_roi
            self.config.save()
            self.log("AUTO_SNAP", f"🎯 포챔스 체력바 카드 자동 스냅 성공: X={new_roi[0]:.2f}, Y={new_roi[1]:.2f}, W={new_roi[2]:.2f}, H={new_roi[3]:.2f}")
        else:
            self.log("AUTO_SNAP", "⚠️ 화면에서 포챔스 배틀 카드를 찾지 못했습니다. 배틀 화면이 켜진 상태에서 다시 시도하세요.")
        return new_roi

    def log(self, level: str, message: str) -> None:
        """UI 로그 전달"""
        timestamp = time.strftime("%H:%M:%S")
        if self.on_log_event:
            try:
                self.on_log_event(timestamp, f"[{level}] {message}")
            except Exception:
                pass
        print(f"[{timestamp}] [{level}] {message}")

    def _handle_pokemon_switched(self, old_max_hp: int, new_max_hp: int, new_hp_pct: float) -> None:
        """포켓몬 교체 시 로그 알림 및 진동 무시"""
        self.log("SWITCH", f"🔄 포켓몬 교체 감지: (최대 HP: {old_max_hp} -> {new_max_hp}, 새 체력: {new_hp_pct:.1f}%) [진동 무시]")

    def _handle_vision_damage(self, delta_hp: float, current_hp_pct: float, timestamp: float) -> None:
        """영상 HP 감소 감지 시 데미지 비례 햅틱 출력"""
        now = time.time()
        
        # 데미지 레벨 결정
        level = "light"
        if delta_hp > 80.0:
            level = "critical"
        elif delta_hp > 50.0:
            level = "heavy"
        elif delta_hp > 20.0:
            level = "medium"
        else:
            level = "light"

        self.log("DAMAGE", f"💥 피격 데미지: -{delta_hp:.1f}% (남은 HP: {current_hp_pct:.1f}%) -> 레벨: [{level.upper()}]")

        # 쿨다운 확인
        if (now - self._last_haptic_trigger_time) < (self.config.debounce_ms / 1000.0):
            return

        self._last_haptic_trigger_time = now
        self.haptics.trigger_damage(level, damage_delta=delta_hp, position_mode=self.config.haptic_position)

    def _handle_haptic_event(self, level: str, intensity: int, duration_ms: int, front: List[int], back: List[int]) -> None:
        """햅틱 출력 시 상세 로그 기록"""
        front_cnt = sum(1 for v in front if v > 0)
        back_cnt = sum(1 for v in back if v > 0)
        self.log("HAPTIC", f"⚡ [{level.upper()}] 촉각슈트 진동 출력 (강도: {intensity}%, 지속: {duration_ms}ms, 모터: 앞 {front_cnt}개 / 뒤 {back_cnt}개)")
