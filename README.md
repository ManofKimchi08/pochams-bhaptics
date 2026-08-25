# PokéChamps x bHaptics Tactile Link v2.1 (포챔스 x bHaptics 실시간 연동 시스템)

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Nintendo%20Switch-E60012?style=for-the-badge&logo=nintendoswitch&logoColor=white" />
  <img src="https://img.shields.io/badge/bHaptics-TactSuit%20X40%20%2F%20X16-00e5ff?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/GUI-PySide6%20Qt%20Docking-41CD52?style=for-the-badge&logo=qt&logoColor=white" />
  <img src="https://img.shields.io/badge/Vision-RapidOCR%20%2B%20OpenCV-FF6F00?style=for-the-badge" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

닌텐도 스위치 포켓몬 챔피언스(포챔스) 게임 화면을 캡처보드 또는 OBS 가상 카메라로 실시간 캡처하여, **아군 포켓몬의 피격 데미지 비율(%)에 비례하는 생생한 햅틱 진동 피드백을 bHaptics TactSuit 슈트로 전달**하는 고성능 비전-햅틱 연동 시스템입니다.

---

## 📑 목차 (Table of Contents)
- [✨ 핵심 기능 (Key Features)](#-핵심-기능-key-features)
- [🖥️ UI 인터페이스 구성 및 조작법](#️-ui-인터페이스-구성-및-조작법)
- [🛠️ 요구 사양 및 준비물](#️-요구-사양-및-준비물)
- [🚀 설치 및 빠른 시작 (Quick Start)](#-설치-및-빠른-시작-quick-start)
- [🎮 상세 사용법 가이드 (User Guide)](#-상세-사용법-가이드-user-guide)
- [❓ 자주 묻는 질문 및 문제 해결 (FAQ & Troubleshooting)](#-자주-묻는-질문-및-문제-해결-faq--troubleshooting)
- [⚙️ 설정 파라미터 안내 (Configuration)](#️-설정-파라미터-안내-configuration)
- [🏗️ 개발자 아키텍처 가이드 (Architecture)](#️-개발자-아키텍처-가이드-architecture)
- [📜 라이선스 (License)](#-라이선스-license)

---

## ✨ 핵심 기능 (Key Features)

### 1. 🎽 피격 패턴별 개별 부위(정면/후면/정+후) 커스텀 제어
* **항목별 독립 부위 설정**: 경타, 중타, 강타, 치명타, 기절, 심장박동, 빨피 상시 등 모든 세부 패턴 카드마다 **`[ 🎽 정+후 (기본) / 👕 정면만 / 🎒 후면만 ]`**을 독립적으로 지정할 수 있습니다.
* **실시간 세기/길이/타격횟수 튜닝**: 세기(0~100%), 지속시간, 타격 횟수(1~5회)를 슬라이더로 즉시 조절하고 각 카드의 `[시험]` 버튼으로 바로 체감할 수 있습니다.

### 2. 🩸 숫자 기반 빨간 체력 (Red HP <= 20%) & 연출 중 진동 유지
* **숫자 기반 정밀 감지**: 색상 바의 불안정한 흔들림 대신, 정확한 체력 비율(`(현재HP / 최대HP) * 100 <= 20%`)로 빨간 체력 상태에 진입합니다.
* **스킬 연출 중 지속 유지 (8.0s 허용)**: 화려한 기술 연출이나 카메라 줌으로 숫자가 잠시 가려지더라도, 포켓몬이 살아있는 한 **심장박동 및 빨피 상시 진동이 끊김 없이 끝까지 지속**됩니다.
* **기절(0%) 및 교체 즉각 해제**: 포켓몬이 쓰러지거나 건강한 포켓몬으로 교체되면 빨간 체력 루프가 즉각 안전하게 종료됩니다.

### 3. 🛡️ 타이머(MM:SS) 오독 원천 차단 및 기절(0/xxx) 완전 분리
* **타이머 블랙리스트**: `04:58`, `05:00` 등 대기/배틀 화면의 타이머 텍스트 및 시계 기호(`⏱`, `⏰`)를 1차 파이프라인에서 100% 감지하여 HP로 오인식하는 현상을 원천 차단했습니다.
* **기절(0/xxx) 판정 독립 수용**: 포켓몬이 기절했을 때(`0 / max_hp`) 배경 일러스트 간섭과 무관하게 `기절 (0%)` 이벤트를 즉각 반영합니다.

### 4. 🖥️ 자유로운 도킹 UI 시스템 & F11 전체 화면
* **QDockWidget 기반 모듈형 패널**: `햅틱 세기 제어`, `장치 설정`, `이벤트 로그` 패널을 자유롭게 분리/이동/탭 결합할 수 있으며, `[🔄 창 배치 초기화]` 버튼으로 언제든 깔끔하게 원상 복구할 수 있습니다.
* **⛶ F11 전체 화면 토글**: 키보드 **`F11`** 키(또는 `Esc` 키)를 눌러 모니터를 꽉 채우는 Full Screen 모드로 즉시 전환할 수 있습니다.
* **🔍 로그 글자 크기 슬라이더**: 이벤트 로그 상단 슬라이더로 글자 크기를 **8pt ~ 22pt**까지 자유롭게 조절할 수 있습니다.

### 5. 🎯 체력바 카드 원클릭 자동 스냅 (Auto-Snap ROI)
* 배틀 화면에서 **`[ 🎯 체력바 자동 스냅 ]`** 버튼을 한 번만 누르면, 1080p/720p 전체 화면에서 포챔스 아군 체력바 카드를 **0.1픽셀 단위로 자동 탐색하여 완벽하게 스냅(Snap)**합니다.

---

## 🖥️ UI 인터페이스 구성 및 조작법

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 🎮 PokéChamps x bHaptics Tactile Link                                                  │
│  [🎽 햅틱 제어] [🔌 장치 설정] [📜 로그 패널] [🔄 창 배치 초기화] [⛶ 전체 화면 (F11)]       │
│ ┌───────────────────────────────────────────────┐ ┌──────────────────────────────────┐ │
│ │ 60FPS 실시간 비디오 뷰어 & ROI 스냅 박스       │ │ 🎽 햅틱 세기 및 진동 제어        │ │
│ │                                               │ │  마스터 세기: ───●─── 100%       │ │
│ │ [ 🎯 펌킨인  0 / 140  (💀 기절) ]             │ │  [🎽 bHaptics 진동 테스트]       │ │
│ ├───────────────────────────────────────────────┤ │  ┌─────────────────────────────┐ │ │
│ │ 📊 실시간 비전 디버그 모니터                  │ │  │ 💥 경타 (0~20%) [부위: 정면만]│ │ │
│ │   [ HP 게이지 마스크 ]   [ OCR 텍스트 크롭 ]    │ │  │ 💥 중타 (20~50%)[부위: 정+후] │ │ │
│ │                            "0 / 140"          │ │  │ 💥 강타 (50~80%)[부위: 정+후] │ │ │
│ ├───────────────────────────────────────────────┤ │  │ 🩸 심장박동    [부위: 정면만]│ │ │
│ │ 아군 잔여 HP: [ 💀 포켓몬 기절 (HP: 0%) ]     │ │  │ 🩸 빨피 상시   [부위: 정+후] │ │ │
│ │   [ 🎯 체력바 자동 스냅 ]   [ ⏸️ 일시정지 ]   │ │  └─────────────────────────────┘ │ │
│ └───────────────────────────────────────────────┘ └──────────────────────────────────┘ │
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
1. 저장소의 최신 빌드 폴더 `dist/Pochams_bHaptics/` 또는 [Releases](https://github.com/ManofKimchi08/pochams_bhaptics/releases)에서 다운로드합니다.
2. `run.bat` 또는 `Pochams_bHaptics.exe`를 더블 클릭하여 실행합니다.

### 방법 2: Python 소스 코드로 직접 실행하기
```bash
# 1. 저장소 복제
git clone https://github.com/ManofKimchi08/pochams_bhaptics.git
cd pochams_bhaptics

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
   - `run.bat`을 실행한 후, 상단 `[입력 장치]` 드롭다운에서 캡처보드 또는 OBS Virtual Camera를 선택합니다.
3. **체력바 영역 지정 (2가지 방법)**:
   - **방법 A (추천)**: 닌텐도 스위치 배틀 화면이 켜진 상태에서 **`[ 🎯 체력바 자동 스냅 ]`** 버튼을 누릅니다. 시스템이 알아서 아군 카드를 찾아 완벽하게 맞춥니다.
   - **방법 B (수동)**: 마우스 왼쪽 버튼으로 화면 좌하단 아군 체력바(`현재HP / 최대HP` 숫자 포함)를 직접 드래그합니다.
4. **전체 화면 전환**:
   - 배틀 중 집중을 위해 **`F11`** 키를 눌러 창 테두리 없이 화면 전체로 꽉 채워 사용할 수 있습니다.
5. **피격 부위 및 패턴 커스텀**:
   - 우측 `햅틱 세기 제어` 패널에서 경타, 중타, 강타, 심장박동 카드의 `[부위]` 드롭다운을 원하는 대로(정면/후면/정+후) 변경하고 `[시험]` 버튼으로 즉시 확인합니다.

---

## ❓ 자주 묻는 질문 및 문제 해결 (FAQ & Troubleshooting)

#### Q1. 진동이 전혀 오지 않아요.
* **확인 1**: PC에서 **bHaptics Player**가 켜져 있고 수트가 페어링되어 있는지 확인하세요.
* **확인 2**: 우측 패널의 `[🎽 bHaptics 진동 테스트]` 버튼 또는 각 카드의 `[시험]` 버튼을 눌렀을 때 수트에 진동이 오는지 확인하세요.
* **확인 3**: 체력바 숫자가 잘려있지 않은지 확인하고 `[ 🎯 체력바 자동 스냅 ]`을 다시 눌러주세요.

#### Q2. 비디오 화면이 검은색으로 나와요.
* OBS 또는 다른 방송 프로그램이 캡처보드 장치를 독점하고 있을 수 있습니다.
* OBS에서 **[가상 카메라 시작 (Start Virtual Camera)]**을 누른 후, 본 프로그램에서 **"OBS Virtual Camera"**를 선택하시면 충돌 없이 화면을 공유할 수 있습니다.

#### Q3. 스킬 이펙트나 카메라 회전 중에 진동이 끊기지 않나요?
* 본 프로그램은 **8.0초 연출 지속 타이머**가 적용되어 있어, 화려한 기술 연출이나 카메라 줌 중에도 포켓몬이 살아있는 한 심장박동과 빨피 상시 진동이 매끄럽게 유지됩니다.

---

## ⚙️ 설정 파라미터 안내 (Configuration)

`config.json` 파일을 통해 고급 설정을 직접 튜닝할 수 있으며, GUI 변경 시 자동 저장됩니다:

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `min_damage_threshold` | `3.0` | 진동을 발생시킬 최소 데미지 기준 (%) |
| `master_intensity` | `100` | 전체 마스터 진동 세기 ($0\sim 100$) |
| `red_hp_threshold` | `20.0` | 빨간 체력(심장박동/상시루프) 활성화 기준 잔여 체력 (%) |
| `log_font_size` | `11` | 이벤트 로그 창 글자 크기 (pt) |
| `show_floating_overlay` | `true` | 독립 플로팅 HUD 창 활성화 여부 |
| `haptic_details` | (객체) | 각 패턴별 세기, 길이, 타격횟수, 부위(`All`/`VestFront`/`VestBack`) 설정 |

---

## 🏗️ 개발자 아키텍처 가이드 (Architecture)

시스템 내부 아키텍처, 60FPS 비동기 멀티스레딩 모델, RapidOCR 전처리 파이프라인, 모터 매트릭스 알고리즘에 대한 자세한 기술 문서는 [**`ARCHITECTURE.md`**](ARCHITECTURE.md)를 참조하세요.

---

## 📜 라이선스 (License)

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.  
* All Pokémon assets and trademarks are the property of Nintendo, Creatures Inc., and GAME FREAK inc.  
* bHaptics is a registered trademark of bHaptics Inc.
��언스 (PokéChamps)
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
