import os
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

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
    fps: int = 30
    
    # 아군 HP 바 ROI (정규화 좌표: 0.0 ~ 1.0)
    hp_roi: list[float] = field(default_factory=lambda: [0.05, 0.65, 0.25, 0.12])
    
    # 비전 감지 설정
    min_damage_threshold: float = 3.0       # 최소 데미지 감지 기준 (% 단위)
    hp_confirm_frames: int = 3
    deadband_percent: float = 2.0
    debounce_ms: int = 350
    
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
    
    # UI 접힘 상태
    sdk_settings_collapsed: bool = True
    
    # 로그 설정 (폰트 크기 및 필터)
    log_font_size: int = 11                 # 로그 글자 크기 (9 ~ 20 pt)
    log_filter: Dict[str, bool] = field(default_factory=lambda: {
        "DAMAGE": True,
        "HP": True,
        "STATE": True,
        "HAPTIC": True,
        "SYSTEM": True
    })

    def save(self, filepath: str = CONFIG_FILE) -> None:
        """설정을 JSON 파일로 저장"""
        try:
            data = asdict(self)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] 설정 저장 실패: {e}")

    @classmethod
    def load(cls, filepath: str = CONFIG_FILE) -> 'AppConfig':
        """JSON 파일에서 설정을 불러오며, 없으면 기본값 반환"""
        if not os.path.exists(filepath):
            config = cls()
            config.save(filepath)
            return config

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            data.pop("bhaptics_ws_url", None)
            data.pop("haptic_position", None)  # 개별 옵션으로 전환됨
            
            sink_data = data.pop("sink", {})
            sink_data["kind"] = "bhaptics"
            sink = HapticSinkConfig(**sink_data)
            
            details_data = data.pop("haptic_details", {})
            rows = {}
            for k in ["light", "medium", "heavy", "critical", "faint", "heartbeat", "low_hp_loop"]:
                if k in details_data:
                    row_dict = details_data[k]
                    # position 필드가 없을 경우 기본 "All"
                    if "position" not in row_dict:
                        row_dict["position"] = "All"
                    rows[k] = HapticDetailRow(**row_dict)
            if "front_balance" in details_data:
                rows["front_balance"] = details_data["front_balance"]
            if "back_balance" in details_data:
                rows["back_balance"] = details_data["back_balance"]
            haptic_details = DetailedHapticConfig(**rows)
            
            valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            config = cls(sink=sink, haptic_details=haptic_details, **valid_fields)
            return config
        except Exception as e:
            print(f"[Config] 설정 파일 로드 오류, 기본값 사용: {e}")
            return cls()
