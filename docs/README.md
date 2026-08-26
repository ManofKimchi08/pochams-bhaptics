# 📚 PokéChamps x bHaptics 개발자 및 기술 설계 문서 (Technical Documentation Index)

이 디렉터리(`docs/`)에는 『포켓몬 챔피언스 x bHaptics 실시간 연동 시스템』의 핵심 알고리즘, 비전 파이프라인, 노이즈 방어 체계, 햅틱 모터 매트릭스, 제품 요구사항 명세가 체계적으로 정리되어 있습니다.

---

## 📑 문서 목차 (Documentation Index)

### 1. 🔍 비전 인식 및 OCR 파이프라인
* 📄 [**`image_recognition_pipeline_ko.md`**](image_recognition_pipeline_ko.md)
  * 60FPS 실시간 비디오 캡처 및 아군 체력바 ROI 자동 스냅
  * 3.0x 바이큐빅 확대 + Unsharp Masking + 3단 적응형 전처리(CLAHE / White Mask / Otsu)
  * 스마트 정규식 파서 및 포챔스 전용 수치 디코딩 알고리즘

### 2. 🛡️ 실시간 노이즈 방어 및 6대 안전망
* 📄 [**`noise_defense_and_safety_net_ko.md`**](noise_defense_and_safety_net_ko.md)
  * 6중 실시간 노이즈 방어 체계 아키텍처
  * 2프레임 연속 일치 합의 락 (2-Frame Consensus Lock) 설계
  * 8.0초 연출 자동 동결 (Cutscene Hold) 및 포켓몬 교체/기절 안전 분기

### 3. 🎽 햅틱 엔진 및 40점 모터 매트릭스
* 📄 [**`haptic_engine_and_motor_mapping_ko.md`**](haptic_engine_and_motor_mapping_ko.md)
  * 4단계 피격 등급(경타/중타/강타/치명타) 및 기절 모터 매핑
  * 부위별(정면/후면/전체) 독립 라우팅 알고리즘
  * 20% 빨피 심장박동 펄스(0.85s) 및 베이스 상시 루프 제어
  * TactSuit X40 / X16 자동 다운샘플링 및 2D 실시간 네온 감쇄 렌더러

### 4. 🏗️ 시스템 아키텍처 및 멀티스레딩
* 📄 [**`system_architecture_and_threading_ko.md`**](system_architecture_and_threading_ko.md)
  * 3계층 비동기 멀티스레딩 모델 (Capture ➔ OCR ➔ Haptic)
  * 배틀 상태 머신 (Finite State Machine)
  * 스레드 세이프 동기화 및 락(Lock) 안전성

### 5. 📋 제품 요구사항 정의서 (PRD)
* 📄 [**`product_requirements_and_spec_ko.md`**](product_requirements_and_spec_ko.md)
  * 프로젝트 목적, 배경 및 20대 핵심 기능 요구사항 정의
  * 품질 속성 및 지연 시간(Latency) 목표
