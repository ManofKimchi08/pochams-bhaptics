# PokéChamps x bHaptics Tactile Link (포챔스 x bHaptics 실시간 연동 시스템)

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Nintendo%20Switch-E60012?style=for-the-badge&logo=nintendoswitch&logoColor=white" />
  <img src="https://img.shields.io/badge/bHaptics-TactSuit%20X40%20%2F%20X16-00e5ff?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/GUI-PySide6%20Qt-41CD52?style=for-the-badge&logo=qt&logoColor=white" />
  <img src="https://img.shields.io/badge/Vision-RapidOCR%20%2B%20OpenCV-FF6F00?style=for-the-badge" />
</p>

닌텐도 스위치 포켓몬 챔피언스(포챔스) 방송 및 플레이 화면을 캡처보드/OBS로 캡처하여, **아군 포켓몬의 실시간 피격 데미지 비율(%)에 비례하는 햅틱 진동 피드백을 bHaptics TactSuit 슈트로 전달**하는 고성능 비전-햅틱 연동 프로그램입니다.

---

## ✨ 핵심 기능 (Key Features)

### 1. 🔢 숫자 최우선 권한 & 연출 자동 동결 (Number-First & Cutscene Hold)
- **절대 권한 숫자 인식**: 3D 배경 폭발이나 광택 노이즈를 배제하고, 화면에 표시되는 정확한 숫자(`현재HP / 최대HP`, 예: `78/207`)만을 단일 진실 기준으로 삼아 데미지 비율($\Delta\text{HP}$)을 계산합니다.
- **연출 자동 동결 (Cutscene Hold)**: 스킬 컷신, 리자몽 꼬리 가림, 포켓몬 교체 연출, 매칭 로비 등으로 숫자가 보이지 않을 때는 즉시 `[ 🎬 연출 중 (체력 동결) ]`로 자동 전환되어 가짜 진동을 $0\%$로 원천 차단합니다.

### 2. 🎯 체력바 카드 원클릭 자동 스냅 (Auto-Snap ROI)
- 배틀 화면에서 `[ 🎯 체력바 자동 스냅 ]` 버튼을 누르면 1080p/720p 전체 화면에서 포챔스 아군 체력바 카드를 0.1픽셀 단위로 자동 탐색하여 딱 맞게 스냅합니다.

### 3. 🎽 독립 플로팅 데스크톱 오버레이 & 2D 모터 뷰어
- **독립 플로팅 HUD**: 방송 화면이나 듀얼 모니터 어디든 자유롭게 드래그하여 배치할 수 있는 투명 Always-on-Top 진동 모니터 창을 제공합니다.
- **2D 실시간 모터 뷰어**: 전면(Front 20점)과 후면(Back 20점) 모터의 실시간 진동 강도 및 네온 감쇄 애니메이션을 표시합니다.

### 4. ⚡ 4단계 데미지 비례 다이내믹 햅틱 엔진
- **Light (약 피격, ~15%)**: 40% 강도, 180ms 찰나의 잽 피격
- **Medium (중 피격, 15~35%)**: 70% 강도, 280ms 묵직한 바디 블로우
- **Heavy (강 피격, 35~60%)**: 90% 강도, 450ms 강력한 넉다운 충격
- **Critical / KO (필살 피격, 60%~)**: 100% 강도, 700ms 흉부/복부 전체 진동

### 5. 🔍 실시간 비전 디버그 모니터 (Visual Debug HUD)
- 실제 추출되고 있는 체력 게이지 흑백 마스크, OCR 텍스트 전송 서브영역, 1D 스캔라인 수치 및 버퍼 요동폭을 실시간으로 모니터링할 수 있습니다.

---

## 🛠️ 요구 사양 및 준비물

- **하드웨어**:
  - 닌텐도 스위치 및 포켓몬 챔피언스 (PokéChamps)
  - HDMI 캡처보드 (또는 OBS 가상 카메라)
  - bHaptics TactSuit (TactSuit X40, TactSuit X16, Tactosy 등)
  - Windows 10 / 11 PC
- **소프트웨어**:
  - [bHaptics Player](https://www.bhaptics.com/) 설치 및 실행 중이어야 함

---

## 🚀 빠른 시작 (Quick Start)

### 방법 A: 빌드된 실행 파일 (.exe)로 바로 실행하기
1. [Releases](https://github.com/) 탭에서 최신 zip 압축 파일을 다운로드하여 해제합니다.
2. `Pochams_bHaptics.exe` 또는 `run.bat`을 실행합니다.

### 방법 B: Python 소스 코드로 직접 실행하기
```bash
# 1. 저장소 복제 (Clone Repository)
git clone https://github.com/<your-username>/pokeechamps-bhaptics.git
cd pokeechamps-bhaptics

# 2. 필수 패키지 설치
pip install -r requirements.txt

# 3. 프로그램 실행
python main.py
```

---

## 🎮 사용 가이드 (How to Use)

1. **bHaptics Player 실행**: bHaptics Player가 PC에서 실행 중이고 수트가 연결되어 있는지 확인합니다.
2. **프로그램 시작**: `run.bat` 또는 `Pochams_bHaptics.exe`를 실행합니다.
3. **비디오 입력 선택**: 상단 드롭다운에서 캡처보드 또는 OBS 가상 카메라를 선택합니다.
4. **체력바 영역 지정**:
   - 배틀 화면에서 **`[ 🎯 체력바 자동 스냅 ]`** 버튼을 누르거나,
   - 아군 체력바(`현재HP / 최대HP` 숫자 포함 영역)를 마우스로 드래그합니다.
5. **플레이**: 포켓몬이 데미지를 입을 때마다 TactSuit로 생생한 타격감이 전달됩니다!
   - 필요 시 **`[ ⏸️ 체력 감지 일시정지 ]`** 버튼으로 매칭/로비 중 진동을 수동 정지할 수 있습니다.

---

## 📁 프로젝트 구조 (Project Structure)

```
pokeechamps-bhaptics/
├── config.py              # 설정 데이터 모델 (Pydantic / dataclass)
├── config.example.json    # 기본 설정 예시 템플릿
├── haptic_manager.py      # bHaptics 공식 SDK 및 WebSocket 연동 매니저
├── vision_detector.py     # 숫자 최우선 비전 엔진 및 1D 스캔라인 분석기
├── fusion_engine.py       # 비전-햅틱 이벤트 브릿지 엔진
├── main.py                # PySide6 기반 모던 GUI 애플리케이션
├── run.bat                # 원클릭 실행 배치 스크립트
├── requirements.txt       # 의존성 패키지 목록
└── README.md              # 프로젝트 문서
```

---

## 📜 라이선스 (License)

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
All Pokémon assets and trademarks are the property of Nintendo, Creatures Inc., and GAME FREAK inc.
bHaptics is a registered trademark of bHaptics Inc.
