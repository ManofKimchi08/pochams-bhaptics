import os
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

@dataclass
class HapticSinkConfig:
    kind: str = "bhaptics"          # "bhaptics" (공식 SDK) 또는 "websocket" (레거시)
    app_id: str = ""                # bHaptics Developer Portal App ID
    api_key: str = ""               # bHaptics Developer Portal API Key
    motor_count: int = 32           # 32 (TactSuit Pro/X16) 또는 40 (TactSuit X40)
    front_gain: float = 1.0         # 전면 모터 게인 (0.0 ~ 2.0)
    back_gain: float = 1.0          # 후면 모터 게인 (0.0 ~ 2.0)

@dataclass
class AppConfig:
    # 햅틱 싱크 설정
    sink: HapticSinkConfig = field(default_factory=HapticSinkConfig)
    
    # 비디오 설정
    video_device_index: int = 0
    video_width: int = 1280
    video_height: int = 720
    fps: int = 30
    
    # 아군 HP 바 ROI (정규화 좌표: 0.0 ~ 1.0)
    hp_roi: list[float] = field(default_factory=lambda: [0.05, 0.65, 0.25, 0.12])
    
    # 비전 감지 설정
    min_damage_threshold: float = 3.0       # 최소 데미지 감지 기준 (% 단위)
    hp_confirm_frames: int = 3              # 노이즈 방지용 연속 프레임 확인 수
    deadband_percent: float = 2.0           # 미세 떨림 방지 데드밴드 (%)
    
    # 데미지별 햅틱 강도 및 지속시간 설정
    debounce_ms: int = 350                  # 연속 진동 방지 쿨다운 (ms)
    
    # light: 1% ~ 20%
    haptic_light_intensity: int = 40        # 0 ~ 100 %
    haptic_light_duration: int = 180        # ms
    
    # medium: 21% ~ 50%
    haptic_medium_intensity: int = 70       # 0 ~ 100 %
    haptic_medium_duration: int = 280       # ms
    
    # heavy: 51% ~ 80%
    haptic_heavy_intensity: int = 90        # 0 ~ 100 %
    haptic_heavy_duration: int = 450        # ms
    
    # critical / KO: 81% ~ 100%
    haptic_critical_intensity: int = 100    # 0 ~ 100 %
    haptic_critical_duration: int = 700     # ms
    
    # 피격 위치 ("VestFront", "VestBack", "All")
    haptic_position: str = "VestFront"
    
    # 비디오 화면 내부 진동 오버레이 표시 여부
    show_visual_overlay: bool = True
    
    # 독립 플로팅 데스크톱 오버레이 창 설정
    show_floating_overlay: bool = True
    floating_overlay_x: int = 60
    floating_overlay_y: int = 60
    
    # 레거시 WebSocket 주소
    bhaptics_ws_url: str = "ws://127.0.0.1:15881/v2/feedbacks"

    def save(self, filepath: str = CONFIG_FILE) -> None:
        """설정을 JSON 파일로 저장"""
        try:
            data = asdict(self)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            print(f"[Config] 설정 저장 완료: {filepath}")
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
            
            sink_data = data.pop("sink", {})
            sink = HapticSinkConfig(**sink_data)
            
            valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            config = cls(sink=sink, **valid_fields)
            return config
        except Exception as e:
            print(f"[Config] 설정 파일 로드 오류, 기본값 사용: {e}")
            return cls()
