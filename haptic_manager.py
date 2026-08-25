import json
import math
import time
import threading
import queue
from typing import Callable, Optional, List, Dict, Any, Tuple
import numpy as np

from config import HapticSinkConfig, DetailedHapticConfig, HapticDetailRow

try:
    import bhaptics_python
    HAS_BHAPTICS_SDK = True
except ImportError:
    bhaptics_python = None
    HAS_BHAPTICS_SDK = False

class HapticManager:
    """
    포챔스 전용 다이내믹 햅틱 컨트롤러
    - 🎽 공식 bhaptics-python SDK 직접 제어
    - ⚡ 4단계 피격 (경타/중타/강타/치명타) + 기절 + 심장박동 + 빨피 상시
    - 🔢 멀티 버스트 타격횟수(Hit Count) 지원
    - 🎚️ 앞/뒤 균형 및 마스터 세기 실시간 적용
    - 📊 실시간 2D 모터 매트릭스 시각화
    """

    def __init__(self, sink_config: HapticSinkConfig, details_config: Optional[DetailedHapticConfig] = None):
        self.sink = sink_config
        self.details = details_config if details_config is not None else DetailedHapticConfig()
        self.master_intensity: int = 100
        
        self._is_running = False
        self._connected = False
        self._status_msg = "초기화 대기 중"
        
        # 큐 및 스레드
        self._send_queue: queue.Queue = queue.Queue(maxsize=100)
        self._worker_thread: Optional[threading.Thread] = None
        
        # 실시간 모터 상태 추적 (시각화 애니메이션용)
        self.last_front_motors: List[int] = [0] * 20
        self.last_back_motors: List[int] = [0] * 20
        self.last_trigger_time: float = 0.0
        self.last_duration_ms: int = 0
        self.last_level: str = "none"
        self._state_lock = threading.Lock()
        
        # 콜백
        self.on_status_change: Optional[Callable[[bool, str], None]] = None
        self.on_haptic_trigger: Optional[Callable[[str, int, int, List[int], List[int]], None]] = None

    def start(self) -> None:
        """햅틱 매니저 가동"""
        if self._is_running:
            return
            
        self._is_running = True
        self._worker_thread = threading.Thread(target=self._run_official_sdk, daemon=True)
        self._worker_thread.start()

    def stop(self) -> None:
        """햅틱 매니저 정지 및 리소스 정리"""
        self._is_running = False
        self._connected = False
        
        if HAS_BHAPTICS_SDK:
            try:
                bhaptics_python.stop_all()
                bhaptics_python.close()
            except Exception:
                pass
                
        self._notify_status(False, "햅틱 장치 연결 종료됨")

    def update_sink_config(self, new_sink: HapticSinkConfig) -> None:
        """GUI에서 설정 변경 시 재연결"""
        self.stop()
        self.sink = new_sink
        time.sleep(0.3)
        self.start()

    def is_connected(self) -> bool:
        return self._connected

    def _notify_status(self, connected: bool, message: str) -> None:
        self._connected = connected
        self._status_msg = message
        if self.on_status_change:
            try:
                self.on_status_change(connected, message)
            except Exception as e:
                print(f"[Haptics] 상태 콜백 오류: {e}")

    def _run_official_sdk(self) -> None:
        """공식 bhaptics-python SDK 백엔드"""
        if not HAS_BHAPTICS_SDK:
            self._notify_status(False, "bhaptics-python 패키지가 설치되지 않았습니다.")
            return

        app_id = self.sink.app_id.strip()
        api_key = self.sink.api_key.strip()
        
        if not app_id or not api_key:
            self._notify_status(False, "App ID 또는 API Key를 입력해주세요.")
            return

        try:
            self._notify_status(False, "bHaptics SDK 초기화 중...")
            bhaptics_python.init(app_id, api_key)
            self._notify_status(True, "bHaptics SDK 공식 연결 완료")
            print("[Haptics] bhaptics_python 공식 SDK 초기화 성공")
        except Exception as e:
            self._notify_status(False, f"SDK 초기화 실패: {e}")
            return

        while self._is_running:
            try:
                item = self._send_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            try:
                req_type = item.get("type")
                if req_type == "play_dot":
                    duration = item.get("duration", 200)
                    motors = item.get("motors", [])
                    bhaptics_python.play_dot(duration, motors)
                elif req_type == "stop":
                    bhaptics_python.stop_all()
            except Exception as e:
                print(f"[Haptics] SDK 전송 오류: {e}")

    def _create_sdk_motor_array(self, front_20: List[int], back_20: List[int]) -> List[int]:
        """Vest 32점 또는 40점 매핑"""
        # 마스터 세기 및 앞뒤 밸런스 적용
        m_factor = self.master_intensity / 100.0
        fb_factor = (self.details.front_balance / 100.0) * self.sink.front_gain
        bb_factor = (self.details.back_balance / 100.0) * self.sink.back_gain
        
        f20_g = [int(np.clip(v * fb_factor * m_factor, 0, 100)) for v in front_20]
        b20_g = [int(np.clip(v * bb_factor * m_factor, 0, 100)) for v in back_20]

        if self.sink.motor_count == 32:
            indices_16 = [0, 1, 2, 3, 4, 7, 8, 11, 12, 15, 16, 17, 18, 19, 5, 6]
            f16 = [f20_g[i] for i in indices_16]
            b16 = [b20_g[i] for i in indices_16]
            return f16 + b16
        else:
            return f20_g + b20_g

    def trigger_pattern_direct(self, level: str, detail_row: HapticDetailRow, position_mode: Optional[str] = None) -> None:
        """단일 또는 다중 타격횟수(Hit Count) 패턴 비동기 실행 (부위별 설정 지원)"""
        pos = position_mode if position_mode is not None else getattr(detail_row, "position", "All")
        threading.Thread(target=self._exec_pattern_burst, args=(level, detail_row, pos), daemon=True).start()

    def _exec_pattern_burst(self, level: str, detail_row: HapticDetailRow, position_mode: str = "All") -> None:
        """타격 횟수(Hit Count)만큼 반복해서 진동 버스트 전송"""
        hit_count = max(1, min(5, detail_row.hit_count))
        duration_ms = int(detail_row.duration * 1000)
        intensity_val = int(detail_row.intensity)

        for burst_idx in range(hit_count):
            front_20, back_20 = self._generate_motor_matrix(level, intensity_val, position_mode)
            motors_sdk = self._create_sdk_motor_array(front_20, back_20)

            # 실시간 시각화 상태 기록
            with self._state_lock:
                self.last_front_motors = front_20
                self.last_back_motors = back_20
                self.last_trigger_time = time.time()
                self.last_duration_ms = duration_ms
                self.last_level = level

            # 하드웨어 SDK 전송
            try:
                self._send_queue.put_nowait({
                    "type": "play_dot",
                    "duration": duration_ms,
                    "motors": motors_sdk
                })
            except queue.Full:
                pass

            if self.on_haptic_trigger:
                try:
                    self.on_haptic_trigger(level, intensity_val, duration_ms, front_20, back_20)
                except Exception:
                    pass

            if burst_idx < hit_count - 1:
                time.sleep((detail_row.duration * 0.7) + 0.05)

    def trigger_damage_haptic(self, damage_percent: float, current_hp_pct: float = 100.0, position_mode: Optional[str] = None) -> None:
        """감지된 데미지 % 및 남은 체력 %에 따른 햅틱 패턴 자동 분기 (각 행별 부위 적용)"""
        d = self.details
        if current_hp_pct <= 0.0:
            pos = position_mode if position_mode is not None else d.faint.position
            self.trigger_pattern_direct("faint", d.faint, pos)
        elif damage_percent <= 20.0:
            pos = position_mode if position_mode is not None else d.light.position
            self.trigger_pattern_direct("light", d.light, pos)
        elif damage_percent <= 50.0:
            pos = position_mode if position_mode is not None else d.medium.position
            self.trigger_pattern_direct("medium", d.medium, pos)
        elif damage_percent <= 80.0:
            pos = position_mode if position_mode is not None else d.heavy.position
            self.trigger_pattern_direct("heavy", d.heavy, pos)
        else:
            pos = position_mode if position_mode is not None else d.critical.position
            self.trigger_pattern_direct("critical", d.critical, pos)

    def _generate_motor_matrix(self, level: str, intensity: int, position_mode: str = "All") -> Tuple[List[int], List[int]]:
        """패턴 레벨에 따른 20개 모터 강도 매핑"""
        front = [0] * 20
        back = [0] * 20
        
        use_front = position_mode in ["VestFront", "All"]
        use_back = position_mode in ["VestBack", "All"]

        if level == "light":
            # 경타: 가슴 중앙 2개 모터
            indices = [5, 6]
            for idx in indices:
                if use_front: front[idx] = intensity
                if use_back: back[idx] = intensity

        elif level == "medium":
            # 중타: 상체 및 가슴 6개 모터
            indices = [1, 2, 5, 6, 9, 10]
            for idx in indices:
                if use_front: front[idx] = intensity
                if use_back: back[idx] = intensity

        elif level == "heavy":
            # 강타: 가슴, 복부, 옆구리 12개 모터
            indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
            for idx in indices:
                if use_front: front[idx] = intensity
                if use_back: back[idx] = intensity

        elif level in ["critical", "faint"]:
            # 치명타 / 기절: 20개 전 모터 풀 파워
            for idx in range(20):
                if use_front: front[idx] = intensity
                if use_back: back[idx] = intensity

        elif level == "heartbeat":
            # 심장박동: 좌측 가슴 펄스
            indices = [4, 5, 8]
            for idx in indices:
                if use_front: front[idx] = intensity
                if use_back: back[idx] = int(intensity * 0.5)

        elif level == "low_hp_loop":
            # 빨피 상시: 하복부 은은한 베이스 지속 진동
            indices = [12, 13, 14, 15, 16, 17, 18, 19]
            for idx in indices:
                if use_front: front[idx] = intensity
                if use_back: back[idx] = intensity
        else:
            indices = [5, 6]
            for idx in indices:
                if use_front: front[idx] = intensity
                if use_back: back[idx] = intensity

        return front, back

    def get_current_motor_intensities(self) -> Tuple[List[float], List[float], str]:
        """UI 시각화를 위해 현재 활성화된 모터 강도(0~100)와 패턴 레벨 반환"""
        with self._state_lock:
            elapsed = (time.time() - self.last_trigger_time) * 1000.0
            duration = max(50, self.last_duration_ms)
            
            if elapsed >= duration or self.last_level == "none":
                return [0.0] * 20, [0.0] * 20, "none"

            # 감쇠 페이드아웃 곡선
            ratio = 1.0 - (elapsed / duration)
            fade = math.sin(ratio * math.pi / 2.0)
            
            front_f = [float(v * fade) for v in self.last_front_motors]
            back_f = [float(v * fade) for v in self.last_back_motors]
            return front_f, back_f, self.last_level
