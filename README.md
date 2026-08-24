# PokéChamps x bHaptics Tactile Link (포챔스 x bHaptics 실시간 연동 시스템)

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Nintendo%20Switch-E60012?style=for-the-badge&logo=nintendoswitch&logoColor=white" />
  <img src="https://img.shields.io/badge/bHaptics-TactSuit%20X40%20%2F%20X16-00e5ff?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/GUI-PySide6%20Qt-41CD52?style=for-the-badge&logo=qt&logoColor=white" />
  <img src="https://img.shields.io/badge/Vision-RapidOCR%20%2B%20OpenCV-FF6F00?style=for-the-badge" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

닌텐도 스위치 포켓몬 챔피언스(포챔스) 게임 화면을 캡처보드 또는 OBS 가상 카메라로 실시간 캡처하여, **아군 포켓몬의 피격 데미지 비율(%)에 비례하는 생생한 햅틱 진동 피드백을 bHaptics TactSuit 슈트로 전달**하는 고성능 비전-햅틱 연동 시스템입니다.

---

## 📑 목차 (Table of Contents)
- [✨ 핵심 기능 (Key Features)](#-핵심-기능-key-features)
- [🖥️ UI 인터페이스 구성](#️-ui-인터페이스-구성)
- [🛠️ 요구 사양 및 준비물](#️-요구-사양-및-준비물)
- [🚀 설치 및 빠른 시작 (Quick Start)](#-설치-및-빠른-시작-quick-start)
- [🎮 상세 사용법 가이드 (User Guide)](#-상세-사용법-가이드-user-guide)
- [❓ 자주 묻는 질문 및 문제 해결 (FAQ & Troubleshooting)](#-자주-묻는-질문-및-문제-해결-faq--troubleshooting)
- [⚙️ 설정 파라미터 안내 (Configuration)](#️-설정-파라미터-안내-configuration)
- [🏗️ 개발자 아키텍처 가이드 (Architecture)](#️-개발자-아키텍처-가이드-architecture)
- [📜 라이선스 (License)](#-라이선스-license)

---

## ✨ 핵심 기능 (Key Features)

### 1. 🔢 숫자 최우선 권한 & 연출 자동 동결 (Number-First & Cutscene Hold)
- **단일 진실 숫자 판정**: 배경 이펙트, 경기장 광택, 캐릭터 꼬리/날개 가림에 의해 출렁이는 색상 막대 대신, 화면에 선명하게 표시되는 **정확한 체력 숫자(`현재HP / 최대HP`, 예: `78/207`)를 최우선 기준**으로 삼아 데미지 비율($\Delta\text{HP}$)을 계산합니다.
- **연출 자동 동결 (Cutscene Hold)**: 스킬 컷신, 포켓몬 교체 연출, 매칭 대기 화면 등으로 숫자가 보이지 않을 때는 즉시 `[ 🎬 연출 중 (체력 동결) ]`로 자동 전환되어 **가짜 진동을 $0\%$로 원천 차단**합니다.

### 2. 🎯 체력바 카드 원클릭 자동 스냅 (Auto-Snap ROI)
- 배틀 화면에서 **`[ 🎯 체력바 자동 스냅 ]`** 버튼을 한 번만 누르면, 1080p/720p 전체 화면에서 포챔스 아군 체력바 카드를 **0.1픽셀 단위로 자동 탐색하여 딱 맞게 스냅(Snap)**합니다. 손으로 번거롭게 맞출 필요가 없습니다.

### 3. 🪟 독립 투명 플로팅 HUD & 2D TactSuit 실시간 모니터
- **독립 플로팅 HUD**: 방송 화면(OBS 오버레이), 서브 모니터 어디든 자유롭게 마우스로 드래그하여 배치할 수 있는 투명 Always-on-Top 진동 모니터 창을 지원합니다.
- **2D 실시간 모터 뷰어**: 전면(Front 20개)과 후면(Back 20개) 모터의 실시간 진동 강도 및 부드러운 네온 감쇄 애니메이션을 실시간으로 표시합니다.

### 4. ⚡ 4단계 데미지 비례 다이내믹 햅틱 엔진
- **Light (약 피격, ~15%)**: 40% 강도, 180ms 찰나의 잽 피격
- **Medium (중 피격, 15~35%)**: 70% 강도, 280ms 묵직한 바디 블로우
- **Heavy (강 피격, 35~60%)**: 90% 강도, 450ms 강력한 넉다운 충격
- **Critical / KO (필살 피격, 60%~)**: 100% 강도, 700ms 흉부/복부 전체 진동

### 5. 🔍 실시간 비전 디버그 모니터 (Visual Debug HUD)
- 실제 추출되고 있는 체력 게이지 흑백 마스크, OCR 텍스트 전송 서브영역, 1D 스캔라인 수치 및 버퍼 요동폭을 한눈에 보며 실시간으로 진단할 수 있습니다.

---

## 🖥️ UI 인터페이스 구성

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 🎮 캡처보드 / OBS 화면 인식                                                             │
│  [ 입력 카메라/캡처: 0 (기본) ▼ ]  [☑️ 화면 내부 오버레이]  [☑️ 🪟 플로팅 창]  [☑️ 🔍 디버그 모니터]│
│ ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 🔍 실시간 비전 디버그 모니터 (비전 내부 실시간 진단)                                  │ │
│ │   [ 📊 HP 게이지 마스크 ]     [ 🔢 OCR 텍스트 크롭 ]    📈 실시간 진단 메트릭          │ │
│ │       ■■■■■■□□□□                  "78/207"           1D 스캔라인: 37.7%             │ │
│ │                                                      OCR 수치: 78/207 (37.7%)      │ │
│ │                                                      버퍼 요동폭: 0.0% (안정)       │ │
│ └────────────────────────────────────────────────────────────────────────────────────┘ │
│ ┌────────────────────────────────────────────────────────────────────────────────────┐ │
│ │ 60FPS 실시간 비디오 뷰어 (녹색 ROI 박스 및 드래그 영역)                             │ │
│ └────────────────────────────────────────────────────────────────────────────────────┘ │
│ 아군 잔여 HP: [================================= 100% ]                                │
│   [ 🎯 체력바 자동 스냅 ]   [ ⏸️ 체력 감지 일시정지 ]   [ 🔄 100% 기준 보정 ]            │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 요구 사양 및 준비물

* **게임 환경**: 닌텐도 스위치 및 포켓몬 챔피언스 (PokéChamps)
* **비디오 캡처**: HDMI 캡처보드 (Elgato, AVerMedia 등) 또는 OBS Studio 가상 카메라
* **햅틱 장비**: bHaptics TactSuit (TactSuit X40, TactSuit X16, Tactosy 등)
* **운영체제**: Windows 10 / 11 (64-bit)
* **필수 소프트웨어**: [bHaptics Player](https://www.bhaptics.com/) 설치 및 실행 필수

---

## 🚀 설치 및 빠른 시작 (Quick Start)

### 방법 1: 독립 실행 파일(.exe)로 즉시 실행하기 (가장 추천 ⭐)
1. 저장소의 최신 빌드 폴더 `dist/Pochams_bHaptics/` 또는 [Releases](https://github.com/ManofKimchi08/pochams-bhaptics/releases)에서 다운로드합니다.
2. `run.bat` 또는 `Pochams_bHaptics.exe`를 더블 클릭하여 실행합니다.

### 방법 2: Python 소스 코드로 직접 실행하기
```bash
# 1. 저장소 복제
git clone https://github.com/ManofKimchi08/pochams-bhaptics.git
cd pochams-bhaptics

# 2. 필수 의존성 설치
pip install -r requirements.txt

# 3. 애플리케이션 시작
python main.py
```

---

## 🎮 상세 사용법 가이드 (User Guide)

1. **bHaptics Player 켜기**:
   - bHaptics Player를 실행하고 TactSuit 슈트가 블루투스 또는 동글로 정상 연결되었는지 확인합니다.
2. **프로그램 실행 및 영상 장치 선택**:
   - `run.bat`을 실행한 후, 상단 `[입력 카메라/캡처보드]` 드롭다운에서 캡처보드 또는 OBS Virtual Camera를 선택합니다.
3. **체력바 영역 지정 (2가지 방법)**:
   - **방법 A (추천)**: 닌텐도 스위치 배틀 화면이 켜진 상태에서 **`[ 🎯 체력바 자동 스냅 ]`** 버튼을 누릅니다. 시스템이 알아서 아군 카드를 찾아 완벽하게 맞춥니다.
   - **방법 B (수동)**: 마우스 왼쪽 버튼으로 화면 좌하단 아군 체력바(`현재HP / 최대HP` 숫자 포함)를 직접 드래그합니다.
4. **플로팅 HUD 창 활용**:
   - **`[☑️ 🪟 독립 플로팅 창 켜기]`**를 체크하면 투명 창이 화면에 나타납니다. 원하는 위치로 마우스 드래그하여 옮겨두고 게임에 몰입하세요.
5. **매칭 및 메뉴 대기 중 제어**:
   - 게임 중 매칭 대기나 픽창에서는 **`[ ⏸️ 체력 감지 일시정지 ]`** 버튼을 눌러 불필요한 감지를 잠시 멈출 수 있습니다.

---

## ❓ 자주 묻는 질문 및 문제 해결 (FAQ & Troubleshooting)

#### Q1. 진동이 전혀 오지 않아요.
* **확인 1**: PC에서 **bHaptics Player**가 켜져 있고 수트가 페어링되어 있는지 확인하세요.
* **확인 2**: 우측 패널의 `[🎽 bHaptics 연결 테스트]` 버튼을 눌렀을 때 수트에 진동이 오는지 테스트해 보세요.
* **확인 3**: 체력바 숫자가 너무 작게 잘려있지 않은지 확인하고 `[ 🎯 체력바 자동 스냅 ]`을 다시 눌러주세요.

#### Q2. 비디오 화면이 검은색으로 나와요.
* OBS 또는 다른 방송 프로그램이 캡처보드 장치를 독점하고 있을 수 있습니다.
* OBS에서 **[가상 카메라 시작 (Start Virtual Camera)]**을 누른 후, 본 프로그램에서 **"OBS Virtual Camera"**를 선택하시면 충돌 없이 화면을 공유할 수 있습니다.

#### Q3. 스킬 이펙트나 캐릭터 꼬리 때문에 진동이 잘못 울리지 않나요?
* 본 프로그램은 **숫자 최우선 권한(Number-First Authority)**이 적용되어 있어, 숫자가 정확히 줄어들었을 때만 진동이 발생하며, 숫자가 가려지는 동안에는 `[ 🎬 연출 중 ]` 상태로 진동이 $100\%$ 차단됩니다.

---

## ⚙️ 설정 파라미터 안내 (Configuration)

`config.json` 파일을 통해 고급 설정을 직접 튜닝할 수 있습니다:

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `min_damage_threshold` | `3.0` | 진동을 발생시킬 최소 데미지 기준 (%) |
| `haptic_light_intensity` | `40` | 약 피격 진동 세기 ($0\sim 100$) |
| `haptic_medium_intensity` | `70` | 중 피격 진동 세기 ($0\sim 100$) |
| `haptic_heavy_intensity` | `90` | 강 피격 진동 세기 ($0\sim 100$) |
| `haptic_critical_intensity` | `100` | 필살/KO 피격 진동 세기 ($0\sim 100$) |
| `show_floating_overlay` | `true` | 독립 플로팅 HUD 창 활성화 여부 |
| `show_visual_overlay` | `true` | 비디오 화면 내부 진동 오버레이 표시 여부 |

---

## 🏗️ 개발자 아키텍처 가이드 (Architecture)

시스템 내부 아키텍처, 60FPS 멀티스레딩 모델, RapidOCR 파이프라인, 모터 매트릭스 알고리즘에 대한 자세한 기술 문서는 [**`ARCHITECTURE.md`**](ARCHITECTURE.md)를 참조하세요.

---

## 📜 라이선스 (License)

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.  
* All Pokémon assets and trademarks are the property of Nintendo, Creatures Inc., and GAME FREAK inc.  
* bHaptics is a registered trademark of bHaptics Inc.
