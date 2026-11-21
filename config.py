import os
import sys
import json
import threading
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Tuple

BASE_DIR = (
    os.path.dirname(sys.executable)
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
_SAVE_LOCK = threading.Lock()


def classify_damage_magnitude(damage_percent: float) -> Tuple[str, str]:
    """피해 비율(%)만으로 피격 등급 키와 한글 표시명 반환"""
    if damage_percent <= 20.0:
        return "light", "경타"
    if damage_percent <= 50.0:
        return "medium", "중타"
    if damage_percent <= 80.0:
        return "heavy", "강타"
    return "critical", "치명타"


def classify_damage_tier(damage_percent: float, current_hp_pct: float = 100.0) -> Tuple[str, str]:
    """잔여 체력 및 피해 비율을 반영한 단일 표준 피격 등급 분류기"""
    if current_hp_pct <= 0.0:
        return "faint", "기절"
    return classify_damage_magnitude(damage_percent)

@dataclass
class HapticSinkConfig:
    kind: str = "bhaptics"          # 공식 bHaptics SDK
    app_id: str = ""                # bHaptics Developer Portal App ID
    api_key: str = ""               # bHaptics Developer Portal API Key
    motor_count: int = 32           # 32 (TactSuit Pro/X16) 또는 40 (TactSuit X40)
    front_gain: float = 1.0         # 전면 모터 게인 (0.0 ~ 2.0)
    back_gain: float = 1.0          # 후면 모터 게인 (0.0 ~ 2.0)

@dataclass
class HapticDetailRow:
    intensity: int = 100            # 세기 (0 ~ 100 %)
    duration: float = 0.30          # 길이 (초 단위, e.g. 0.26초)
    hit_count: int = 1              # 타격횟수 (1 ~ 5회)
    position: str = "All"           # 피격 부위 ("All": 정+후면 모두, "VestFront": 정면만, "VestBack": 후면만)

@dataclass
class DetailedHapticConfig:
    # 1. 경타 (1~20% 깎임)
    light: HapticDetailRow = field(default_factory=lambda: HapticDetailRow(intensity=100, duration=0.26, hit_count=1, position="All"))
    # 2. 중타 (21~50% 깎임)
    medium: HapticDetailRow = field(default_factory=lambda: HapticDetailRow(intensity=100, duration=0.42, hit_count=2, position="All"))
    # 3. 강타 (51~80% 깎임)
    heavy: HapticDetailRow = field(default_factory=lambda: HapticDetailRow(intensity=100, duration=0.48, hit_count=3, position="All"))
    # 4. 치명타 (81~100% 깎임)
    critical: HapticDetailRow = field(default_factory=lambda: HapticDetailRow(intensity=100, duration=0.52, hit_count=4, position="All"))
    # 5. 기절 (쓰러졌을 때)
    faint: HapticDetailRow = field(default_factory=lambda: HapticDetailRow(intensity=100, duration=0.90, hit_count=2, position="All"))
    # 6. 심장박동 (빨간 체력 60~171 BPM)
    heartbeat: HapticDetailRow = field(default_factory=lambda: HapticDetailRow(intensity=100, duration=0.15, hit_count=1, position="All"))
    # 7. 빨피 상시 (빨간 체력일 때 지속딜)
    low_hp_loop: HapticDetailRow = field(default_factory=lambda: HapticDetailRow(intensity=100, duration=0.42, hit_count=1, position="All"))
    # 8. 앞뒤 균형 (앞면 / 뒷면 세기 %)
    front_balance: int = 100
    back_balance: int = 100
    # 9. 🌊 충격파(Ripple) 분산 효과 활성화 여부
    enable_ripple_effect: bool = True

@dataclass
class AppConfig:
    # 햅틱 싱크 설정 (공식 bHaptics SDK 전용)
    sink: HapticSinkConfig = field(default_factory=HapticSinkConfig)
    haptic_details: DetailedHapticConfig = field(default_factory=DetailedHapticConfig)
    
    # 마스터 진동 세기 (0 ~ 100 %)
    master_intensity: int = 100
    
    # 비디오 설정
    video_device_index: int = 0
    video_width: int = 1280
    video_height: int = 720
    
    # 아군 HP 바 ROI (정규화 좌표: 0.0 ~ 1.0 - 포챔스 배틀 체력 카드에 정확히 맞춤)
    hp_roi: list[float] = field(default_factory=lambda: [0.045, 0.828, 0.195, 0.148])
    
    # 비전 감지 설정
    detection_mode: str = "balanced"        # 감지 모드 ("fast": 초고속, "balanced": 균형 6:4, "accurate": 고정밀 8.5:1.5)
    min_damage_threshold: float = 3.0       # 최소 데미지 감지 기준 (% 단위)
    
    # 빨간 체력 기준치 (% 단위, 기본 20.0%)
    red_hp_threshold: float = 20.0
    
    # 독립 플로팅 데스크톱 오버레이 창 설정 (정면 / 후면 개별 위치 지원)
    show_floating_overlay: bool = True
    floating_front_x: int = 60
    floating_front_y: int = 60
    floating_back_x: int = 200
    floating_back_y: int = 60
    overlay_scale: float = 1.0              # 오버레이 크기 (0.5 ~ 2.0 배)
    overlay_opacity: float = 0.95           # 오버레이 투명도 (0.2 ~ 1.0)
    overlay_show_front: bool = True         # 정면 오버레이 표시 여부
    overlay_show_back: bool = True          # 후면 오버레이 표시 여부
    
    # 컴팩트 모드 위치 상태
    compact_mode_x: int = 180
    compact_mode_y: int = 36
    
    # 로그 설정 (폰트 크기 및 필터)
    log_font_size: int = 11                 # 로그 글자 크기 (9 ~ 20 pt)
    log_filter: Dict[str, bool] = field(default_factory=lambda: {
        "DAMAGE": True,
        "HP": True,
        "STATE": True,
        "HAPTIC": True,
        "CAMERA": True,
        "SYSTEM": True
    })

    def save(self, filepath: str = CONFIG_FILE) -> None:
        """설정을 JSON 파일로 원자적(Atomic)이고 스레드 안전하게 저장"""
        tmp_path = f"{filepath}.tmp"
        with _SAVE_LOCK:
            try:
                parent_dir = os.path.dirname(os.path.abspath(filepath))
                if parent_dir:
                    os.makedirs(parent_dir, exist_ok=True)
                data = asdict(self)
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, filepath)
            except Exception as e:
                print(f"[Config] 설정 저장 실패: {e}")
                try:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except OSError:
                    pass

    @classmethod
    def load(cls, filepath: str = CONFIG_FILE) -> 'AppConfig':
        """JSON 파일에서 설정을 불러오며, 없으면 기본값 반환 (미지 필드 안전 필터링)"""
        if not os.path.exists(filepath):
            config = cls()
            config.save(filepath)
            return config

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return cls()

            data.pop("bhaptics_ws_url", None)
            data.pop("haptic_position", None)  # 개별 옵션으로 전환됨

            raw_sink = data.pop("sink", {})
            sink_fields = HapticSinkConfig.__dataclass_fields__
            sink_data = {k: v for k, v in raw_sink.items() if k in sink_fields} if isinstance(raw_sink, dict) else {}
            sink_data["kind"] = "bhaptics"
            sink = HapticSinkConfig(**sink_data)

            raw_details = data.pop("haptic_details", {})
            details_data = raw_details if isinstance(raw_details, dict) else {}
            row_fields = HapticDetailRow.__dataclass_fields__
            rows: Dict[str, Any] = {}
            for k in ["light", "medium", "heavy", "critical", "faint", "heartbeat", "low_hp_loop"]:
                raw_row = details_data.get(k)
                if isinstance(raw_row, dict):
                    row_dict = {rk: rv for rk, rv in raw_row.items() if rk in row_fields}
                    if "position" not in row_dict:
                        row_dict["position"] = "All"
                    rows[k] = HapticDetailRow(**row_dict)
            if "front_balance" in details_data:
                rows["front_balance"] = details_data["front_balance"]
            if "back_balance" in details_data:
                rows["back_balance"] = details_data["back_balance"]
            if "enable_ripple_effect" in details_data:
                rows["enable_ripple_effect"] = bool(details_data["enable_ripple_effect"])
            haptic_details = DetailedHapticConfig(**rows)

            valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            default_filter = cls().log_filter
            loaded_filter = valid_fields.get("log_filter")
            if isinstance(loaded_filter, dict):
                merged_filter = dict(default_filter)
                merged_filter.update({k: bool(v) for k, v in loaded_filter.items() if k in default_filter or isinstance(v, bool)})
                valid_fields["log_filter"] = merged_filter
            else:
                valid_fields.pop("log_filter", None)

            config = cls(sink=sink, haptic_details=haptic_details, **valid_fields)
            return config
        except Exception as e:
            print(f"[Config] 설정 파일 로드 오류, 기본값 사용: {e}")
            return cls()
