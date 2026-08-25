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
        
        # 디버그 뷰어용 실시간 이미지 및 수치
        self._debug_hp_mask: Optional[np.ndarray] = None
        self._debug_text_crop: Optional[np.ndarray] = None
        self._debug_scanline_val: float = 0.0
        
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
        
        # 1D 게이지 최근 수치 추적
        self._latest_gauge_pct: float = 100.0
        
        # 비동기 고속 OCR 큐
        self._ocr_queue: queue.Queue = queue.Queue(maxsize=1)
        self._ocr_engine = None
        self._last_ocr_dispatch_time: float = 0.0
        self._last_ocr_reading: Optional[Tuple[int, int, float]] = None
        self._last_ocr_raw_text: str = ""
        
        # 콜백
        self.on_hp_update: Optional[Callable[[float, float, bool, str], None]] = None
        self.on_damage_detected: Optional[Callable[[float, float, float], None]] = None
        self.on_pokemon_switched: Optional[Callable[[int, int, float], None]] = None

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
        """배틀 화면에서 아군 체력바 카드를 0.1픽셀 단위로 자동 탐색하여 딱 맞게 스냅"""
        with self._lock:
            if self._latest_raw_frame is None:
                return None
            frame = self._latest_raw_frame.copy()

        h, w, _ = frame.shape
        sx1, sy1 = int(w * 0.0), int(h * 0.45)
        sx2, sy2 = int(w * 0.45), int(h * 0.95)
        search_roi = frame[sy1:sy2, sx1:sx2]
        
        gray = cv2.cvtColor(search_roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 40, 140)
        
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 3))
        dilated = cv2.dilate(edges, kernel, iterations=2)
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        candidates = []
        for c in contours:
            cx, cy, cw, ch = cv2.boundingRect(c)
            aspect = cw / float(max(1, ch))
            if 1.6 <= aspect <= 3.8 and cw >= int(w * 0.10) and ch >= int(h * 0.04):
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

    def calibrate_100_percent(self) -> None:
        """현재 체력바 상태를 100% 기준으로 강제 캘리브레이션"""
        with self._lock:
            self.current_hp_pct = 100.0
            self.confirmed_stable_hp_pct = 100.0
            self.last_triggered_hp_pct = 100.0
            if self.confirmed_max_hp > 0:
                self.confirmed_curr_hp = self.confirmed_max_hp
            self._ocr_history.clear()

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
        """UI 표시용 최신 주석(ROI 사각형 및 HP 텍스트) 프레임 반환"""
        with self._lock:
            if self._latest_annotated_frame is not None:
                return self._latest_annotated_frame.copy()
            return None

    def get_debug_data(self) -> dict:
        """비전 디버그 모니터용 실시간 진단 데이터"""
        with self._lock:
            return {
                "hp_mask": self._debug_hp_mask.copy() if self._debug_hp_mask is not None else None,
                "text_crop": self._debug_text_crop.copy() if self._debug_text_crop is not None else None,
                "scanline_val": self._debug_scanline_val,
                "ocr_reading": self._last_ocr_reading,
                "raw_text": self._last_ocr_raw_text,
                "battle_state": self.battle_state,
                "is_paused": self.is_paused
            }

    def _capture_loop(self) -> None:
        """60FPS 프레임 캡처 루프"""
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

        # 1. 1D 색상 게이지 분석 (스캔라인)
        raw_gauge_hp, hp_slot_rect, dbg_mask = self._analyze_gauge_auxiliary(roi_img)
        self._latest_gauge_pct = raw_gauge_hp

        # 2. 텍스트 서브영역 분리 및 OCR 큐 전달 (0.10초 주기 고속 파이프라인)
        now = time.time()
        rh_sub, rw_sub = roi_img.shape[:2]
        # 🎯 OCR 텍스트 서브영역: 상단 포켓몬 이름/성별 아이콘(♀/♂) 및 좌측 스프라이트를 배제하고 하단 수치 영역(0/140) 집중 크롭
        num_crop = roi_img[int(rh_sub * 0.45):, int(rw_sub * 0.28):]
        
        if HAS_RAPID_OCR and (now - self._last_ocr_dispatch_time >= 0.10):
            self._last_ocr_dispatch_time = now
            try:
                if self._ocr_queue.empty():
                    self._ocr_queue.put_nowait((num_crop.copy(), raw_gauge_hp))
            except Exception:
                pass

        # 3. 🎬 연출 자동 동결 (Cutscene Hold) 및 💀 기절(Fainted) 처리
        time_since_number = now - self.last_number_seen_time
        if self.confirmed_curr_hp <= 0 and self.confirmed_max_hp > 0:
            self.hud_visible = False
            self.battle_state = "FAINTED"
            status_detail = "💀 포켓몬 기절 (HP: 0%)"
            roi_color = (128, 128, 128)
            display_tag = "[ 💀 포켓몬 기절 (HP: 0%) ]"
        elif time_since_number > 1.3:
            self.hud_visible = False
            self.battle_state = "CUTSCENE"
            status_detail = f"🎬 연출 중 (체력 유지: {self.current_hp_pct:.0f}%)"
            roi_color = (255, 140, 0)
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
                
            if self.confirmed_max_hp > 0:
                display_tag = f"HP: {self.confirmed_curr_hp}/{self.confirmed_max_hp} ({self.current_hp_pct:.0f}%)"
                status_detail = display_tag
            else:
                display_tag = f"HP: {self.current_hp_pct:.0f}%"
                status_detail = display_tag

        if self.on_hp_update:
            try:
                self.on_hp_update(self.current_hp_pct, 0.0, self.hud_visible, status_detail)
            except Exception:
                pass

        # 4. UI 렌더링
        annotated = frame.copy()
        cv2.rectangle(annotated, (px, py), (px + pw, py + ph), roi_color, 2)
        cv2.rectangle(annotated, (px + int(pw * 0.15), py + int(ph * 0.30)), (px + pw, py + ph), (0, 255, 255), 1)
        cv2.putText(annotated, display_tag, (px, max(22, py - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(annotated, display_tag, (px, max(22, py - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, roi_color, 1)

        with self._lock:
            self._latest_raw_frame = frame
            self._latest_annotated_frame = annotated
            self._debug_hp_mask = dbg_mask
            self._debug_text_crop = num_crop
            self._debug_scanline_val = raw_gauge_hp

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
        t = re.sub(r'[\/\|\\ㅣ]', '/', t)
        
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
    def parse_pokeechamps_hp_smart(cls, text: str) -> Optional[Tuple[int, int]]:
        """
        🔤 포챔스 전용 고정밀 수치 및 슬래시(/) 분리 스마트 교정기
        - ⏰ 1. 타이머 형식 (MM:SS, e.g. 04:58, 05:00, 0:45) 사전 원천 필터링
        - 🎯 2. 표준 포챔스 HP (40 <= 최대HP <= 750, 현재HP <= 최대HP) 검증
        """
        raw_clean = text.strip()
        
        # ⏰ [안전망 1: 타이머 MM:SS 및 타이머 아이콘 사전 차단]
        # 예: '04:58', '05:00', '4:58', '02:30', '00:45'
        if re.search(r'\b\d{1,2}\s*[:;]\s*[0-5]\d\b', raw_clean):
            return None
        if any(sym in raw_clean for sym in ['⏱', '⏰', '⏳', '초', '분']):
            return None

        norm = cls.normalize_ocr_text(raw_clean)
        
        # 1. 표준 슬래시 분리 (예: '78/207', '155/155', '0/100')
        m = re.search(r'(\d{1,3})\s*\/\s*(\d{2,3})', norm)
        if m:
            c, m_val = int(m.group(1)), int(m.group(2))
            # 포챔스(50레벨) 포켓몬 최대 HP 기준 (40 ~ 750)
            if 40 <= m_val <= 750 and 0 <= c <= m_val:
                return c, m_val
                
        # 2. 슬래시가 '1', '7' 등으로 붙어서 연속 숫자로 합쳐진 경우 복원
        digits = re.findall(r'\d+', norm)
        for d in digits:
            L = len(d)
            if L == 7: # 1637163 (3 + 1 + 3) -> 163 / 163
                c, m_val = int(d[:3]), int(d[4:])
                if 40 <= m_val <= 750 and 0 <= c <= m_val:
                    return c, m_val
            elif L == 6: # 781207 (2 + 1 + 3) 또는 155155 (3 + 3)
                # 1) 만약 앞 3자리와 뒤 3자리가 같은 경우 (155155 -> 155/155 100% 풀체력) 우선 매칭
                c2, m2 = int(d[:3]), int(d[3:])
                if 40 <= m2 <= 750 and c2 == m2:
                    return c2, m2
                # 2) 781207 (2 + 1 + 3) 형태 (중간 1/7이 구분자)
                c1, m1 = int(d[:2]), int(d[3:])
                if 40 <= m1 <= 750 and 0 <= c1 <= m1:
                    return c1, m1
            elif L == 5: # 11183 (1 + 1 + 3) 또는 82149 (2 + 1 + 2)
                c1, m1 = int(d[:1]), int(d[2:])
                if 40 <= m1 <= 750 and 0 <= c1 <= m1:
                    return c1, m1
                c2, m2 = int(d[:2]), int(d[2:])
                if 40 <= m2 <= 750 and 0 <= c2 <= m2:
                    return c2, m2

        return None

    def _analyze_gauge_auxiliary(self, roi: np.ndarray) -> Tuple[float, Optional[Tuple[int, int, int, int]], Optional[np.ndarray]]:
        """1D 색상 게이지 스캔라인 분석 (초록/노랑/빨강 체력바 길이 측정 - 포켓몬 스프라이트 및 성별 아이콘 배제)"""
        if roi is None or roi.size == 0:
            return 0.0, None, None
            
        h, w, _ = roi.shape
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        
        mask_green = cv2.inRange(hsv, np.array([35, 70, 70]), np.array([85, 255, 255]))
        mask_yellow = cv2.inRange(hsv, np.array([20, 70, 70]), np.array([34, 255, 255]))
        mask_red1 = cv2.inRange(hsv, np.array([0, 70, 70]), np.array([10, 255, 255]))
        mask_red2 = cv2.inRange(hsv, np.array([170, 70, 70]), np.array([180, 255, 255]))
        mask_active_hp = cv2.bitwise_or(mask_green, cv2.bitwise_or(mask_yellow, cv2.bitwise_or(mask_red1, mask_red2)))

        # 🎯 포켓몬 카드 내 실제 HP 바 슬롯 영역으로 엄격 격리:
        # 1) 상단 48% 마스킹 (포켓몬 이름, 성별 아이콘 ♀/♂, 타겟 마크 차단)
        # 2) 좌측 28% 마스킹 (호박/피카츄 등 노랑/빨강/초록 포켓몬 일러스트 스프라이트 차단)
        # 3) 우측 22% 마스킹 (배경 및 우측 외곽선 차단)
        if h > 20 and w > 40:
            mask_active_hp[0:int(h * 0.48), :] = 0
            mask_active_hp[int(h * 0.85):, :] = 0
            mask_active_hp[:, 0:int(w * 0.28)] = 0
            mask_active_hp[:, int(w * 0.78):] = 0
            
        body_y_start = int(h * 0.48)
        body_y_end = int(h * 0.85)
        slot_x_start = int(w * 0.28)
        slot_x_end = int(w * 0.78)
        
        active_in_body = mask_active_hp[body_y_start:body_y_end, slot_x_start:slot_x_end]
        slot_w = float(max(1, slot_x_end - slot_x_start))
        
        col_sums = np.sum(active_in_body > 0, axis=0)
        # 세로 2픽셀 이상 연속 채워진 유효 게이지 컬럼 수 (단발성 노이즈 배제)
        active_cols = np.sum(col_sums >= 2)
        raw_hp = (active_cols / slot_w) * 100.0
            
        return float(np.clip(raw_hp, 0.0, 100.0)), (slot_x_start, body_y_start, int(slot_w), body_y_end - body_y_start), mask_active_hp

    def _async_ocr_worker(self) -> None:
        """
        🔍 3중 적응형 전처리 + 📊 듀얼 교차 검증 + 🛡️ 2~3프레임 연속 합의 락 파이프라인
        """
        try:
            self._ocr_engine = RapidOCR()
        except Exception:
            return

        # CLAHE 객체 생성
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))

        while self._is_running:
            try:
                queue_item = self._ocr_queue.get(timeout=0.25)
                roi_crop, gauge_pct = queue_item
            except queue.Empty:
                continue

            try:
                # 1. 🔍 3.0x 고품질 바이큐빅 확대
                scaled = cv2.resize(roi_crop, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
                
                # 2. 🔍 샤프닝 필터 (Unsharp Mask)
                gaussian = cv2.GaussianBlur(scaled, (0, 0), 2.0)
                unsharp = cv2.addWeighted(scaled, 2.0, gaussian, -1.0, 0)
                
                # --- [파이프라인 1차: 샤프닝 + CLAHE 명암비 강화] ---
                gray = cv2.cvtColor(unsharp, cv2.COLOR_BGR2GRAY)
                enhanced_gray = clahe.apply(gray)
                parsed_pair = None

                result1, _ = self._ocr_engine(enhanced_gray)
                if result1:
                    raw_text1 = " ".join([r[1] for r in result1])
                    self._last_ocr_raw_text = raw_text1
                    parsed_pair = self.parse_pokeechamps_hp_smart(raw_text1)

                # --- [파이프라인 2차: 순수 화이트 마스크 (HSV V>170, S<70)] ---
                if parsed_pair is None:
                    hsv = cv2.cvtColor(scaled, cv2.COLOR_BGR2HSV)
                    mask_white = cv2.inRange(hsv, np.array([0, 0, 160]), np.array([180, 80, 255]))
                    result2, _ = self._ocr_engine(mask_white)
                    if result2:
                        raw_text2 = " ".join([r[1] for r in result2])
                        self._last_ocr_raw_text = raw_text2
                        parsed_pair = self.parse_pokeechamps_hp_smart(raw_text2)

                # --- [파이프라인 3차: 이진화 Otsu Threshold] ---
                if parsed_pair is None:
                    _, otsu = cv2.threshold(enhanced_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    result3, _ = self._ocr_engine(otsu)
                    if result3:
                        raw_text3 = " ".join([r[1] for r in result3])
                        self._last_ocr_raw_text = raw_text3
                        parsed_pair = self.parse_pokeechamps_hp_smart(raw_text3)

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
                                
                    # --- [B. 첫 진입 (초기 기준 체력 설정)] ---
                    elif self.confirmed_max_hp == 0 or self.confirmed_curr_hp == 0:
                        self.confirmed_max_hp = max_hp
                        self.confirmed_curr_hp = curr
                        self.current_hp_pct = ocr_hp_pct
                        self.confirmed_stable_hp_pct = ocr_hp_pct
                        self.last_triggered_hp_pct = ocr_hp_pct
                        
                    # --- [C. 2~3프레임 연속 일치 합의 락 (피격 최종 판정)] ---
                    elif len(self._ocr_history) >= 2:
                        currs = [item[1] for item in self._ocr_history]
                        counts = Counter(currs)
                        mode_curr, mode_count = counts.most_common(1)[0]
                        
                        # 최근 연속 2프레임이 동일한 최빈값일 때만 정적 안착 확정!
                        last_two = currs[-2:]
                        is_steady = (last_two[0] == mode_curr and last_two[1] == mode_curr)
                        
                        # 교체 직후 0.8초간 진동 보호 뮤트
                        is_switch_protected = (now - self.last_switch_time < 0.8)

                        if is_steady and mode_curr != self.confirmed_curr_hp:
                            # 1) 데미지 발생 (체력 감소)
                            if mode_curr < self.confirmed_curr_hp:
                                damage_delta = ((self.confirmed_curr_hp - mode_curr) / float(max_hp)) * 100.0
                                self.confirmed_curr_hp = mode_curr
                                self.current_hp_pct = (mode_curr / float(max_hp)) * 100.0
                                self.confirmed_stable_hp_pct = self.current_hp_pct
                                self.last_triggered_hp_pct = self.current_hp_pct
                                
                                if damage_delta >= self.min_damage_threshold and not is_switch_protected:
                                    if self.on_damage_detected:
                                        try:
                                            self.on_damage_detected(damage_delta, self.current_hp_pct, now)
                                        except Exception as e:
                                            print(f"[Vision] 피격 트리거 오류: {e}")
                                            
                            # 2) 체력 회복 / 힐 (2프레임 연속 확정 시 수치 갱신 및 회복 이벤트 전달)
                            elif mode_curr > self.confirmed_curr_hp:
                                self.confirmed_curr_hp = mode_curr
                                self.current_hp_pct = (mode_curr / float(max_hp)) * 100.0
                                self.confirmed_stable_hp_pct = self.current_hp_pct
                                self.last_triggered_hp_pct = self.current_hp_pct
                                if hasattr(self, 'on_heal_detected') and self.on_heal_detected:
                                    try:
                                        self.on_heal_detected(self.current_hp_pct)
                                    except Exception:
                                        pass

            except Exception as e:
                pass
            time.sleep(0.04)
