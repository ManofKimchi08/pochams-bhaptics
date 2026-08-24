import time
import threading
import numpy as np
import sounddevice as sd
from scipy.signal import butter, sosfilt, sosfilt_zi
from typing import Callable, Optional, List, Dict

class AudioDetector:
    """실시간 오디오 피격 사운드 분석 및 감지기"""

    def __init__(self, 
                 device_index: int = -1,
                 sample_rate: int = 44100,
                 block_size: int = 1024,
                 lowcut: float = 300.0,
                 highcut: float = 3500.0,
                 rms_threshold: float = 0.04,
                 peak_ratio: float = 2.2,
                 cooldown_ms: int = 300,
                 buffer_size: int = None,
                 **kwargs):
        
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.block_size = buffer_size if buffer_size is not None else block_size
        self.lowcut = lowcut
        self.highcut = highcut
        self.rms_threshold = rms_threshold
        self.peak_ratio = peak_ratio
        self.cooldown_ms = cooldown_ms
        
        self._stream: Optional[sd.InputStream] = None
        self._is_running = False
        self._last_hit_time = 0.0
        self._noise_floor = 0.01
        
        # 필터 초기화
        self._sos = butter(4, [self.lowcut, self.highcut], btype='bandpass', fs=self.sample_rate, output='sos')
        self._zi = sosfilt_zi(self._sos)
        
        # 콜백 함수들
        self.on_audio_level: Optional[Callable[[float], None]] = None
        self.on_hit_detected: Optional[Callable[[float, float], None]] = None

    @staticmethod
    def get_input_devices() -> List[Dict[str, any]]:
        """사용 가능한 입력 오디오 장치 목록 조회"""
        devices = []
        try:
            device_list = sd.query_devices()
            for idx, dev in enumerate(device_list):
                if dev['max_input_channels'] > 0:
                    devices.append({
                        "index": idx,
                        "name": dev['name'],
                        "hostapi": dev['hostapi'],
                        "channels": dev['max_input_channels'],
                        "default_samplerate": dev['default_samplerate']
                    })
        except Exception as e:
            print(f"[Audio] 장치 목록 조회 오류: {e}")
        return devices

    def start(self) -> bool:
        """오디오 스트림 캡처 시작"""
        if self._is_running:
            return True
        
        try:
            # 장치 설정
            dev_idx = None if self.device_index < 0 else self.device_index
            self._stream = sd.InputStream(
                device=dev_idx,
                channels=1,
                samplerate=self.sample_rate,
                blocksize=self.block_size,
                callback=self._audio_callback
            )
            self._stream.start()
            self._is_running = True
            print(f"[Audio] 오디오 감지 시작 (장치: {dev_idx or '기본값'}, {self.sample_rate}Hz)")
            return True
        except Exception as e:
            print(f"[Audio] 스트림 시작 실패: {e}")
            self._is_running = False
            return False

    def stop(self) -> None:
        """오디오 스트림 정지"""
        self._is_running = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def update_params(self, rms_threshold: float = None, peak_ratio: float = None, cooldown_ms: int = None):
        """실시간 파라미터 업데이트"""
        if rms_threshold is not None:
            self.rms_threshold = max(0.001, rms_threshold)
        if peak_ratio is not None:
            self.peak_ratio = max(1.0, peak_ratio)
        if cooldown_ms is not None:
            self.cooldown_ms = max(50, cooldown_ms)

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """실시간 오디오 콜백"""
        if not self._is_running:
            return
        
        # 1. 1차원 데이터 추출
        raw_signal = indata[:, 0]
        
        # 2. 대역통과 필터 적용 (타격/피격음 대역)
        try:
            filtered_signal, self._zi = sosfilt(self._sos, raw_signal, zi=self._zi)
        except Exception:
            filtered_signal = raw_signal
            
        # 3. RMS 계산
        rms = float(np.sqrt(np.mean(filtered_signal ** 2)))
        
        # UI 레벨 미터 알림 (0.0 ~ 1.0 정규화)
        if self.on_audio_level:
            try:
                level_disp = min(1.0, rms * 15.0)
                self.on_audio_level(level_disp)
            except Exception:
                pass
        
        # 4. 동적 배경 노이즈 플로어 업데이트 (지수 이동 평균)
        self._noise_floor = 0.95 * self._noise_floor + 0.05 * rms
        
        # 5. 피격 사운드 피크 판정
        now = time.time()
        is_cooldown = (now - self._last_hit_time) < (self.cooldown_ms / 1000.0)
        
        if not is_cooldown and rms > self.rms_threshold:
            if rms > (self._noise_floor * self.peak_ratio):
                self._last_hit_time = now
                intensity = min(1.0, rms / (self.rms_threshold * 3.0))
                
                if self.on_hit_detected:
                    try:
                        self.on_hit_detected(intensity, now)
                    except Exception as e:
                        print(f"[Audio] 히트 콜백 오류: {e}")
