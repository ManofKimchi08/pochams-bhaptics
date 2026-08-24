import time
import re
import queue
import threading
import cv2
import numpy as np
from typing import Callable, Optional, Tuple, List, Dict

try:
    from rapidocr_onnxruntime import RapidOCR
    HAS_RAPID_OCR = True
except ImportError:
    RapidOCR = None
    HAS_RAPID_OCR = False

class VisionDetector:
    """
    포챔스 전용 숫자 최우선(Number-First Authority) 비전 분석기
    - 🔢 숫자 인식 최우선 권한: OCR로 읽힌 정확한 수치('현재HP / 최대HP')를 절대 권한으로 사용
    - 🎬 숫자 미인식 시 100% 연출 처리: 숫자가 안 보이면 연출 중으로 간주하여 진동 원천 차단 및 체력 동결
    - 🎯 HUD 원클릭 자동 스냅 (Auto-Snap Card ROI)
    - 🔍 실시간 비전 디버그 모니터 지원
    """

    def __init__(self,
                 device_index: int = 0,
                 width: int = 1280,
                 height: int = 720,
                 roi: List[float] = None,
                 min_damage_threshold: float = 3.0,
                 buffer_size: int = 6,
                 max_jitter_percent: float = 2.0,
                 confirm_frames: Optional[int] = None,
                 deadband_percent: Optional[float] = None,
                 **kwargs):
        
        self.device_index = device_index
        self.target_width = width
        self.target_height = height
        
        # ROI: [x_ratio, y_ratio, w_ratio, h_ratio] (0.0 ~ 1.0)
        self.roi = roi if roi is not None else [0.05, 0.65, 0.25, 0.12]
        self.min_damage_threshold = min_damage_threshold
        
        self._cap: Optional[cv2.VideoCapture] = None
        self._is_running = False
        self._capture_thread: Optional[threading.Thread] = None
        self._ocr_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # 프레임 저장 (UI 렌더링용)
        self._latest_raw_frame: Optional[np.ndarray] = None
        self._latest_annotated_frame: Optional[np.ndarray] = None
        
        # 디버그 뷰어용 실시간 마스크 이미지
        self._debug_hp_mask: Optional[np.ndarray] = None
        self._debug_text_crop: Optional[np.ndarray] = None
        self._debug_scanline_val: float = 0.0
        
        # 배틀 상태 머신 ("IDLE" / "IN_BATTLE" / "CUTSCENE")
        self.battle_state: str = "IDLE"
        self.is_paused: bool = False
        self.current_hp_pct: float = 100.0
        self.confirmed_stable_hp_pct: Optional[float] = None
        self.last_triggered_hp_pct: Optional[float] = None
        
        self.current_curr_hp: int = 0
        self.current_max_hp: int = 0
        self.hud_visible: bool = False
        self.last_number_seen_time: float = 0.0
        
        # 비동기 고속 OCR 큐
        self._ocr_queue: queue.Queue = queue.Queue(maxsize=1)
        self._ocr_engine = None
        self._last_ocr_dispatch_time: float = 0.0
        self._last_ocr_reading: Optional[Tuple[int, int, float]] = None
        self._last_ocr_raw_text: str = ""
        
        # 기하학적 박스 크기 고정 락
        self._box_history: List[Tuple[int, int, int, int]] = []
        self._locked_slot_box: Optional[Tuple[int, int, int, int]] = None
        
        # 콜백
        self.on_hp_update: Optional[Callable[[float, float, bool, str], None]] = None
        self.on_damage_detected: Optional[Callable[[float, float, float], None]] = None
        self.on_pokemon_switched: Optional[Callable[[int, int, float], None]] = None

    @staticmethod
    def get_video_devices(max_check: int = 4) -> List[Dict[str, any]]:
        """사용 가능한 비디오 입력 장치 스캔"""
        devices = []
        for i in range(max_check):
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap.isOpened():
                    name = f"카메라 / 캡처 장치 {i}"
                    if i == 0:
                        name += " (기본 / OBS 가상카메라 또는 캡처보드)"
                    devices.append({
                        "index": i,
                        "name": name
                    })
                    cap.release()
            except Exception:
                pass
        if not devices:
            devices.append({"index": 0, "name": "카메라 / 캡처 장치 0 (기본)"})
        return devices

    def auto_snap_card_roi(self) -> Optional[List[float]]:
        """
        🎯 1080p/720p 화면에서 포챔스 아군 체력바 카드를 0.1픽셀 단위로 자동 탐색하여 스냅
        """
        with self._lock:
            if self._latest_raw_frame is None:
                return None
            frame = self._latest_raw_frame.copy()

        h, w, _ = frame.shape
        sx1, sx2 = 0, int(w * 0.45)
        sy1, sy2 = int(h * 0.45), int(h * 0.98)
        search_crop = frame[sy1:sy2, sx1:sx2]
        
        hsv = cv2.cvtColor(search_crop, cv2.COLOR_BGR2HSV)
        
        mask_dark = cv2.inRange(hsv, np.array([0, 0, 10]), np.array([180, 100, 75]))
        mask_green = cv2.inRange(hsv, np.array([35, 70, 70]), np.array([85, 255, 255]))
        mask_yellow = cv2.inRange(hsv, np.array([20, 70, 70]), np.array([34, 255, 255]))
        mask_red = cv2.inRange(hsv, np.array([0, 70, 70]), np.array([10, 255, 255]))
        mask_blue_card = cv2.inRange(hsv, np.array([100, 60, 60]), np.array([140, 255, 255]))
        mask_all = cv2.bitwise_or(mask_dark, cv2.bitwise_or(mask_green, cv2.bitwise_or(mask_yellow, cv2.bitwise_or(mask_red, mask_blue_card))))

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 10))
        closed = cv2.morphologyEx(mask_all, cv2.MORPH_CLOSE, kernel)
        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for c in contours:
            cx, cy, cw, ch = cv2.boundingRect(c)
            aspect = cw / float(max(1, ch))
            if 1.8 <= aspect <= 5.5 and cw >= (w * 0.10) and ch >= (h * 0.04):
                area = cv2.contourArea(c)
                candidates.append((area, (cx + sx1, cy + sy1, cw, ch)))

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            fx, fy, fw, fh = candidates[0][1]
            
            px_pad = int(fw * 0.06)
            py_pad = int(fh * 0.08)
            nx = max(0, fx - px_pad) / float(w)
            ny = max(0, fy - py_pad) / float(h)
            nw = min(w - (nx * w), fw + 2 * px_pad) / float(w)
            nh = min(h - (ny * h), fh + 2 * py_pad) / float(h)
            
            new_roi = [float(nx), float(ny), float(nw), float(nh)]
            self.set_roi(new_roi[0], new_roi[1], new_roi[2], new_roi[3])
            return new_roi
            
        return None

    def set_roi(self, x: float, y: float, w: float, h: float) -> None:
        """ROI 좌표(0.0 ~ 1.0 정규화 비율) 업데이트 및 기준치 재계산"""
        with self._lock:
            self.roi = [
                max(0.0, min(1.0, x)),
                max(0.0, min(1.0, y)),
                max(0.01, min(1.0, w)),
                max(0.01, min(1.0, h))
            ]
            self._box_history.clear()
            self._locked_slot_box = None
            self.current_curr_hp = 0
            self.current_max_hp = 0
            self.confirmed_stable_hp_pct = None
            self.last_triggered_hp_pct = None
            self._last_ocr_reading = None

    def toggle_pause(self) -> bool:
        """체력 감지 일시정지 / 재개 토글 (True: 일시정지됨, False: 재개됨)"""
        with self._lock:
            self.is_paused = not self.is_paused
            if not self.is_paused:
                self.confirmed_stable_hp_pct = None
                self.last_triggered_hp_pct = None
                self._last_ocr_reading = None
            return self.is_paused

    def set_pause(self, paused: bool) -> None:
        """체력 감지 일시정지 상태 직접 설정"""
        with self._lock:
            self.is_paused = paused
            if not self.is_paused:
                self.confirmed_stable_hp_pct = None
                self.last_triggered_hp_pct = None
                self._last_ocr_reading = None

    def calibrate_100_percent(self) -> None:
        """현재 체력바 상태를 100% 기준으로 강제 캘리브레이션"""
        with self._lock:
            self.current_hp_pct = 100.0
            self.confirmed_stable_hp_pct = 100.0
            self.last_triggered_hp_pct = 100.0
            if self.current_max_hp > 0:
                self.current_curr_hp = self.current_max_hp

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
            print(f"[Vision] 비디오 시작 실패: {e}")
            self._is_running = False
            return False

    def stop(self) -> None:
        """비디오 캡처 정지"""
        self._is_running = False
        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=1.0)
        if self._cap:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """UI 렌더링용 최신 주석(오버레이) 프레임 반환"""
        with self._lock:
            if self._latest_annotated_frame is not None:
                return self._latest_annotated_frame.copy()
            elif self._latest_raw_frame is not None:
                return self._latest_raw_frame.copy()
            return None

    def get_debug_data(self) -> Dict[str, any]:
        """🔍 실시간 디버그 모니터용 데이터 반환"""
        with self._lock:
            return {
                "hp_mask": self._debug_hp_mask.copy() if self._debug_hp_mask is not None else None,
                "text_crop": self._debug_text_crop.copy() if self._debug_text_crop is not None else None,
                "scanline_val": self._debug_scanline_val,
                "buffer": [self.current_hp_pct],
                "stable_hp": self.current_hp_pct,
                "ocr_reading": self._last_ocr_reading,
                "ocr_raw_text": self._last_ocr_raw_text,
                "is_paused": self.is_paused,
                "battle_state": self.battle_state
            }

    def _capture_loop(self) -> None:
        """60FPS 연속 비디오 프레임 캡처 및 분석 루프 (0.3ms 연산)"""
        while self._is_running:
            if not self._cap or not self._cap.isOpened():
                time.sleep(0.05)
                continue
            
            ret, frame = self._cap.read()
            if not ret or frame is None:
                time.sleep(0.005)
                continue
            
            self._process_frame(frame)
            time.sleep(0.016)  # ~60 FPS

    def _process_frame(self, frame: np.ndarray) -> None:
        """단일 프레임 처리 (숫자 최우선 권한 & 숫자 미인식 시 연출 처리)"""
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
        
        # =========================================================================
        # ⏸️ [상태 0: 수동 일시정지 상태]
        # =========================================================================
        if self.is_paused:
            self.hud_visible = False
            status_detail = "⏸️ 체력 감지 일시정지 중"
            display_tag = "[ ⏸️ 체력 감지 일시정지 중 ]"
            roi_color = (0, 165, 255) # 주황색
            
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

        # 1. 텍스트 서브영역 추출 및 고속 OCR 디스패치 (0.15초 주기)
        now = time.time()
        rh_sub, rw_sub = roi_img.shape[:2]
        num_crop = roi_img[int(rh_sub * 0.35):, int(rw_sub * 0.20):]
        
        if HAS_RAPID_OCR and (now - self._last_ocr_dispatch_time >= 0.15):
            self._last_ocr_dispatch_time = now
            try:
                if self._ocr_queue.empty():
                    self._ocr_queue.put_nowait(num_crop.copy())
            except Exception:
                pass

        # 2. 게이지 보조 분석 (디버그 뷰어용)
        raw_hp, hp_slot_rect, dbg_mask = self._analyze_gauge_auxiliary(roi_img)

        # =========================================================================
        # 🔢 [핵심: 숫자 최우선 권한 & 숫자 미인식 시 연출 처리 로직]
        # =========================================================================
        time_since_number = now - self.last_number_seen_time
        
        # 1.2초 이상 숫자가 감지되지 않은 경우 -> 100% "🎬 연출 중 / 대기 중"으로 처리!
        if time_since_number > 1.2:
            self.hud_visible = False
            self.battle_state = "CUTSCENE"
            status_detail = f"🎬 연출 중 (체력 유지: {self.current_hp_pct:.0f}%)"
            roi_color = (255, 140, 0) # 주황색 (연출 중)
            display_tag = f"[ 🎬 연출 중 (HP: {self.current_hp_pct:.0f}%) ]"
        else:
            self.hud_visible = True
            self.battle_state = "IN_BATTLE"
            if self.current_hp_pct > 50:
                roi_color = (0, 255, 0)
            elif self.current_hp_pct > 20:
                roi_color = (0, 255, 255)
            else:
                roi_color = (0, 0, 255)
                
            if self.current_max_hp > 0:
                display_tag = f"HP: {self.current_curr_hp}/{self.current_max_hp} ({self.current_hp_pct:.0f}%)"
                status_detail = display_tag
            else:
                display_tag = f"HP: {self.current_hp_pct:.0f}%"
                status_detail = display_tag

        # 콜백 알림 (UI 갱신)
        if self.on_hp_update:
            try:
                self.on_hp_update(self.current_hp_pct, 0.0, self.hud_visible, status_detail)
            except Exception:
                pass

        # 3. UI 프리뷰 오버레이 렌더링
        annotated = frame.copy()
        
        # 메인 사용자 ROI 박스
        cv2.rectangle(annotated, (px, py), (px + pw, py + ph), roi_color, 2)
        
        # 텍스트 영역 박스 (시각 피드백)
        cv2.rectangle(annotated, (px + int(pw * 0.20), py + int(ph * 0.35)), (px + pw, py + ph), (0, 255, 255), 1)

        # 텍스트 라벨
        cv2.putText(annotated, display_tag, (px, max(22, py - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(annotated, display_tag, (px, max(22, py - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, roi_color, 1)

        with self._lock:
            self._latest_raw_frame = frame
            self._latest_annotated_frame = annotated
            self._debug_hp_mask = dbg_mask
            self._debug_text_crop = num_crop
            self._debug_scanline_val = raw_hp

    @staticmethod
    def parse_pokeechamps_hp(text: str) -> Optional[Tuple[int, int]]:
        """포챔스 체력 숫자 ('현재체력 / 최대체력') 전용 고정밀 파서"""
        text = text.strip()
        
        # 1. 표준 슬래시/기호 형태 (예: '78/207', '82/149', '1/183', '93 / 183', '155/155')
        m = re.search(r'(\d{1,3})\s*[\/\|\\ㅣIil]\s*(\d{2,3})', text)
        if m:
            c, m_val = int(m.group(1)), int(m.group(2))
            if 20 <= m_val <= 600 and c <= m_val:
                return c, m_val
                
        # 2. 슬래시(/)가 '1' 또는 '7'로 붙어서 인식된 경우 (예: '2071207', '1637163')
        digits = re.findall(r'\d+', text)
        for d in digits:
            if len(d) == 7:
                c, m_val = int(d[:3]), int(d[4:])
                if 20 <= m_val <= 600 and c <= m_val:
                    return c, m_val
            if len(d) == 6:
                c, m_val = int(d[:2]), int(d[3:])
                if 20 <= m_val <= 600 and c <= m_val:
                    return c, m_val
            if len(d) == 6:
                c, m_val = int(d[:3]), int(d[3:])
                if c == m_val and 20 <= m_val <= 600:
                    return c, m_val
            if len(d) == 5:
                c, m_val = int(d[:1]), int(d[2:])
                if 20 <= m_val <= 600 and c <= m_val:
                    return c, m_val

        return None

    def _analyze_gauge_auxiliary(self, roi: np.ndarray) -> Tuple[float, Optional[Tuple[int, int, int, int]], Optional[np.ndarray]]:
        """게이지 보조 분석 (디버그 뷰어 표시용)"""
        if roi is None or roi.size == 0:
            return 0.0, None, None
            
        h, w, _ = roi.shape
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        mask_green = cv2.inRange(hsv, np.array([35, 70, 70]), np.array([85, 255, 255]))
        mask_yellow = cv2.inRange(hsv, np.array([20, 70, 70]), np.array([34, 255, 255]))
        mask_red1 = cv2.inRange(hsv, np.array([0, 70, 70]), np.array([10, 255, 255]))
        mask_red2 = cv2.inRange(hsv, np.array([170, 70, 70]), np.array([180, 255, 255]))
        mask_active_hp = cv2.bitwise_or(mask_green, cv2.bitwise_or(mask_yellow, cv2.bitwise_or(mask_red1, mask_red2)))

        if h > 40:
            mask_active_hp[0:int(h * 0.45), :] = 0
            
        body_y_start = int(h * 0.50)
        active_in_body = mask_active_hp[body_y_start:, :]
        col_sums = np.sum(active_in_body > 0, axis=0)
        active_indices = np.where(col_sums >= 1)[0]
        
        if len(active_indices) == 0:
            raw_hp = 0.0
        else:
            start_x = active_indices[0]
            consecutive_w = active_indices.max() - start_x + 1
            raw_hp = (consecutive_w / float(max(1, w * 0.75))) * 100.0
            
        return float(np.clip(raw_hp, 0.0, 100.0)), (0, body_y_start, w, h - body_y_start), mask_active_hp

    def _async_ocr_worker(self) -> None:
        """
        초고속 백그라운드 OCR (숫자 감지 시 즉각 피격 판정 및 진동 트리거)
        """
        try:
            self._ocr_engine = RapidOCR()
        except Exception:
            return

        while self._is_running:
            try:
                roi_crop = self._ocr_queue.get(timeout=0.3)
            except queue.Empty:
                continue

            try:
                # 2.5x 고품질 바이큐빅 확대
                scaled = cv2.resize(roi_crop, (0, 0), fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
                result, _ = self._ocr_engine(scaled)
                
                if result:
                    combined_text = " ".join([r[1] for r in result])
                    self._last_ocr_raw_text = combined_text
                    parsed = self.parse_pokeechamps_hp(combined_text)
                    
                    if parsed:
                        curr, max_hp = parsed
                        hp_pct = (curr / float(max_hp)) * 100.0
                        now = time.time()
                        
                        self.last_number_seen_time = now
                        self._last_ocr_reading = (curr, max_hp, hp_pct)
                        
                        # --- [A. 포켓몬 교체 감지 (최대 체력 변경)] ---
                        if self.current_max_hp > 0 and max_hp != self.current_max_hp:
                            old_max = self.current_max_hp
                            self.current_max_hp = max_hp
                            self.current_curr_hp = curr
                            self.current_hp_pct = hp_pct
                            self.confirmed_stable_hp_pct = hp_pct
                            self.last_triggered_hp_pct = hp_pct
                            if self.on_pokemon_switched:
                                try:
                                    self.on_pokemon_switched(old_max, max_hp, hp_pct)
                                except Exception:
                                    pass
                                    
                        # --- [B. 첫 진입 (기준 체력 설정)] ---
                        elif self.current_max_hp == 0 or self.current_curr_hp == 0:
                            self.current_max_hp = max_hp
                            self.current_curr_hp = curr
                            self.current_hp_pct = hp_pct
                            self.confirmed_stable_hp_pct = hp_pct
                            self.last_triggered_hp_pct = hp_pct
                            
                        # --- [C. 실제 체력 감소 (데미지 피격 감지!)] ---
                        elif curr < self.current_curr_hp:
                            damage_delta = ((self.current_curr_hp - curr) / float(max_hp)) * 100.0
                            self.current_curr_hp = curr
                            self.current_hp_pct = hp_pct
                            self.confirmed_stable_hp_pct = hp_pct
                            self.last_triggered_hp_pct = hp_pct
                            
                            if damage_delta >= self.min_damage_threshold:
                                if self.on_damage_detected:
                                    try:
                                        self.on_damage_detected(damage_delta, hp_pct, now)
                                    except Exception as e:
                                        print(f"[Vision] 피격 트리거 오류: {e}")
                                        
                        # --- [D. 체력 회복] ---
                        elif curr > self.current_curr_hp:
                            self.current_curr_hp = curr
                            self.current_hp_pct = hp_pct
                            self.confirmed_stable_hp_pct = hp_pct
                            self.last_triggered_hp_pct = hp_pct
            except Exception as e:
                pass
            time.sleep(0.05) # 빠른 반응속도 확보
