# 🔍 비전 인식 및 OCR 파이프라인 설계서 (Vision & RapidOCR Pipeline)

문서 버전: v2.1 | 최종 수정일: 2026-08-26

## 1. 개요 (Overview)

본 문서는 닌텐도 스위치 『포켓몬 챔피언스 (PokéChamps)』의 60FPS 실시간 배틀 화면에서 아군 포켓몬의 체력 정보(`현재HP / 최대HP`)를 0.1초 주기로 정밀 추출하는 **3중 적응형 전처리 및 비동기 RapidOCR 파이프라인**의 기술 명세서입니다.

---

## 2. 파이프라인 처리 흐름도 (Dataflow)

```
[ 60FPS 실시간 프레임 캡처 (1080p/720p) ]
                   │
                   ▼
[ 지능형 체력바 카드 ROI 크롭 (Auto-Snap) ]
                   │
                   ▼
[ 하단 우측 텍스트 집중 서브영역 분리 (num_crop) ] ─── (포켓몬 일러스트 및 성별 기호 ♀/♂ 배제)
                   │
                   ▼
[ 1단계: 3.0x 바이큐빅 확대 + 언샤프 마스킹 (Unsharp Mask) ]
                   │
                   ├───────────────────────────────┬───────────────────────────────┐
                   ▼                               ▼                               ▼
      [ 경로 A: CLAHE 명암비 강화 ]     [ 경로 B: HSV 순수 화이트 마스크 ]     [ 경로 C: Otsu 적응형 이진화 ]
      (Gray + CLAHE Clip=2.5)          (V>160, S<80 고순도 화이트)        (Enhanced Gray + Otsu Thresh)
                   │                               │                               │
                   └───────────────────────────────┼───────────────────────────────┘
                                                   │
                                                   ▼
                                  [ RapidOCR 텍스트 인식 엔진 실행 ]
                                                   │
                                                   ▼
                              [ 스마트 포맷 파싱 & 정규식 유효성 검증 ]
                                                   │
                                                   ▼
                            [ 2프레임 연속 합의 락 (Consensus Lock) 판정 ]
```

---

## 3. 세부 기술 구현 (Technical Specifications)

### 3.1 텍스트 서브영역 격리 (Sub-Region Isolation)
포켓몬 배틀 카드의 좌측에는 포켓몬 스프라이트(호박 펌킨인, 피카츄, 한카리아스 등)가 위치하고 상단에는 이름과 성별 아이콘(`♀`, `♂`)이 위치합니다.
이 영역이 OCR 또는 게이지 스캔에 포함되면 문자 오독(`61/140`)이나 색상 간섭(`게이지 96% 오판`)이 발생하므로, 아래와 같이 **하단 우측 숫자 영역만 엄격 격리 크롭**합니다.

```python
rh_sub, rw_sub = roi_img.shape[:2]
# 상단 45% (이름/성별) 및 좌측 28% (포켓몬 일러스트) 배제
num_crop = roi_img[int(rh_sub * 0.45):, int(rw_sub * 0.28):]
```

---

### 3.2 3.0x 바이큐빅 확대 및 샤프닝 (Unsharp Masking)
포챔스 게임 내 체력 폰트는 기울임(Italic)과 네온 외곽선 효과가 적용되어 있어, 원본 해상도에서는 획이 뭉개집니다.
고품질 바이큐빅 인터폴레이션과 언샤프 필터로 글자의 외곽선을 선명하게 살립니다.

```python
# 1. 3.0x 바이큐빅 고해상도 확대
scaled = cv2.resize(num_crop, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)

# 2. 언샤프 마스킹 필터 (Unsharp Mask)
gaussian = cv2.GaussianBlur(scaled, (0, 0), 2.0)
unsharp = cv2.addWeighted(scaled, 2.0, gaussian, -1.0, 0)
```

---

### 3.3 3단 적응형 전처리 경로 (3-Tier Preprocessing Pipeline)

1. **경로 1: CLAHE (Contrast Limited Adaptive Histogram Equalization)**
   * 배경이 어둡고 글자가 밝을 때 국소 영역별 히스토그램을 균일화하여 명암비를 극대화합니다.
   * `clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))`
2. **경로 2: HSV 순수 화이트 마스크 (High-Value Low-Saturation Mask)**
   * 스킬 불꽃이나 경기장 네온 바닥의 유색 파티클을 100% 제거하고 오직 흰색 텍스트 픽셀만 추출합니다.
   * `mask_white = cv2.inRange(hsv, np.array([0, 0, 160]), np.array([180, 80, 255]))`
3. **경로 3: 적응형 Otsu 이진화 (Adaptive Otsu Threshold)**
   * 특수 조명 상황에서 최적의 전경/배경 임계값을 자동으로 계산하여 이진화합니다.

---

### 3.4 스마트 정규식 파서 (Smart HP Parsing)

추출된 원시 텍스트에서 불필요한 기호를 정제하고, 포챔스의 실제 체력 형식(`현재 / 최대`)을 완벽하게 디코딩합니다:

* **타이머 사전 배제**: `04:58`, `⏱` 등 콜론(`:`)이 포함된 시간 텍스트는 슬래시 치환에서 제외하고 즉시 거부.
* **정규식 매칭**: `r'(\d{1,3})\s*/\s*(\d{2,3})'` 형식 추출.
* **붙어있는 연속 숫자 분리 (Heuristic Split)**:
  * 7자리 (`155/155` -> `1557155` 형태): `c=d[:3], m=d[4:]`
  * 6자리 (`155155` -> `155/155`, `781207` -> `78/207`): 중간 구분자(1/7) 분리.
* **물리적 한계 검증 (Sanity Bounds)**:
  * `40 <= 최대HP <= 750` 및 `0 <= 현재HP <= 최대HP` 조건을 만족할 때만 유효 수치로 인정.
