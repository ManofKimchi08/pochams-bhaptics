import json
import time
import threading
import queue
import asyncio
import numpy as np
import websocket
from typing import Callable, Optional, List, Dict, Any, Tuple

from config import HapticSinkConfig

# 공식 SDK 임포트
try:
    import bhaptics_python
    HAS_BHAPTICS_SDK = True
except ImportError:
    bhaptics_python = None
    HAS_BHAPTICS_SDK = False

class HapticManager:
    """공식 bhaptics-python SDK 및 레거시 WebSocket 기반 햅틱 컨트롤러 (실시간 모터 시각화 지원)"""

    def __init__(self, sink_config: HapticSinkConfig, ws_url: str = "ws://127.0.0.1:15881/v2/feedbacks"):
        self.sink = sink_config
        self.ws_url = ws_url
        
        self._is_running = False
        self._connected = False
        self._status_msg = "초기화 대기 중"
        
        # 큐 및 스레드
        self._send_queue: queue.Queue = queue.Queue(maxsize=100)
        self._worker_thread: Optional[threading.Thread] = None
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # WebSocket 레거시용
        self.ws: Optional[websocket.WebSocketApp] = None
        
        # 실시간 모터 상태 추적 (시각화 애니메이션용)
        self.last_front_motors: List[int] = [0] * 20
        self.last_back_motors: List[int] = [0] * 20
        self.last_trigger_time: float = 0.0
        self.last_duration_ms: int = 0
        self.last_level: str = "none"
        self._state_lock = threading.Lock()
        
        # 콜백: (level, intensity, duration_ms, front_motors, back_motors)
        self.on_status_change: Optional[Callable[[bool, str], None]] = None
        self.on_haptic_trigger: Optional[Callable[[str, int, int, List[int], List[int]], None]] = None

    def start(self) -> None:
        """햅틱 매니저 가동"""
        if self._is_running:
            return
            
        self._is_running = True
        self._worker_thread = threading.Thread(target=self._run_backend, daemon=True)
        self._worker_thread.start()

    def stop(self) -> None:
        """햅틱 매니저 정지 및 리소스 정리"""
        self._is_running = False
        self._connected = False
        
        # 공식 SDK 정리
        if self.sink.kind == "bhaptics" and HAS_BHAPTICS_SDK:
            try:
                bhaptics_python.stop_all()
                bhaptics_python.close()
            except Exception:
                pass
                
        # WebSocket 정리
        if self.ws:
            try:
                self.ws.close()
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

    def _run_backend(self) -> None:
        """선택된 방식(SDK 또는 WebSocket)에 따라 백엔드 루프 실행"""
        if self.sink.kind == "bhaptics":
            self._run_sdk_backend()
        else:
            self._run_websocket_backend()

    # ==========================================
    # 1. 공식 bhaptics-python SDK 백엔드
    # ==========================================
    def _run_sdk_backend(self) -> None:
        """공식 SDK asyncio 워커 루프"""
        if not HAS_BHAPTICS_SDK:
            self._notify_status(False, "오류: bhaptics-python 패키지가 설치되지 않았습니다.")
            return

        if not self.sink.app_id.strip() or not self.sink.api_key.strip():
            self._notify_status(False, "App ID / API Key를 입력하고 설정을 저장하세요.")
            print("[Haptics] App ID 또는 API Key가 비어 있어 SDK 초기화를 대기합니다.")
            
        self._async_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._async_loop)
        
        try:
            self._async_loop.run_until_complete(self._sdk_main_loop())
        except Exception as e:
            self._notify_status(False, f"SDK 루프 오류: {e}")
        finally:
            self._async_loop.close()

    async def _sdk_main_loop(self) -> None:
        """SDK 초기화 및 큐 전송 비동기 루프"""
        app_id = self.sink.app_id.strip()
        api_key = self.sink.api_key.strip()
        
        if not app_id or not api_key:
            while self._is_running:
                await asyncio.sleep(1.0)
            return

        try:
            self._notify_status(False, "bHaptics SDK 초기화 중...")
            await bhaptics_python.registry_and_initialize(app_id, api_key, "")
            self._notify_status(True, f"bHaptics SDK 연결됨 ({self.sink.motor_count} 모터)")
            print(f"[Haptics] 공식 bhaptics-python SDK 초기화 완료! (App ID: {app_id})")
        except Exception as e:
            self._notify_status(False, f"SDK 초기화 실패: {e}")
            print(f"[Haptics] SDK 초기화 실패: {e}")

        # 모터 출력 루프
        while self._is_running:
            try:
                while not self._send_queue.empty():
                    item = self._send_queue.get_nowait()
                    if item.get("type") == "play_dot":
                        duration = item["duration"]
                        motors = item["motors"]
                        bhaptics_python.play_dot(0, duration, motors)
                await asyncio.sleep(0.01)
            except Exception:
                await asyncio.sleep(0.05)

    # ==========================================
    # 2. 레거시 WebSocket 백엔드
    # ==========================================
    def _run_websocket_backend(self) -> None:
        """bHaptics Player 로컬 WebSocket 서버 통신 워커"""
        print(f"[Haptics] 레거시 WebSocket 모드로 {self.ws_url} 연결 시도...")
        while self._is_running:
            try:
                self.ws = websocket.WebSocketApp(
                    self.ws_url,
                    on_open=self._on_ws_open,
                    on_message=self._on_ws_message,
                    on_error=self._on_ws_error,
                    on_close=self._on_ws_close
                )
                
                ws_sender_thread = threading.Thread(target=self._ws_queue_sender, daemon=True)
                ws_sender_thread.start()
                
                self.ws.run_forever(ping_interval=5, ping_timeout=2)
            except Exception as e:
                self._notify_status(False, f"WebSocket 재연결 대기: {e}")
            
            if self._is_running:
                time.sleep(3)

    def _ws_queue_sender(self) -> None:
        """WebSocket 전송 큐 처리"""
        while self._is_running and self._connected:
            try:
                item = self._send_queue.get(timeout=0.1)
                if item.get("type") == "ws_msg" and self.ws and self.ws.sock and self.ws.sock.connected:
                    self.ws.send(json.dumps(item["payload"]))
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[Haptics] WebSocket 메시지 송신 오류: {e}")

    def _on_ws_open(self, ws):
        print(f"[Haptics] bHaptics Player WebSocket 연결 성공 ({self.ws_url})")
        self._notify_status(True, "bHaptics Player 연결됨 (WebSocket)")
        register_msg = {
            "Register": [{
                "Key": "PochamsHaptics",
                "Project": {
                    "Tracks": [],
                    "Layout": {"Type": "Vest"}
                }
            }]
        }
        ws.send(json.dumps(register_msg))

    def _on_ws_message(self, ws, message):
        pass

    def _on_ws_error(self, ws, error):
        print(f"[Haptics] WebSocket 에러: {error}")
        self._notify_status(False, f"bHaptics 연결 에러: {error}")

    def _on_ws_close(self, ws, close_status_code, close_msg):
        print(f"[Haptics] WebSocket 연결 끊김: {close_status_code} - {close_msg}")
        self._notify_status(False, "bHaptics 연결 끊김 (재연결 중...)")

    # ==========================================
    # 3. 모터 매핑 및 햅틱 출력
    # ==========================================
    def _create_sdk_motor_array(self, front_20: List[int], back_20: List[int]) -> List[int]:
        """
        공식 SDK 포맷(정수 0~100 배열)으로 변환
        32모터: 16전면 + 16후면
        40모터: 20전면 + 20후면
        """
        f_gain = self.sink.front_gain
        b_gain = self.sink.back_gain

        if self.sink.motor_count == 32:
            # 20 -> 16 모터 다운샘플링 (4x5 그리드 중 가슴/복부 4x4 핵심 모터 추출)
            f16_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
            b16_indices = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]
            
            f16 = [int(np.clip(front_20[i] * f_gain, 0, 100)) for i in f16_indices]
            b16 = [int(np.clip(back_20[i] * b_gain, 0, 100)) for i in b16_indices]
            return f16 + b16
        else:
            # 40 모터 (전면 20 + 후면 20)
            f20_g = [int(np.clip(v * f_gain, 0, 100)) for v in front_20]
            b20_g = [int(np.clip(v * b_gain, 0, 100)) for v in back_20]
            return f20_g + b20_g

    def trigger_damage(self, level: str, damage_delta: float = 0.0, position_mode: str = "VestFront") -> None:
        """
        데미지 수준별 햅틱 피드백 전송
        level: "light", "medium", "heavy", "critical"
        """
        front_20 = [0] * 20
        back_20 = [0] * 20
        duration_ms = 200
        intensity = 50

        if level == "light":
            # 약공격: 가슴 중앙 4개 모터 집중
            intensity = 40
            duration_ms = 180
            for idx in [5, 6, 9, 10]:
                front_20[idx] = intensity

        elif level == "medium":
            # 중공격: 가슴 + 명치 + 상복부
            intensity = 70
            duration_ms = 280
            for idx in [4, 5, 6, 7, 8, 9, 10, 11, 13, 14]:
                front_20[idx] = intensity
            if position_mode == "All":
                for idx in [5, 6, 9, 10]:
                    back_20[idx] = int(intensity * 0.5)

        elif level == "heavy":
            # 강공격: 앞면 전체 20개 모터 + 등 잔류 진동
            intensity = 90
            duration_ms = 450
            front_20 = [intensity] * 20
            if position_mode in ["VestBack", "All"]:
                for idx in [4, 5, 6, 7, 8, 9, 10, 11]:
                    back_20[idx] = int(intensity * 0.7)

        elif level == "critical":
            # 치명타 / KO: 전신 100% 최대 파동
            intensity = 100
            duration_ms = 700
            front_20 = [100] * 20
            back_20 = [100] * 20

        # 위치 모드 단독 후면 반전
        if position_mode == "VestBack" and sum(back_20) == 0:
            back_20 = front_20
            front_20 = [0] * 20

        # 실시간 모터 상태 기록 (UI 시각화용)
        with self._state_lock:
            self.last_front_motors = front_20.copy()
            self.last_back_motors = back_20.copy()
            self.last_trigger_time = time.time()
            self.last_duration_ms = duration_ms
            self.last_level = level

        # 1. 공식 SDK 방식 전송
        if self.sink.kind == "bhaptics":
            motors = self._create_sdk_motor_array(front_20, back_20)
            try:
                self._send_queue.put_nowait({
                    "type": "play_dot",
                    "duration": duration_ms,
                    "motors": motors
                })
            except queue.Full:
                pass
                
        # 2. 레거시 WebSocket 방식 전송
        else:
            front_dots = [{"Index": i, "Intensity": int(np.clip(v * self.sink.front_gain, 0, 100))} for i, v in enumerate(front_20) if v > 0]
            back_dots = [{"Index": i, "Intensity": int(np.clip(v * self.sink.back_gain, 0, 100))} for i, v in enumerate(back_20) if v > 0]
            
            payload = {"Submit": []}
            if front_dots:
                payload["Submit"].append({
                    "Type": "dot",
                    "Key": f"Pochams_{level}_Front",
                    "Frame": {
                        "Position": "VestFront",
                        "DotPoints": front_dots,
                        "DurationMillis": duration_ms
                    }
                })
            if back_dots:
                payload["Submit"].append({
                    "Type": "dot",
                    "Key": f"Pochams_{level}_Back",
                    "Frame": {
                        "Position": "VestBack",
                        "DotPoints": back_dots,
                        "DurationMillis": duration_ms
                    }
                })
            try:
                self._send_queue.put_nowait({
                    "type": "ws_msg",
                    "payload": payload
                })
            except queue.Full:
                pass

        if self.on_haptic_trigger:
            try:
                self.on_haptic_trigger(level, intensity, duration_ms, front_20, back_20)
            except Exception as e:
                print(f"[Haptics] 트리거 콜백 오류: {e}")

    def get_current_motor_intensities(self) -> Tuple[List[float], List[float], str]:
        """UI 시각화를 위한 현재 감쇠된 40개 모터 실시간 강도(0~100) 및 레벨 반환"""
        with self._state_lock:
            if self.last_trigger_time <= 0:
                return [0.0] * 20, [0.0] * 20, "none"
            
            elapsed_ms = (time.time() - self.last_trigger_time) * 1000.0
            total_duration = float(self.last_duration_ms + 400)
            
            if elapsed_ms >= total_duration:
                return [0.0] * 20, [0.0] * 20, "none"
                
            decay = max(0.0, 1.0 - (elapsed_ms / total_duration))
            front = [v * decay for v in self.last_front_motors]
            back = [v * decay for v in self.last_back_motors]
            return front, back, self.last_level

    def stop_all(self) -> None:
        """모든 햅틱 진동 정지"""
        with self._state_lock:
            self.last_front_motors = [0] * 20
            self.last_back_motors = [0] * 20
            self.last_trigger_time = 0.0
            
        if self.sink.kind == "bhaptics" and HAS_BHAPTICS_SDK:
            try:
                bhaptics_python.stop_all()
            except Exception:
                pass
        else:
            payload = {"Submit": [{"Type": "turnOff", "Key": "all"}]}
            try:
                self._send_queue.put_nowait({"type": "ws_msg", "payload": payload})
            except Exception:
                pass
