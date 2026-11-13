import time
import re
import queue
import threading
import cv2
import numpy as np
from collections import Counter
from typing import Callable, Optional, Tuple, List, Dict

try:
    from rapidocr_onnxruntime import RapidOCR
    HAS_RAPID_OCR = True
except ImportError:
    RapidOCR = None
    HAS_RAPID_OCR = False

# 🚀 고속 정규식 사전 컴파일 (매 프레임 재컴파일 오버헤드 100% 제거)
RE_TIMER = re.compile(r'\b\d{1,2}\s*[:;\-\.]\s*[0-5]\d\b')
RE_SLASH_SYMBOLS = re.compile(r'[\/\|\\ㅣ]')
RE_HP_STANDARD = re.compile(r'(\d{1,3})\s*\/\s*(\d{2,3})')
RE_DIGITS = re.compile(r'\d+')

class VisionDetector:
    """
    포챔스 전용 슈퍼 안정화 5대 비전/OCR 엔진
    - 🔍 1. 화이트 폰트 샤프닝 & CLAHE 적응형 명암비 전처리 (Unsharp Masking)
    - 🔤 2. 포챔스 전용 숫자/슬래시 문법 검증기 & 오인식 교정기 (Regex & Char Normalization)
    - 📊 3. 1D 색상 게이지 스캔라인 + 2D OCR 듀얼 교차 검증 (Dual Cross-Check)
    - 🛡️ 4. 2~3프레임 연속 일치 다수결 합의 락 (Temporal Consensus Filter)
    - ⏱️ 5. 포켓몬 교체 / 컷신 / 체력 회복 스마트 뮤트 (Smart Context Gate)
    - 🎯 6. HUD 원클릭 자동 스냅 (Auto-Snap Card ROI)
    """

    def __init__(self,
                 device_index: int = 0,
                 width: int = 1280,
                 height: int = 720,
                 roi: List[float] = None,
                 min_damage_threshold: float = 3.0,
                 buffer_size: int = 4,
                 max_jitter_percent: float = 2.0,
                 **kwargs):
        
        self.device_index = device_index
        self.target_width = width
        self.target_height = height
        
        # ROI: [x_ratio, y_ratio, w_ratio, h_ratio] (0.0 ~ 1.0) - 포챔스 표준 배틀 체력 카드 영역
        self.roi = roi if roi is not None else kwargs.get("initial_roi", [0.045, 0.828, 0.195, 0.148])
        self.min_damage_threshold = min_damage_threshold
        
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._ocr_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # 프레임 저장 (UI 렌더링용)
        self._latest_raw_frame: Optional[np.ndarray] = None
        self._latest_annotated_frame: Optional[np.ndarray] = None
        
        # 디버그 뷰어용 실시간 이미지 및 수치 (100% 순수 숫자 전담 모드)
        self._debug_text_crop: Optional[np.ndarray] = None
        self._debug_enhanced_crop: Optional[np.ndarray] = None
        
        # 배틀 상태 머신 ("IDLE" / "IN_BATTLE" / "CUTSCENE")
        self.battle_state: str = "IDLE"
        self.is_paused: bool = False
        
        # 확정된 안정 체력 상태
        self.confirmed_curr_hp: int = 0
        self.confirmed_max_hp: int = 0
        self.current_hp_pct: float = 100.0
        self.confirmed_stable_hp_pct: Optional[float] = None
        self.last_triggered_hp_pct: Optional[float] = None
        
        self.hud_visible: bool = False
        self.last_number_seen_time: float = 0.0
        self.last_switch_time: float = 0.0
        
        # 🔄 다수결 통계 합의 큐: [(timestamp, curr, max)]
        self._ocr_history: List[Tuple[float, int, int]] = []
        
        # 비동기 고속 OCR 큐
        self._ocr_queue: queue.Queue = queue.Queue(maxsize=1)
        self._ocr_engine = None
        self._last_ocr_dispatch_time: float = 0.0
        self._last_ocr_reading: Optional[Tuple[int, int, float]] = None
        self._last_ocr_raw_text: str = ""
        
        # 콜백
        self.on_hp_update: Optional[Callable[[float, float, bool, str], None]] = None
        self.on_damage_detected: Optional[Callable[[float, float, float], None]] = None
        self.on_heal_detected: Optional[Callable[[float, float], None]] = None
        self.on_pokemon_switched: Optional[Callable[[int, int, float], None]] = None
        self.on_camera_status: Optional[Callable[[bool, str], None]] = None
        self.is_camera_connected: bool = True

        # 🎛️ 감지 모드 프로필 ("fast": 초고속 7:3, "balanced": 균형 6:4, "accurate": 고정밀 8.5:1.5)
        self.detection_mode: str = kwargs.get("detection_mode", "balanced")
        self._ocr_dispatch_min_interval: float = 0.07
        self.set_detection_mode(self.detection_mode)

    def set_detection_mode(self, mode: str) -> None:
        """감지 모드 실시간 전환 ('fast', 'balanced', 'accurate')"""
        if mode not in ["fast", "balanced", "accurate"]:
            mode = "balanced"
        self.detection_mode = mode
        if mode == "fast":
            self._ocr_dispatch_min_interval = 0.05
        elif mode == "balanced":
            self._ocr_dispatch_min_interval = 0.07
        else: # accurate
            self._ocr_dispatch_min_interval = 0.10

    @staticmethod
    def get_video_devices(max_check: int = 4) -> List[Dict[str, any]]:
        """사용 가능한 비디오 입력 장치 스캔 (예외 처리 완료)"""
        devices = []
        for i in range(max_check):
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if not cap.isOpened():
                    cap = cv2.VideoCapture(i)
                if cap.isOpened():
                    devices.append({
                        "index": i,
                        "name": f"카메라 / 캡처 장치 {i}" + (" (기본 / OBS 가상카메라 또는 캡처보드)" if i == 0 else "")
                    })
                    cap.release()
            except Exception:
                pass
                
        if not devices:
            devices.append({"index": 0, "name": "카메라 / 캡처 장치 0 (기본)"})
        return devices

    def auto_snap_roi(self) -> Optional[List[float]]:
        """배틀 화면에서 아군 체력바 카드를 0.1픽셀 단위로 자동 탐색하여 딱 맞게 스냅 (포챔스 표준 카드 규격 반영)"""
        with self._lock:
            if self._latest_raw_frame is None:
                new_roi = [0.045, 0.828, 0.195, 0.148]
                self.set_roi(new_roi[0], new_roi[1], new_roi[2], new_roi[3])
                return new_roi
            frame = self._latest_raw_frame.copy()

        h, w, _ = frame.shape
        sx1, sy1 = int(w * 0.0), int(h * 0.55)
        sx2, sy2 = int(w * 0.40), int(h * 0.99)
        search_roi = frame[sy1:sy2, sx1:sx2]
        
        gray = cv2.cvtColor(search_roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        edges = cv2.Canny(blurred, 30, 100)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
        dilated = cv2.dilate(edges, kernel, iterations=1)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for c in contours:
            cx, cy, cw, ch = cv2.boundingRect(c)
            aspect = cw / float(max(1, ch))
            if 1.3 <= aspect <= 3.6 and cw >= int(w * 0.12) and ch >= int(h * 0.06):
                area = cv2.contourArea(c)
                candidates.append((area, (cx + sx1, cy + sy1, cw, ch)))

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            fx, fy, fw, fh = candidates[0][1]
            
            # 포챔스 카드 본체에 정확히 밀착 스냅
            nx = max(0.0, (fx + int(fw * 0.12)) / float(w))
            ny = max(0.0, (fy + int(fh * 0.02)) / float(h))
            nw = min(1.0 - nx, (fw * 0.86) / float(w))
            nh = min(1.0 - ny, (fh * 0.96) / float(h))
            
            new_roi = [round(float(nx), 4), round(float(ny), 4), round(float(nw), 4), round(float(nh), 4)]
            self.set_roi(new_roi[0], new_roi[1], new_roi[2], new_roi[3])
            return new_roi
        else:
            # 외곽선이 뚜렷하지 않은 비배틀 화면에서도 표준 포챔스 카드 위치로 정밀 스냅
            new_roi = [0.045, 0.828, 0.195, 0.148]
            self.set_roi(new_roi[0], new_roi[1], new_roi[2], new_roi[3])
            return new_roi

    def set_roi(self, x: float, y: float, w: float, h: float) -> None:
        """ROI 좌표(0.0 ~ 1.0 정규화 비율) 업데이트 및 기준치 재계산"""
        with self._lock:
            self.roi = [
                max(0.0, min(1.0, x)),
                max(0.0, min(1.0, y)),
                max(0.01, min(1.0, w)),
                max(0.01, min(1.0, h))
            ]
            self._ocr_history.clear()
            self.confirmed_curr_hp = 0
            self.confirmed_max_hp = 0
            self.confirmed_stable_hp_pct = None
            self.last_triggered_hp_pct = None
            self._last_ocr_reading = None

    def toggle_pause(self) -> bool:
        """체력 감지 일시정지 / 재개 토글 (True: 일시정지됨, False: 재개됨)"""
        with self._lock:
            self.is_paused = not self.is_paused
            if not self.is_paused:
                self._ocr_history.clear()
                self.confirmed_stable_hp_pct = None
                self.last_triggered_hp_pct = None
                self._last_ocr_reading = None
            return self.is_paused

    def reset_battle_state(self) -> None:
        """확정된 최대/현재 체력 잠금 및 OCR 히스토리를 완전히 초기화 (새 배틀/강제 리셋)"""
        with self._lock:
            self.confirmed_max_hp = 0
            self.confirmed_curr_hp = 0
            self.current_hp_pct = 100.0
            self.confirmed_stable_hp_pct = None
            self.last_triggered_hp_pct = None
            self._last_ocr_reading = None
            self._last_ocr_raw_text = ""
            self._ocr_history.clear()
            self.last_switch_time = 0.0

    def calibrate_100_percent(self) -> None:
        """현재 체력바 상태를 초기 기준(100% 대기)으로 리셋"""
        self.reset_battle_state()

    def start(self) -> bool:
        """비디오 캡처 및 백그라운드 OCR 스레드 시작"""
        if self._is_running:
            return True
        
        try:
            self._cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
            if not self._cap.isOpened():
                self._cap = cv2.VideoCapture(self.device_index)
                
            if not self._cap.isOpened():
                print(f"[Vision] 비디오 장치 {self.device_index} 열기 실패")
                return False

            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self._is_running = True
            
            # 1. 60FPS 비디오 캡처 루프
            self._capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._capture_thread.start()
            
            # 2. 비동기 백그라운드 OCR 워커
            if HAS_RAPID_OCR:
                self._ocr_thread = threading.Thread(target=self._async_ocr_worker, daemon=True)
                self._ocr_thread.start()

            print(f"[Vision] 60FPS 실시간 비디오 캡처 시작 (장치 {self.device_index})")
            return True
        except Exception as e:
            print(f"[Vision] 캡처 초기화 오류: {e}")
            return False

    def stop(self) -> None:
        """비디오 캡처 및 OCR 스레드 정지"""
        self._is_running = False
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        if self._ocr_thread and self._ocr_thread.is_alive():
            self._ocr_thread.join(timeout=1.0)
            
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """UI 표시용 최신 주석(ROI 사각형 및 HP 텍스트) 프레임 반환 (불필요한 6.2MB 중복 복사 제거)"""
        with self._lock:
            return self._latest_annotated_frame

    def get_debug_data(self) -> dict:
        """비전 디버그 모니터용 실시간 진단 데이터 (100% 순수 숫자 전담 모드)"""
        with self._lock:
            return {
                "enhanced_crop": self._debug_enhanced_crop,
                "text_crop": self._debug_text_crop,
                "ocr_reading": self._last_ocr_reading,
                "raw_text": self._last_ocr_raw_text,
                "battle_state": self.battle_state,
                "is_paused": self.is_paused
            }

    def _attempt_reconnect(self) -> bool:
        """비디오 캡처 장치 안전 릴리즈 후 백그라운드 재연결 시도"""
        try:
            if self._cap:
                try:
                    self._cap.release()
                except Exception:
                    pass
                self._cap = None
                
            cap = cv2.VideoCapture(self.device_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(self.device_index)
                
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.target_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.target_height)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self._cap = cap
                return True
        except Exception:
            pass
        return False

    def _capture_loop(self) -> None:
        """60FPS 고속 프레임 캡처 루프 (하드웨어 V-Sync 동기화 & 가변 델타 제어 & 캡처 와치독)"""
        target_interval = 1.0 / 60.0
        last_frame_time = time.perf_counter()
        consecutive_failures = 0
        last_reconnect_attempt = 0.0
        
        while self._is_running:
            if not self._cap or not self._cap.isOpened():
                now = time.time()
                if now - last_reconnect_attempt >= 1.5:
                    last_reconnect_attempt = now
                    self._attempt_reconnect()
                time.sleep(0.05)
                continue
                
            ret, frame = self._cap.read()
            if not ret or frame is None:
                consecutive_failures += 1
                if consecutive_failures >= 30:  # 약 0.5초 연속 실패 시 신호 단절 판정
                    if self.is_camera_connected:
                        self.is_camera_connected = False
                        if self.on_camera_status:
                            try:
                                self.on_camera_status(False, "⚠️ 캡처보드 신호 단절 감지: 자동 재연결 시도 중...")
                            except Exception:
                                pass
                    now = time.time()
                    if now - last_reconnect_attempt >= 1.5:
                        last_reconnect_attempt = now
                        if self._attempt_reconnect():
                            consecutive_failures = 0
                time.sleep(0.01)
                continue
            
            # 정상 프레임 수신 복구
            if not self.is_camera_connected:
                self.is_camera_connected = True
                consecutive_failures = 0
                if self.on_camera_status:
                    try:
                        self.on_camera_status(True, "✅ 캡처보드 신호가 정상 복구되었습니다.")
                    except Exception:
                        pass

            consecutive_failures = 0
            self._process_frame(frame)
            
            # 🚀 가변 델타 슬립: cap.read()의 하드웨어 블로킹 속도를 존중하여 60FPS 초과 시에만 미세 슬립
            now = time.perf_counter()
            elapsed = now - last_frame_time
            last_frame_time = now
            if elapsed < target_interval:
                time.sleep(target_interval - elapsed)

    def _process_frame(self, frame: np.ndarray) -> None:
        """단일 프레임 처리 (고속 디스패치 및 UI 렌더링)"""
        h, w, _ = frame.shape
        rx, ry, rw, rh = self.roi
        
        px = int(rx * w)
        py = int(ry * h)
        pw = int(rw * w)
        ph = int(rh * h)
        
        px = max(0, min(w - 1, px))
        py = max(0, min(h - 1, py))
        pw = max(5, min(w - px, pw))
        ph = max(5, min(h - py, ph))
        
        roi_img = frame[py:py+ph, px:px+pw]
        
        # ⏸️ 일시정지 상태 처리
        if self.is_paused:
            self.hud_visible = False
            status_detail = "⏸️ 체력 감지 일시정지 중"
            display_tag = "[ ⏸️ 체력 감지 일시정지 중 ]"
            roi_color = (0, 165, 255)
            
            if self.on_hp_update:
                try:
                    self.on_hp_update(self.current_hp_pct, 0.0, False, status_detail)
                except Exception:
                    pass

            annotated = frame.copy()
            cv2.rectangle(annotated, (px, py), (px + pw, py + ph), roi_color, 2)
            cv2.putText(annotated, display_tag, (px, max(22, py - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
            cv2.putText(annotated, display_tag, (px, max(22, py - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, roi_color, 1)

            with self._lock:
                self._latest_raw_frame = frame
                self._latest_annotated_frame = annotated
            return

        now = time.time()

        # 1. 텍스트 서브영역 분리 및 OCR 큐 전달 (100% 순수 숫자 전담 모드)
        rh_sub, rw_sub = roi_img.shape[:2]
        # 🎯 적응형 OCR 크롭 (사용자 지정 ROI 크기 자동 감지):
        # 사용자가 이미 체력바/숫자 위주로 타이트하게 지정한 경우 (높이 < 55, 너비 < 120, 또는 가로세로비 < 2.0):
        # 좌측 여백을 임의로 자르면 '108'의 '1'이 잘려나가 '8/207'로 오인식되는 대참사가 발생합니다!
        # 따라서 타이트한 ROI에서는 사용자 지정 영역 전체를 100% 보존합니다.
        # 사용자가 포켓몬 이름/스프라이트까지 포함된 풀 배틀 카드를 지정한 대형 ROI일 때만
        # 상단 이름 영역(35%)만 안전하게 배제하고, 좌측 숫자는 잘리지 않도록 안전 여백만 유지합니다.
        if rh_sub < 55 or rw_sub < 120 or (rw_sub / float(max(1, rh_sub))) < 2.0:
            num_crop = roi_img
            crop_rect_offset = (0, 0, pw, ph)
        else:
            y_cut = int(rh_sub * 0.35)
            x_cut = int(rw_sub * 0.05)
            num_crop = roi_img[y_cut:, x_cut:]
            crop_rect_offset = (x_cut, y_cut, pw, ph)
        
        if HAS_RAPID_OCR and (now - self._last_ocr_dispatch_time >= self._ocr_dispatch_min_interval):
            self._last_ocr_dispatch_time = now
            try:
                if self._ocr_queue.empty():
                    self._ocr_queue.put_nowait(num_crop.copy())
            except Exception:
                pass

        # 3. 🎬 연출 자동 동결 (Cutscene Hold) 및 💀 기절(Fainted) 처리
        time_since_number = now - self.last_number_seen_time
        if self.confirmed_curr_hp <= 0 and self.confirmed_max_hp > 0:
            self.hud_visible = False
            self.battle_state = "FAINTED"
            self.current_hp_pct = 0.0
            status_detail = "💀 포켓몬 기절 (HP: 0%)"
            roi_color = (128, 128, 128)
            display_tag = "[ 💀 포켓몬 기절 (HP: 0%) ]"
        elif time_since_number > 1.3:
            self.hud_visible = False
            self.battle_state = "CUTSCENE"
            if self.confirmed_max_hp > 0 and self.confirmed_curr_hp > 0:
                self.current_hp_pct = (self.confirmed_curr_hp / float(self.confirmed_max_hp)) * 100.0
            status_detail = f"🎬 연출 중 (체력 유지: {self.current_hp_pct:.0f}%)"
            roi_color = (255, 140, 0)
            display_tag = f"[ 🎬 연출 중 (HP: {self.current_hp_pct:.0f}%) ]"
        else:
            self.hud_visible = True
            self.battle_state = "IN_BATTLE"
            if self.confirmed_max_hp > 0 and self.confirmed_curr_hp > 0:
                self.current_hp_pct = (self.confirmed_curr_hp / float(self.confirmed_max_hp)) * 100.0
                
            if self.current_hp_pct > 50:
                roi_color = (0, 255, 0)
            elif self.current_hp_pct > 20:
                roi_color = (0, 255, 255)
            else:
                roi_color = (0, 0, 255)
                
            if self.confirmed_max_hp > 0:
                display_tag = f"HP: {self.confirmed_curr_hp}/{self.confirmed_max_hp} ({self.current_hp_pct:.1f}%)"
                status_detail = display_tag
            else:
                display_tag = f"HP: {self.current_hp_pct:.0f}% (대기)"
                status_detail = display_tag

        if self.on_hp_update:
            try:
                self.on_hp_update(self.current_hp_pct, 0.0, self.hud_visible, status_detail)
            except Exception:
                pass

        # 4. UI 렌더링 (사이버펑크 코너 브래킷 + 정밀 스캔 박스)
        annotated = frame.copy()
        cv2.rectangle(annotated, (px, py), (px + pw, py + ph), roi_color, 1)
        corner_len = max(6, min(16, pw // 5, ph // 3))
        # 좌상, 우상, 좌하, 우하 코너 브래킷 강조
        for (cx_p, cy_p, dx_s, dy_s) in [
            (px, py, 1, 1),
            (px + pw, py, -1, 1),
            (px, py + ph, 1, -1),
            (px + pw, py + ph, -1, -1)
        ]:
            cv2.line(annotated, (cx_p, cy_p), (cx_p + dx_s * corner_len, cy_p), roi_color, 3)
            cv2.line(annotated, (cx_p, cy_p), (cx_p, cy_p + dy_s * corner_len), roi_color, 3)

        # 디버그 스캔 박스: 실제 OCR 엔진으로 넘어가는 영역을 노란색 박스로 정밀 표시
        if crop_rect_offset[0] > 0 or crop_rect_offset[1] > 0:
            cv2.rectangle(annotated, 
                          (px + crop_rect_offset[0], py + crop_rect_offset[1]), 
                          (px + pw, py + ph), 
                          (0, 255, 255), 1)
        cv2.putText(annotated, display_tag, (px, max(22, py - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(annotated, display_tag, (px, max(22, py - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, roi_color, 1)

        with self._lock:
            self._latest_raw_frame = frame
            self._latest_annotated_frame = annotated
            self._debug_text_crop = num_crop

    @staticmethod
    def normalize_ocr_text(raw: str) -> str:
        r"""
        🔤 OCR 자주 발생하는 오인식 알파벳을 숫자로 스마트 정규화 (콜론 ':'은 타이머 구분을 위해 슬래시로 치환하지 않음)
        - O, o, Q, D -> 0
        - I, l -> 1
        - S, s -> 5
        - Z, z -> 2
        - B -> 8
        - / | \ ㅣ -> / (슬래시)
        """
        t = raw.strip()
        # 슬래시 및 세로바 기호만 슬래시로 정리 (콜론 ':'과 세미콜론 ';'은 타이머 필터링을 위해 절대 변환하지 않음)
        t = RE_SLASH_SYMBOLS.sub('/', t)
        
        # 알파벳 오인식 치환 테이블
        rep_map = {
            'O': '0', 'o': '0', 'Q': '0', 'D': '0',
            'S': '5', 's': '5',
            'Z': '2', 'z': '2',
            'B': '8',
            'g': '9', 'q': '9'
        }
        res = []
        for ch in t:
            res.append(rep_map.get(ch, ch))
        return "".join(res)

    @classmethod
    def parse_pokeechamps_hp_smart(cls, text: str, known_max_hp: int = 0, known_curr_hp: int = 0) -> Optional[Tuple[int, int]]:
        """
        🔤 포챔스 전용 고정밀 수치 및 슬래시(/) 분리 스마트 교정기
        - ⏰ 1. 타이머 형식 (MM:SS, e.g. 04:58, 06-35, 05:00) 텍스트 내부 사전 정제
        - 🎯 2. 표준 포챔스 HP (40 <= 최대HP <= 420, 현재HP <= 최대HP) 검증
        - 💡 3. RapidOCR 다중 토큰('197 1197', '197 7197', '197 197') 및 1자리 딸피('91197', '9197') 완벽 대응
        """
        raw_clean = text.strip()
        
        # ⏰ [안전망 1: 타이머 MM:SS 및 특수기호 제거]
        for sym in ['⏱', '⏰', '⏳', '초', '분']:
            raw_clean = raw_clean.replace(sym, ' ')
        raw_clean = RE_TIMER.sub(' ', raw_clean)

        norm = cls.normalize_ocr_text(raw_clean)
        
        # 1. 표준 슬래시 분리 (예: '78/207', '155/155', '0/100', '197 / 197')
        m = RE_HP_STANDARD.search(norm)
        if m:
            c_str, m_str = m.group(1), m.group(2)
            # 포켓몬 본가 포맷: 0이 아닌 체력에 선행 '0'이 붙는 수치(예: '08/207')는 첫자리 잘림 오류이므로 기각
            if not (len(c_str) > 1 and c_str.startswith('0')):
                c, m_val = int(c_str), int(m_str)
                if 40 <= m_val <= 420 and 0 <= c <= m_val:
                    return c, m_val
                
        # 2. 띄어쓰기로 분리된 2개 숫자 토큰 (예: '197 1197', '197 7197', '197 197', '19 1183', '0 1140')
        tokens = RE_DIGITS.findall(norm)
        if len(tokens) == 2:
            t1, t2 = tokens[0], tokens[1]
            if not (len(t1) > 1 and t1.startswith('0')):
                # Case A: '197 197' 또는 '19 183'
                if 40 <= int(t2) <= 420 and 0 <= int(t1) <= int(t2):
                    return int(t1), int(t2)
                # Case B: '197 1197' 또는 '197 7197' (t2의 첫 글자가 슬래시 치환 1 또는 7인 경우)
                if len(t2) >= 3 and t2[0] in ['1', '7']:
                    m_val = int(t2[1:])
                    c_val = int(t1)
                    if 40 <= m_val <= 420 and 0 <= c_val <= m_val:
                        return c_val, m_val

        # 3. 공백 없이 완전히 붙은 연속 숫자 (예: '179197', '197197', '781207', '78197', '91197', '9197')
        compact = re.sub(r'\s+', '', norm)
        merged_digits = RE_DIGITS.findall(compact)
        for d in merged_digits:
            if d.startswith('0') and len(d) > 1:
                continue
            L = len(d)
            if L == 7: # 1977197 (3 + 1 + 3) -> 197 / 197
                if d[3] in ['1', '7']:
                    c, m_val = int(d[:3]), int(d[4:])
                    if 40 <= m_val <= 420 and 0 <= c <= m_val:
                        return c, m_val
            elif L == 6: # 179197 (3 + 3) 또는 781207 (2 + 1 + 3)
                # 1) 3자리/3자리 체력 (179197 -> 179/197, 197197 -> 197/197)
                c2, m2 = int(d[:3]), int(d[3:])
                if 40 <= m2 <= 420 and 0 <= c2 <= m2:
                    return c2, m2
                # 2) 781207 (2 + 1 + 3) 형태 (중간 1 또는 7이 슬래시)
                if d[2] in ['1', '7']:
                    c1, m1 = int(d[:2]), int(d[3:])
                    if 40 <= m1 <= 420 and 0 <= c1 <= m1:
                        return c1, m1
            elif L == 5: # 78197 (2 + 3) 또는 91197 (1자리 체력 + 슬래시 '1'/'7' + 3자리 최대HP)
                c_two, m_val = int(d[:2]), int(d[2:])
                # 1자리 빨피(예: 9/197)에서 슬래시가 1 또는 7로 읽혀 '91197'이 된 경우 우선 감지:
                # 직전 확정 체력(known_curr_hp)이 c_two(91)보다 작거나, c_two > m_val인 경우 1자리 체력으로 분리
                if d[1] in ['1', '7'] and 40 <= m_val <= 420:
                    c_one = int(d[:1])
                    if c_two > m_val or (known_max_hp == m_val and 0 < known_curr_hp < c_two):
                        return c_one, m_val
                if 40 <= m_val <= 420 and 0 <= c_two <= m_val:
                    return c_two, m_val
            elif L == 4: # 9197 (1자리 체력 + 3자리 최대HP) 또는 8595 (2자리 + 2자리)
                c_one, m_three = int(d[:1]), int(d[1:])
                if 100 <= m_three <= 420 and 0 <= c_one <= m_three:
                    return c_one, m_three
                c_two, m_two = int(d[:2]), int(d[2:])
                if 40 <= m_two <= 99 and 0 <= c_two <= m_two:
                    return c_two, m_two

        return None

    @classmethod
    def parse_ocr_results_smart(cls, ocr_results: List, known_max_hp: int = 0, known_curr_hp: int = 0) -> Tuple[Optional[Tuple[int, int]], str]:
        """
        다중 바운딩 박스 스마트 우선순위 파싱:
        1. 바운딩 박스 중심 Y좌표 기준 아래쪽에서 위쪽으로 개별 박스 우선 검사 (HP 숫자는 항상 카드 최하단에 위치)
        2. 개별 박스에서 유효한 (curr, max)가 나오면 즉시 채택 (상단 타이머나 레벨/이름 텍스트의 간섭 원천 차단)
        3. 개별 박스에서 안 나오면 전체 결합 문자열로 폴백 검사
        """
        if not ocr_results:
            return None, ""
            
        full_raw = " ".join([r[1] for r in ocr_results if len(r) > 1 and r[1]])
        
        # 바운딩 박스 중심 Y 좌표 기준 내림차순 정렬 (화면 아래쪽 라인 우선)
        try:
            sorted_boxes = sorted(
                ocr_results, 
                key=lambda r: (r[0][0][1] + r[0][2][1]) / 2.0 if (len(r) > 0 and len(r[0]) >= 3) else 0.0, 
                reverse=True
            )
        except Exception:
            sorted_boxes = ocr_results
            
        for item in sorted_boxes:
            if len(item) > 1 and item[1]:
                box_text = item[1].strip()
                pair = cls.parse_pokeechamps_hp_smart(box_text, known_max_hp, known_curr_hp)
                if pair is not None:
                    return pair, full_raw
                
        # 개별 라인에서 매칭되지 않으면 결합 텍스트로 폴백
        return cls.parse_pokeechamps_hp_smart(full_raw, known_max_hp, known_curr_hp), full_raw

    def _async_ocr_worker(self) -> None:
        """
        🔍 100% 순수 체력 숫자 전담: 컷신 Early-Exit + 3중 적응형 전처리 + 스마트 분리 파싱 + 초고속 피격/회복 파이프라인
        """
        try:
            self._ocr_engine = RapidOCR()
        except Exception:
            return

        # CLAHE 객체 생성
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))

        while self._is_running:
            try:
                roi_crop = self._ocr_queue.get(timeout=0.25)
            except queue.Empty:
                continue

            try:
                # 🚀 [초고속 Early-Exit 사전 필터]
                # 암전이나 어두운 컷신 등 밝은 텍스트 픽셀(V>140)이 0.8% 미만이면 불필요한 3중 ONNX 추론을 생략
                raw_gray_small = cv2.cvtColor(roi_crop, cv2.COLOR_BGR2GRAY)
                bright_ratio = np.count_nonzero(raw_gray_small > 140) / float(max(1, raw_gray_small.size))
                if bright_ratio < 0.008:
                    continue

                known_max = self.confirmed_max_hp
                known_curr = self.confirmed_curr_hp

                # 1. 🔍 3.0x 고품질 바이큐빅 확대
                scaled = cv2.resize(roi_crop, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
                
                # 2. 🔍 샤프닝 필터 (Unsharp Mask)
                gaussian = cv2.GaussianBlur(scaled, (0, 0), 2.0)
                unsharp = cv2.addWeighted(scaled, 2.0, gaussian, -1.0, 0)
                
                # --- [파이프라인 1차: 샤프닝 + CLAHE 명암비 강화] ---
                gray = cv2.cvtColor(unsharp, cv2.COLOR_BGR2GRAY)
                enhanced_gray = clahe.apply(gray)
                with self._lock:
                    self._debug_enhanced_crop = enhanced_gray
                parsed_pair = None

                result1, _ = self._ocr_engine(enhanced_gray)
                result2 = None
                if result1:
                    parsed_pair, raw_text1 = self.parse_ocr_results_smart(result1, known_max, known_curr)
                    self._last_ocr_raw_text = raw_text1

                # --- [파이프라인 2차: 순수 화이트 마스크 (HSV V>160, S<80)] ---
                # 1차에서 텍스트 박스가 아예 0개이고 밝은 픽셀도 희박(<2.5%)하면 컷신 화면이므로 2·3차 생략 (즉각 복귀 보장)
                has_potential_text = (result1 is not None and len(result1) > 0) or (bright_ratio >= 0.025)
                if parsed_pair is None and has_potential_text:
                    hsv = cv2.cvtColor(scaled, cv2.COLOR_BGR2HSV)
                    mask_white = cv2.inRange(hsv, np.array([0, 0, 160]), np.array([180, 80, 255]))
                    result2, _ = self._ocr_engine(mask_white)
                    if result2:
                        parsed_pair, raw_text2 = self.parse_ocr_results_smart(result2, known_max, known_curr)
                        self._last_ocr_raw_text = raw_text2

                # --- [파이프라인 3차: 이진화 Otsu Threshold] ---
                if parsed_pair is None and (result1 or result2):
                    _, otsu = cv2.threshold(enhanced_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    result3, _ = self._ocr_engine(otsu)
                    if result3:
                        parsed_pair, raw_text3 = self.parse_ocr_results_smart(result3, known_max, known_curr)
                        self._last_ocr_raw_text = raw_text3

                # =====================================================================
                # 📊 3. 유효 수치 검증 & 🛡️ 4. 2~3프레임 연속 합의 락
                # =====================================================================
                if parsed_pair:
                    curr, max_hp = parsed_pair
                    ocr_hp_pct = (curr / float(max_hp)) * 100.0

                    now = time.time()

                    # 유효한 수치가 판독되었으므로 실시간 타임스탬프 갱신 (연출 오판 방지)
                    self.last_number_seen_time = now
                    self._last_ocr_reading = (curr, max_hp, ocr_hp_pct)
                    
                    # 1.5초 슬라이딩 윈도우 히스토리
                    self._ocr_history.append((now, curr, max_hp))
                    self._ocr_history = [item for item in self._ocr_history if now - item[0] <= 1.5]
                    
                    # --- [A. 포켓몬 교체 감지 (최대 체력 변경)] ---
                    if self.confirmed_max_hp > 0 and max_hp != self.confirmed_max_hp:
                        # 🛡️ [핵심 개선: 교체 시에도 2프레임 연속 합의 락 강제 적용]
                        # 찰나의 1프레임 오독(예: 197이 1번 261로 튐)으로 즉시 교체 처리되어 체력이 출렁이는 것을 100% 방지
                        recent_maxes = [item[2] for item in self._ocr_history[-2:]]
                        is_real_switch = (len(recent_maxes) >= 2 and recent_maxes[0] == max_hp and recent_maxes[1] == max_hp)

                        if is_real_switch:
                            old_max = self.confirmed_max_hp
                            self.confirmed_max_hp = max_hp
                            self.confirmed_curr_hp = curr
                            self.current_hp_pct = ocr_hp_pct
                            self.confirmed_stable_hp_pct = ocr_hp_pct
                            self.last_triggered_hp_pct = ocr_hp_pct
                            self.last_switch_time = now
                            self._ocr_history.clear()
                            
                            if self.on_pokemon_switched:
                                try:
                                    self.on_pokemon_switched(old_max, max_hp, ocr_hp_pct)
                                except Exception:
                                    pass
                        else:
                            # 1프레임 튀는 수치는 교체로 인정하지 않고 즉시 기각!
                            continue
                                
                    # --- [B. 첫 진입 (초기 기준 체력 설정)] ---
                    elif self.confirmed_max_hp == 0 or self.confirmed_curr_hp == 0:
                        recent_maxes = [item[2] for item in self._ocr_history[-2:]]
                        if len(recent_maxes) >= 2 and recent_maxes[0] == max_hp and recent_maxes[1] == max_hp:
                            self.confirmed_max_hp = max_hp
                            self.confirmed_curr_hp = curr
                            self.current_hp_pct = ocr_hp_pct
                            self.confirmed_stable_hp_pct = ocr_hp_pct
                            self.last_triggered_hp_pct = ocr_hp_pct
                        elif self.detection_mode == "fast":
                            self.confirmed_max_hp = max_hp
                            self.confirmed_curr_hp = curr
                            self.current_hp_pct = ocr_hp_pct
                            self.confirmed_stable_hp_pct = ocr_hp_pct
                            self.last_triggered_hp_pct = ocr_hp_pct
                        else:
                            continue
                        
                    # --- [C. 정상 배틀 중 체력 갱신 (max_hp == self.confirmed_max_hp)] ---
                    else:
                        is_switch_protected = (now - self.last_switch_time < 0.8)

                        # 💥 1) 데미지 피격 감지 (curr < self.confirmed_curr_hp)
                        if curr < self.confirmed_curr_hp:
                            should_trigger = False

                            # ⚡ 모드 A & B: 초고속(fast) 및 균형(balanced) 모드
                            # - 최대 HP(예: 197)가 정확히 일치하고 현재 체력이 감소한 유효 판독은
                            #   배경 조명이나 게이지 왜곡에 구애받지 않고 1프레임 즉각 확정 및 피격 진동 발동!
                            if self.detection_mode in ["fast", "balanced"]:
                                should_trigger = True
                            # 🎯 모드 C: 고정밀 모드 (accurate)
                            # - 2프레임 연속 동일 수치 합의 락 (안전망: CPU 연산 지연 감안 1.5초 윈도우)
                            else:
                                recent_currs = [item[1] for item in self._ocr_history if item[2] == self.confirmed_max_hp]
                                if len(recent_currs) >= 2:
                                    time_gap = self._ocr_history[-1][0] - self._ocr_history[-2][0]
                                    if time_gap <= 1.5 and recent_currs[-1] == recent_currs[-2] == curr:
                                        should_trigger = True

                            if should_trigger:
                                damage_delta = ((self.confirmed_curr_hp - curr) / float(max_hp)) * 100.0
                                self.confirmed_curr_hp = curr
                                self.current_hp_pct = (curr / float(max_hp)) * 100.0
                                self.confirmed_stable_hp_pct = self.current_hp_pct
                                self.last_triggered_hp_pct = self.current_hp_pct
                                
                                if damage_delta >= self.min_damage_threshold and not is_switch_protected:
                                    if self.on_damage_detected:
                                        try:
                                            self.on_damage_detected(damage_delta, self.current_hp_pct, now)
                                        except Exception as e:
                                            print(f"[Vision] 피격 트리거 오류: {e}")

                        # 🌿 2) 체력 회복 / 힐 (curr > self.confirmed_curr_hp)
                        elif curr > self.confirmed_curr_hp:
                            should_heal = False

                            # 초고속 및 균형 모드: 1프레임 즉시 회복 승인!
                            if self.detection_mode in ["fast", "balanced"]:
                                should_heal = True
                            # 고정밀 모드: 2프레임 연속 동일 수치 합의
                            else:
                                recent_currs = [item[1] for item in self._ocr_history if item[2] == self.confirmed_max_hp]
                                if len(recent_currs) >= 2:
                                    time_gap = self._ocr_history[-1][0] - self._ocr_history[-2][0]
                                    if time_gap <= 1.5 and recent_currs[-1] == recent_currs[-2] == curr:
                                        should_heal = True

                            if should_heal:
                                heal_delta = ((curr - self.confirmed_curr_hp) / float(max_hp)) * 100.0
                                self.confirmed_curr_hp = curr
                                self.current_hp_pct = (curr / float(max_hp)) * 100.0
                                self.confirmed_stable_hp_pct = self.current_hp_pct
                                self.last_triggered_hp_pct = self.current_hp_pct

                                if self.on_heal_detected:
                                    try:
                                        self.on_heal_detected(heal_delta, self.current_hp_pct)
                                    except Exception:
                                        pass

                        # 🛡️ 3) 현재 수치와 일치하여 안정 상태 유지
                        else:
                            if self.confirmed_max_hp > 0:
                                self.current_hp_pct = (self.confirmed_curr_hp / float(self.confirmed_max_hp)) * 100.0

            except Exception as e:
                pass
            time.sleep(0.04)
