import time
import threading
from typing import Callable, Optional, List, Dict
from config import AppConfig
from haptic_manager import HapticManager
from vision_detector import VisionDetector

class FusionEngine:
    """비전 분석 및 bHaptics 출력을 결합하는 전용 연동 엔진 (OCR + 빨간 체력(<=20%) 루프 + 포켓몬 교체 감지)"""

    def __init__(self, config: AppConfig):
        self.config = config
        
        # 서브 모듈 초기화
        self.haptics = HapticManager(
            sink_config=self.config.sink,
            details_config=self.config.haptic_details
        )
        self.haptics.master_intensity = self.config.master_intensity
        
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
        self._is_red_hp_active: bool = False
        self._red_hp_thread: Optional[threading.Thread] = None
        self._last_heartbeat_time: float = 0.0
        
        # 이벤트 로그 콜백
        self.on_log_event: Optional[Callable[[str, str, str], None]] = None

        # 비전 및 햅틱 이벤트 바인딩
        self.vision.on_damage_detected = self._handle_vision_damage
        self.vision.on_heal_detected = self._handle_vision_heal
        self.vision.on_pokemon_switched = self._handle_pokemon_switched
        self.haptics.on_haptic_trigger = self._handle_haptic_event

    def start(self) -> None:
        """엔진 컴포넌트 시작"""
        self._is_running = True
        self.haptics.start()
        self.vision.start()
        
        # 빨간 체력 (심장박동 / 상시 루프) 백그라운드 스레드 가동
        self._red_hp_thread = threading.Thread(target=self._red_hp_worker, daemon=True)
        self._red_hp_thread.start()
        
        self.log("SYSTEM", "포챔스-bHaptics 실시간 연동 엔진 가동 (5대 안정화 & 빨간 체력 20% 감지)")

    def stop(self) -> None:
        """엔진 컴포넌트 정지"""
        self._is_running = False
        self.vision.stop()
        self.haptics.stop()
        self.log("SYSTEM", "연동 엔진이 정지되었습니다.")

    @property
    def is_paused(self) -> bool:
        return self.vision.is_paused

    def toggle_pause(self) -> bool:
        paused = self.vision.toggle_pause()
        state_str = "일시정지" if paused else "재개"
        self.log("STATE", f"체력 감지 및 자동 진동이 수동으로 {state_str}되었습니다.")
        return paused

    def auto_snap_roi(self) -> Optional[List[float]]:
        """화면에서 포챔스 아군 체력바 카드를 자동 감지하여 ROI 스냅"""
        new_roi = self.vision.auto_snap_roi()
        if new_roi:
            self.config.hp_roi = new_roi
            self.config.save()
            self.log("STATE", f"🎯 포챔스 체력바 카드 자동 스냅 성공: X={new_roi[0]:.2f}, Y={new_roi[1]:.2f}, W={new_roi[2]:.2f}, H={new_roi[3]:.2f}")
        else:
            self.log("STATE", "⚠️ 화면에서 포챔스 배틀 카드를 찾지 못했습니다. 배틀 화면이 켜진 상태에서 다시 시도하세요.")
        return new_roi

    def log(self, category: str, message: str) -> None:
        """UI 로그 전달 (카테고리 필터링 지원)"""
        timestamp = time.strftime("%H:%M:%S")
        if self.on_log_event:
            try:
                self.on_log_event(timestamp, category, message)
            except Exception:
                pass
        print(f"[{timestamp}] [{category}] {message}")

    def _handle_pokemon_switched(self, old_max_hp: int, new_max_hp: int, new_hp_pct: float) -> None:
        """포켓몬 교체 시 로그 알림 및 빨간 체력 상태 즉시 동기화"""
        red_threshold = self.config.red_hp_threshold
        if 0.0 < new_hp_pct <= red_threshold:
            self._is_red_hp_active = True
            self.log("HP", f"🔄 포켓몬 교체 감지: (최대 HP: {old_max_hp} -> {new_max_hp}, 체력: {new_hp_pct:.1f}%) [🚨 교체 포켓몬 빨간 체력 활성]")
        else:
            self._is_red_hp_active = False
            self.log("HP", f"🔄 포켓몬 교체 감지: (최대 HP: {old_max_hp} -> {new_max_hp}, 체력: {new_hp_pct:.1f}%) [체력 정상 - 빨피 진동 해제]")

    def _handle_vision_heal(self, current_hp_pct: float) -> None:
        """2프레임 연속 안정 회복 확정 시 빨간 체력 해제"""
        red_threshold = self.config.red_hp_threshold
        if current_hp_pct > red_threshold:
            if self._is_red_hp_active:
                self._is_red_hp_active = False
                self.log("HP", f"💚 체력 회복 확정: 빨간 체력 해제 (잔여 체력: {current_hp_pct:.1f}% > {red_threshold:.0f}%)")

    def _handle_vision_damage(self, delta_hp: float, current_hp_pct: float, timestamp: float) -> None:
        """영상 HP 감소 감지 시 데미지 비례 햅틱 출력 및 빨간 체력(<=20%) 상태 갱신"""
        now = time.time()
        
        # 1. 빨간 체력 (Red HP) 진입 검사 (숫자 기반 <= 20%)
        red_threshold = self.config.red_hp_threshold
        if 0.0 < current_hp_pct <= red_threshold:
            if not self._is_red_hp_active:
                self._is_red_hp_active = True
                self.log("HP", f"🚨 빨간 체력 진입! (잔여 체력: {current_hp_pct:.1f}% <= {red_threshold:.0f}%) [심장박동/상시진동 활성 (연출 중에도 지속)]")

        # 2. 피격 등급 판정
        level = "경타"
        if current_hp_pct <= 0.0:
            level = "기절"
            self._is_red_hp_active = False
        elif delta_hp >= 80.0:
            level = "치명타"
        elif delta_hp >= 50.0:
            level = "강타"
        elif delta_hp >= 20.0:
            level = "중타"

        self.log("DAMAGE", f"💥 피격 데미지: -{delta_hp:.1f}% (남은 HP: {current_hp_pct:.1f}%) -> [{level}]")

        if (now - self._last_haptic_trigger_time) < (self.config.debounce_ms / 1000.0):
            return

        self._last_haptic_trigger_time = now
        self.haptics.trigger_damage_haptic(delta_hp, current_hp_pct)

    def _red_hp_worker(self) -> None:
        """빨간 체력 (<=20%) 상태일 때 심장박동 / 상시 루프 진동 비동기 관리 (8.0초 연출 허용 & 심리스 루프)"""
        last_loop_time = 0.0
        while self._is_running:
            now = time.time()
            time_since_seen = now - self.vision.last_number_seen_time
            
            # 💀 1. 기절 상태 엄격 검사 (체력 0 이거나 기절 상태면 즉시 빨간 체력 영구 해제)
            if self.vision.confirmed_curr_hp <= 0 or self.vision.current_hp_pct <= 0.0:
                self._is_red_hp_active = False
            
            # ⏱️ 6대 안전망 검증:
            # 1) 빨간 체력 플래그 활성화
            # 2) 수동 일시정지 아님
            # 3) 잔여 체력 > 0 (기절 아님) & 확정 체력 > 0
            # 4) 최근 8.0초 이내 숫자 인식됨 (포챔스의 긴 스킬 컷신/카메라 회전 중에도 끊김 없이 지속)
            is_alive_red = self._is_red_hp_active and (self.vision.current_hp_pct > 0.0) and (self.vision.confirmed_curr_hp > 0)
            is_valid_scene = (time_since_seen <= 8.0)
            
            if is_alive_red and not self.is_paused and is_valid_scene:
                d = self.config.haptic_details
                
                # 1. 심장박동 (Heartbeat): 주기적 펄스 진동 (0.85초 주기)
                if d.heartbeat.intensity > 0:
                    if (now - self._last_haptic_trigger_time) > 0.4 and (now - self._last_heartbeat_time) > 0.85:
                        self._last_heartbeat_time = now
                        self.haptics.trigger_pattern_direct("heartbeat", d.heartbeat, d.heartbeat.position)
                        
                # 2. 빨피 상시 (Low HP Loop): 빈틈없는 심리스(Seamless) 지속 진동
                if d.low_hp_loop.intensity > 0:
                    dur_sec = max(0.35, d.low_hp_loop.duration)
                    # 이전 진동이 끝나기 0.05초 전에 다음 루프를 큐잉하여 공백 없는 완벽한 지속감 유지
                    if (now - self._last_haptic_trigger_time) > 0.4 and (now - last_loop_time) >= (dur_sec - 0.05):
                        last_loop_time = now
                        self.haptics.trigger_pattern_direct("low_hp_loop", d.low_hp_loop, d.low_hp_loop.position)

            time.sleep(0.04)

    def _handle_haptic_event(self, level: str, intensity: int, duration_ms: int, front: List[int], back: List[int]) -> None:
        active_motors = sum(1 for v in front + back if v > 0)
        self.log("HAPTIC", f"🎽 진동 피드백 발송: [{level.upper()}] 세기: {intensity}%, 지속시간: {duration_ms}ms (모터 {active_motors}개 작동)")
