# 🏗️ PokéChamps x bHaptics 시스템 아키텍처 및 개발자 인수인계 가이드 (Developer & Architecture Guide)

본 문서는 **포켓몬 챔피언스(Nintendo Switch)와 bHaptics TactSuit 실시간 연동 시스템**의 내부 구조, 동시성 모델, 핵심 알고리즘 및 코드 확장 가이드를 개발자 관점에서 상세히 기술합니다.

---

## 📌 1. 시스템 전체 아키텍처 (System Overview)

본 시스템은 **생산자-소비자(Producer-Consumer) 멀티스레드 모델**과 **옵저버(Observer) 패턴 기반의 이벤트 브릿지**로 구성되어 있습니다.

```mermaid
graph TD
    subgraph CaptureLayer["1. 영상 캡처 및 전처리 (60 FPS)"]
        Cam["HDMI 캡처보드 / OBS 가상카메라"] --> |cv2.VideoCapture DirectShow| CapLoop["Capture Loop Thread (60 FPS)"]
        CapLoop --> RawFrame["최신 프레임 버퍼 (Frame Buffer)"]
    end

    subgraph VisionLayer["2. 하이브리드 비전 엔진 (VisionDetector)"]
        RawFrame --> ROI["ROI 크롭 (아군 체력 영역)"]
        ROI --> AutoSnap["🎯 Auto-Snap Card Anchor"]
        ROI --> NumCrop["🔢 텍스트 서브영역 분리 (2.5x Cubic)"]
        NumCrop --> OCRQueue["비동기 OCR 큐 (Queue maxsize=1)"]
        OCRQueue --> OCRWorker["Async RapidOCR Worker Thread"]
        OCRWorker --> Parser["포챔스 전용 정밀 수치 파서 (Regex)"]
        Parser --> StateMachine["⚔️ 배틀 상태 머신 (Number-First Authority)"]
        StateMachine --> |숫자 미인식 (>1.2s)| CutsceneHold["🎬 연출 중 (체력 동결 & 진동 차단)"]
        StateMachine --> |체력 감소 감지| DamageEvent["⚡ 피격 이벤트 발생 (Delta HP%)"]
    end

    subgraph FusionLayer["3. 이벤트 브릿지 엔진 (FusionEngine)"]
        DamageEvent --> Fusion["FusionEngine (중계 및 스케줄링)"]
        CutsceneHold --> Fusion
    end

    subgraph HapticLayer["4. 햅틱 피드백 엔진 (HapticManager)"]
        Fusion --> TierMap["4단계 데미지 비례 강도 매핑 (Light/Med/Heavy/Critical)"]
        TierMap --> SDKRouter{"연동 방식 분기"}
        SDKRouter --> |bhaptics| OfficialSDK["공식 bHaptics Python SDK (C-API)"]
        SDKRouter --> |websocket| WSClient["레거시 로컬 WebSocket 통신"]
        OfficialSDK --> TactSuit["🎽 bHaptics TactSuit 슈트"]
        WSClient --> TactSuit
    end

    subgraph UILayer["5. 프레젠테이션 계층 (PySide6 GUI)"]
        Fusion --> Signals["Qt Signals / Slots"]
        Signals --> MainWindow["메인 대시보드 윈도우"]
        Signals --> VideoWidget["60FPS 비디오 뷰어 & 인게임 오버레이"]
        Signals --> TactVisualizer["2D TactSuit 모터 매트릭스"]
        Signals --> FloatingOverlay["🪟 독립 투명 플로팅 HUD 창"]
        Signals --> DebugWidget["🔍 실시간 비전 디버그 모니터"]
    end
```

---

## 📁 2. 모듈별 역할 및 책임 (Module Breakdown)

| 파일명 | 클래스명 | 핵심 책임 및 역할 |
|---|---|---|
| [`config.py`](file:///C:/Users/dlwjd/.gemini/antigravity/scratch/pochams_bhaptics/config.py) | `AppConfig`, `SinkConfig` | Pydantic 기반 설정 직렬화/역직렬화 및 `config.json` 로컬 저장 관리 |
| [`vision_detector.py`](file:///C:/Users/dlwjd/.gemini/antigravity/scratch/pochams_bhaptics/vision_detector.py) | `VisionDetector` | 비디오 캡처, 자동 스냅, RapidOCR 수치 파싱, 숫자 최우선 배틀 상태 머신 |
| [`haptic_manager.py`](file:///C:/Users/dlwjd/.gemini/antigravity/scratch/pochams_bhaptics/haptic_manager.py) | `HapticManager` | bHaptics C-API 연동, 4단계 데미지 강도 계산, 2D 모터 애니메이션 매트릭스 계산 |
| [`fusion_engine.py`](file:///C:/Users/dlwjd/.gemini/antigravity/scratch/pochams_bhaptics/fusion_engine.py) | `FusionEngine` | 비전 분석 결과와 햅틱 출력을 결합하는 미들웨어, 로깅 및 수동 일시정지 제어 |
| [`main.py`](file:///C:/Users/dlwjd/.gemini/antigravity/scratch/pochams_bhaptics/main.py) | `MainWindow`, `FloatingHapticOverlay`, `VideoWidget`, `VisionDebugWidget` | PySide6 기반 고성능 하드웨어 가속 GUI 및 오버레이 렌더링 |

---

## 🧠 3. 핵심 알고리즘 상세 (Deep Dive into Algorithms)

### 3.1. 숫자 최우선 권한 (Number-First Authority) & 연출 자동 동결
* **배경**: 콘솔 3D 게임 특성상 스킬 폭발 이펙트, 캐릭터 모델(예: 리자몽 날개/꼬리), 경기장 바닥 조명으로 인해 2D 색상 막대(Color Bar)는 출렁임(Jitter)이 발생할 수 있습니다.
* **해결 알고리즘**:
  1. ROI 우측 하단 텍스트 영역(`num_crop`)을 $2.5\times$ 바이큐빅(Bicubic) 확대하여 백그라운드 OCR로 전송합니다.
  2. OCR 결과에서 포챔스 고유의 정규표현식(`\d{1,3}\s*[\/|ㅣIl]\s*\d{2,3}`)으로 `(현재체력, 최대체력)` 정수 쌍을 추출합니다.
  3. **체력 감소 판정**:
     $$\Delta \text{HP} = \frac{\text{Previous\_Curr} - \text{Current\_Curr}}{\text{Max\_HP}} \times 100.0\%$$
     $\Delta \text{HP} \ge 3.0\%$일 때 단 $1$회 피격 진동을 발생시킵니다.
  4. **포켓몬 교체 판정**:
     $$\text{New\_Max\_HP} \neq \text{Old\_Max\_HP}$$
     최대 체력이 달라지면 교체로 판정하여 기준 체력을 즉시 갱신하고 진동을 $0$으로 억제합니다.
  5. **연출 자동 동결 (Cutscene Hold)**:
     $$T_{\text{now}} - T_{\text{last\_number\_seen}} > 1.2\text{s}$$
     숫자가 화면에서 사라진 지 $1.2$초가 초과되면 `CUTSCENE` 상태로 전환하여 체력을 동결하고 모든 진동을 원천 차단합니다.

### 3.2. 🎯 체력바 카드 자동 스냅 (Auto-Snap Card Anchor)
* **알고리즘**:
  * 1080p/720p 전체 프레임의 좌측 하단 $45\%$ 영역($X \in [0, 0.45], Y \in [0.45, 0.98]$)을 HSV 색공간으로 변환합니다.
  * 포챔스 카드 고유의 색상 집합(Dark Slot, Active Green/Yellow/Red, Blue Nameplate) 마스크를 생성하고 모폴로지 닫힘 연산(`MORPH_CLOSE`)을 수행합니다.
  * 종횡비($\text{Aspect Ratio} \in [1.8, 5.5]$)와 최소 면적 조건을 만족하는 가장 큰 컨투어를 찾아 상하좌우 $6\sim 8\%$ 패딩을 부여한 정규화 ROI를 자동 반환합니다.

### 3.3. 🎽 2D 공간 햅틱 매트릭스 및 네온 감쇄 렌더링
* 전면 20개($4\times 5$), 후면 20개($4\times 5$)의 모터 배열을 관리합니다.
* 피격 발생 시 데미지 등급에 따라 해당 모터 인덱스에 강도($0\sim 100$)를 부여하고, $60\text{FPS}$ 렌더 틱마다 지수 감쇄(Exponential Decay, $\text{intensity} \times 0.88$)를 적용하여 부드러운 네온 잔상 애니메이션을 생성합니다.

---

## 🧵 4. 스레딩 및 동시성 모델 (Threading & Concurrency)

```
[Main UI Thread (PySide6 Event Loop)]
   ├── 60FPS QTimer (_on_render_tick)
   │     ├── 최신 비디오 프레임 GUI 렌더링
   │     ├── 독립 플로팅 HUD 위치 동기화
   │     └── 모터 네온 감쇄 애니메이션 갱신
   │
   ├── [Capture Loop Thread (VisionDetector)]
   │     ├── cv2.VideoCapture read (DirectShow)
   │     ├── ROI 크롭 및 고속 1D 스캔라인 계산
   │     └── OCR Queue에 0.15초 주기로 num_crop 푸시 (Non-blocking)
   │
   └── [Async OCR Worker Thread (VisionDetector)]
         ├── OCR Queue에서 프레임 팝
         ├── RapidOCR ONNX 추론 (평균 40~70ms)
         └── 수치 파싱 후 데미지/교체 콜백 발화
```

* **스레드 안전성(Thread Safety)**:
  * 프레임 버퍼 및 상태 변수는 `threading.Lock()`으로 보호됩니다.
  * 비전 이벤트 $\to$ UI 스레드 간 데이터 전달은 `QObject`의 `Qt.QueuedConnection` 시그널(`QSignalBridge`)을 통해 메인 UI 스레드 충돌 없이 안전하게 전달됩니다.

---

## 🔧 5. 빌드 및 배포 (Build & Packaging)

### PyInstaller 단일 폴더 패키징 명령
```bash
pyinstaller --noconfirm --onedir --windowed \
  --name "Pochams_bHaptics" \
  --hidden-import "bhaptics_python" --collect-all "bhaptics_python" \
  --hidden-import "rapidocr_onnxruntime" --collect-all "rapidocr_onnxruntime" \
  --hidden-import "onnxruntime" --collect-all "onnxruntime" \
  main.py
```
* 빌드 결과물: `dist/Pochams_bHaptics/Pochams_bHaptics.exe`

---

## 🚀 6. 향후 확장 및 개선 포인트 (Future Extensibility)

1. **초경량 11종 비트맵 CNN 모델 교체**:
   - `RapidOCR` 대신 11종 포챔스 폰트(`0~9`, `/`)만 학습한 50KB ONNX 모델로 교체 시 연산 시간을 $0.1\text{ms}$ 이하로 단축 가능.
2. **OBS WebSocket 무손실 다이렉트 프레임 연동**:
   - DirectShow 웹캠 캡처 대신 `obs-websocket-py`를 통해 OBS 렌더 텍스처를 직접 전달받아 압축 노이즈 제로화 가능.
3. **타격음(Impact SFX) 주파수 하이브리드 결합**:
   - `audio_detector.py`를 연동하여 HDMI 오디오의 200~800Hz 타격 과도응답(Transient)을 감지해 10ms 초고속 반응 구현 가능.
