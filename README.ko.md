<div align="center">

# WP Elementor Ops

### WordPress + Elementor 사이트를 안전하게 감사하고 편집하는 스킬. 실제 프로덕션에서 발생한 실수와 그 해결법이 그대로 담겨 있습니다.

<p>
  <a href="https://github.com/Moksa1123/wp-elementor-ops"><img src="https://img.shields.io/github/stars/Moksa1123/wp-elementor-ops?style=flat-square&logo=github&logoColor=white&color=181717" alt="GitHub stars"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="MIT"></a>
</p>

<p>
  <img src="https://img.shields.io/badge/format-Agent%20Skill-blue?style=flat-square" alt="Agent Skill">
  <img src="https://img.shields.io/badge/python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/php-7.4%2B-777BB4?style=flat-square&logo=php&logoColor=white" alt="PHP 7.4+">
  <img src="https://img.shields.io/badge/AI%20platforms-8-blueviolet?style=flat-square" alt="8 AI platforms">
</p>

<p>
  <a href="#빠른-시작"><strong>시작하기</strong></a> ·
  <a href="https://github.com/Moksa1123/wp-elementor-ops"><strong>GitHub</strong></a> ·
  <a href="https://github.com/Moksa1123/rankmath-seo-wp"><strong>자매 프로젝트</strong></a> ·
  <a href="https://moksaweb.com"><strong>moksaweb.com</strong></a>
</p>

<p>
  <a href="README.md">English</a> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <a href="README.ja.md">日本語</a> ·
  <strong>한국어</strong>
</p>

</div>

---

## 이럴 때 사용하세요

- **"이 WordPress 사이트 상태 점검해줘" / "안 쓰는 플러그인 어떤 거야?"** —
  추측이 아니라 플러그인의 *실제* 블록/숏코드/옵션 시그니처를 먼저 찾습니다
  (슬러그로 추측하는 것이 이 스킬이 막으려는 가장 흔한 실수입니다). 실제
  사용 여부를 교차 확인하고, "고아 미디어" 오탐 함정을 방지합니다.
- **"이 공유 Elementor 템플릿 수정해줘"** — `_elementor_data` JSON 구조를
  한 단계 누락 없이 정확히 탐색하고, 게시물마다 달라져야 하는 콘텐츠는
  고정된 위젯이 아니라 동적 숏코드로 변환하며, 캐시를 올바른 계층 순서로
  플러시합니다.
- **"이 Elementor 위젯에는 어떤 설정이 있지?"** — 실제 운영 중인
  Elementor + Elementor Pro에서 추출한 데이터(위젯 164개, 컨트롤 48,238개,
  추측이 아닌 실측)와, 전체 위젯의 98%가 공유하는 "고급(Advanced)" 탭
  섹션 전체가 문서화되어 있습니다.
- **"수정했는데 반영이 안 돼"** — 실제 사고에서 얻은 캐시 레이어 및 압축/
  스크린샷 축소 관련 디버깅 노트.

## 빠른 시작

```bash
git clone https://github.com/Moksa1123/wp-elementor-ops.git
cd wp-elementor-ops
python tools/install-skill.py --list                 # 지원 플랫폼 목록 보기
python tools/install-skill.py claude-code             # 현재 프로젝트에 설치
python tools/install-skill.py claude-code --global    # 전역(모든 프로젝트)으로 설치
```

전체 계약 내용은 `SKILL.md`, 방법론은 `references/`를 참고하세요.

## 저장소 구조

```
wp-elementor-ops/
├── SKILL.md                        # 스킬 계약 — AI 어시스턴트가 자동으로 불러옵니다
├── README.md                       # 이 파일 (+ zh-TW / ja / ko 번역)
├── CLAUDE.md                       # AI 개발 규칙 + 정보 삭제(sanitisation) 규칙
├── LICENSE                         # MIT
├── references/
│   ├── plugin-audit-methodology.md         # 사용 여부를 판단하기 전에 "진짜" 시그니처부터 찾기
│   ├── elementor-safe-edit.md              # 공유 템플릿 안전 편집 절차
│   ├── elementor-widgets-and-containers.md # 컨테이너/위젯/다이나믹 태그 데이터 모델, 실측 검증
│   ├── dynamic-ghost-text-pattern.md       # 정적 콘텐츠를 게시물별 동적 콘텐츠로 바꾸는 실전 예제
│   ├── wp-cli-safe-scripting.md            # 따옴표/이스케이프/파일 기반 실행 원칙
│   └── multiplatform-install-verification.md # 플랫폼별 설치 규칙과 검증 날짜
├── tools/
│   ├── audit-plugin-usage.php         # `wp eval-file`로 실행 — 실제 사용 여부 교차 확인
│   ├── audit-orphan-media.php         # `wp eval-file`로 실행 — 오탐 방지 로직이 포함된 고아 미디어 탐지
│   ├── extract-elementor-controls.php # `wp eval-file`로 실행 — 내 사이트에서 컨트롤 데이터 재추출
│   ├── ghost-glint-svg.py             # 독립 실행형 — 고스트 텍스트 SVG 비율 미리보기/조정
│   └── install-skill.py               # 멀티 플랫폼 설치기
├── data/
│   ├── platform-conventions.csv          # 플랫폼별 설치 경로와 검증 날짜
│   └── elementor-core-pro-controls.json  # 위젯 135개의 전체 컨트롤 스키마 (실제 운영 환경에서 추출)
└── assets/templates/platforms/*.json  # 플랫폼별 설치 설정
```

## 이 프로젝트가 존재하는 이유

실제 운영 중인 WooCommerce + Elementor Pro 사이트의 실제 디버깅 과정에서
탄생했습니다: 어떤 플러그인은 *추측한* 블록 이름으로 검색했더니 아무것도
나오지 않아 비활성화되었는데, *실제* 이름(제작자 고유의 네임스페이스)은
이미 게시된 글 10개에서 사용되고 있었습니다. 공유 Elementor 템플릿의
장식용 텍스트는 그 템플릿을 쓰는 모든 게시물에서 똑같이 하드코딩되어
있었습니다. "고아 미디어" 전수 조사는 관련 없는 조회수 카운터 메타데이터를
실제 참조로 착각한 탓에, ACF 이미지 필드로 실제 참조되고 있던 파일을
하마터면 잘못 표시할 뻔했습니다. 여기 있는 모든 레퍼런스 문서는 실제
사건 하나하나로 거슬러 올라갑니다 — 처음에 잘못 짚었던 부분까지 포함해서,
그리고 이 프로젝트의 감사 도구 자체가 개발 중에 발견한 진짜 버그
(`wp eval-file`은 유닉스 CLI처럼 `--` 구분자나 `--flag=value` 문법을
지원하지 않는다는 사실)까지 포함해서요.

## 추측이 아니라 검증된 것

이 저장소에는 "그럴듯하다"만으로는 부족하다는 이유만으로 존재하는 것이
두 가지 있습니다:

- **Elementor의 데이터 모델**(`elementor-widgets-and-containers.md`,
  `data/elementor-core-pro-controls.json`)은 실제 운영 중인 설치 환경의
  위젯 등록 정보를 직접 조회해서 추출한 것이며, 학습 데이터나 기억으로
  작성한 것이 아닙니다. 실제 추출 과정에서 진짜 빈틈이 발견된 부분
  (Border/Box-Shadow/Custom CSS는 Elementor Pro가 훅을 통해 주입하는
  기능인데, 단순한 `get_controls()` 호출로는 그 훅이 발동하지 않습니다)은
  숨기지 않고 빈틈으로 명시했습니다.
- **멀티 플랫폼 설치 규칙**(`multiplatform-install-verification.md`)에는
  검증 날짜가 기록되어 있고 독립적으로 재확인되었습니다 — 지원하는 8개
  플랫폼 중 3개가 자매 스킬 자체의 표가 작성된 지 약 6주 만에 이미
  바뀌어 있었습니다.

## 기여하기

`CONTRIBUTING.md`를 참고하세요. 이 프로젝트에서는 정보 삭제(sanitisation)가
다른 저장소보다 훨씬 중요합니다 — 실제 사이트에서 파생된 내용이 포함된 PR을
보내기 전에 `CLAUDE.md`의 "정보 삭제 규칙" 섹션을 먼저 읽어주세요.

## 제작자

**moksa** ([moksaweb.com](https://moksaweb.com)) 개발 및 유지 관리. MIT 라이선스.
