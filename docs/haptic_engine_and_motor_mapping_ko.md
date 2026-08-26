# 🎽 햅틱 엔진 및 40점 모터 매트릭스 설계서 (Haptic Engine & Motor Mapping)

문서 버전: v2.1 | 최종 수정일: 2026-08-26

## 1. 개요 (Overview)

본 문서는 bHaptics TactSuit (TactSuit X40, TactSuit X16) 슈트의 전면(Front 20점) 및 후면(Back 20점) 모터에 최적화된 **피격 등급별 모터 매트릭스 알고리즘, 부위별(정면/후면/정+후) 독립 라우팅, 심장박동/빨피 상시 펄스 제어**에 대한 기술 명세서입니다.

---

## 2. 4단계 피격 등급 및 패턴 정의

| 피격 등급 | 체력 감소율 ($\Delta\text{HP}$) | 기본 강도 / 지속시간 | 기본 타격횟수 | 모터 작동 범위 |
|---|---|---|---|---|
| **경타 (Light)** | $0.0\% < \Delta\text{HP} \le 20.0\%$ | $40\% \ /\ 180\text{ms}$ | 1회 | 가슴/명치 중앙 2점 (점 [5, 6]) |
| **중타 (Medium)** | $20.0\% < \Delta\text{HP} \le 50.0\%$ | $70\% \ /\ 280\text{ms}$ | 2회 | 상체 및 가슴 6점 (점 [1, 2, 5, 6, 9, 10]) |
| **강타 (Heavy)** | $50.0\% < \Delta\text{HP} \le 80.0\%$ | $90\% \ /\ 450\text{ms}$ | 2회 | 가슴, 복부, 옆구리 12점 전면 강타 |
| **치명타 (Critical)** | $\Delta\text{HP} > 80.0\%$ | $100\% \ /\ 700\text{ms}$ | 3회 | 전면 20점 + 후면 20점 (총 40점 풀 파워) |
| **기절 (Faint)** | $\text{Current HP} = 0.0\%$ | $100\% \ /\ 900\text{ms}$ | 3회 | 흉부/등 전체 40점 넉다운 진동 |
| **심장박동 (Heartbeat)** | $\text{Current HP} \le 20.0\%$ | $85\% \ /\ 150\text{ms}$ | 1회 (0.85s 주기) | 좌측 가슴 심장 위치 3점 (점 [4, 5, 8]) |
| **빨피 상시 (Low HP Loop)**| $\text{Current HP} \le 20.0\%$ | $40\% \ /\ 420\text{ms}$ | 연속 루프 (심리스) | 하복부 및 허리 8점 은은한 지속 진동 |

---

## 3. 부위별(정면/후면/전체) 라우팅 알고리즘

사용자는 GUI에서 각 패턴별로 진동이 울릴 신체 부위를 자유롭게 선택할 수 있습니다.
시스템은 선택된 부위 모드(`All`, `VestFront`, `VestBack`)에 따라 활성 모터 배열을 동적으로 분기합니다.

```python
def _generate_motor_matrix(self, level: str, intensity: int, position_mode: str = "All") -> Tuple[List[int], List[int]]:
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
        # 심장박동: 좌측 흉부 펄스
        indices = [4, 5, 8]
        for idx in indices:
            if use_front: front[idx] = intensity
            if use_back: back[idx] = int(intensity * 0.5)

    elif level == "low_hp_loop":
        # 빨피 상시: 하복부 지속 진동
        indices = [12, 13, 14, 15, 16, 17, 18, 19]
        for idx in indices:
            if use_front: front[idx] = intensity
            if use_back: back[idx] = intensity

    return front, back
```

---

## 4. TactSuit X16 (16점) 및 X40 (40점) 자동 다운샘플링

32점(X16 수트) 환경에서는 20점 배열을 물리적 모터 배치에 맞게 16점으로 자동 다운샘플링 변환합니다:

```python
if self.sink.motor_count == 32:
    indices_16 = [0, 1, 2, 3, 4, 7, 8, 11, 12, 15, 16, 17, 18, 19, 5, 6]
    f16 = [f20_g[i] for i in indices_16]
    b16 = [b20_g[i] for i in indices_16]
    return f16 + b16
else:
    return f20_g + b20_g
```

---

## 5. UI 실시간 2D 모터 뷰어 및 네온 감쇄 애니메이션

수트에 진동이 전달되는 순간, 사용자가 UI 상에서 모터 강도를 시각적으로 확인할 수 있도록 $\sin$ 감쇄 곡선 기반의 페이드아웃 애니메이션을 실시간 렌더링합니다:

$$V(t) = V_0 \times \sin\left(\left(1 - \frac{t}{\text{Duration}}\right) \times \frac{\pi}{2}\right)$$
