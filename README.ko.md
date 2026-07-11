<div align="center">

# Elementor Headless

### JSON과 메타 데이터를 직접 읽고 써서 Elementor 페이지를 만들고 수정합니다. 비주얼 에디터가 필요 없습니다. Pro 전용 기능은 전부 명시적으로 표시됩니다.

<p>
  <a href="https://github.com/Moksa1123/elementor-headless"><img src="https://img.shields.io/github/stars/Moksa1123/elementor-headless?style=flat-square&logo=github&logoColor=white&color=181717" alt="GitHub stars"></a>
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
  <a href="https://github.com/Moksa1123/elementor-headless"><strong>GitHub</strong></a> ·
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

## 이게 뭔가요

Elementor를 헤드리스 방식으로 다룹니다: 페이지는 컨테이너와 위젯으로
이루어진 JSON 트리이고, 각 위젯은 타입이 정해진 필드들의 `settings`
객체입니다. 이 스킬은 AI 에이전트에게 실제로 검증된 전체 파라미터
지도——위젯 컨트롤, 스타일 그룹, 반응형 브레이크포인트, 템플릿 조건,
다이나믹 태그——를 제공하여, 비주얼 에디터를 한 번도 열지 않고도 데이터만
으로 페이지를 만들고 재구성할 수 있게 합니다.

사이트 상태 점검이나 플러그인 감사 도구가 **아닙니다** — 그건 명확히
범위 밖입니다. 이 스킬은 "진단"이 아니라 "구축"에 관한 것입니다.

## 다루는 범위

- **템플릿**: Theme Builder 템플릿의 생성/읽기/적용
  (`elementor_library` CRUD, `_elementor_template_type`)
- **표시 조건(Display Conditions)과 고급 조건(Advanced Conditions)**:
  Include/Exclude 조건의 타입과 이름을 완전히 정리 (general／singular／
  archive 3대 분류와 Elementor Pro가 제공하는 모든 하위 조건), 그리고
  경쟁하는 여러 템플릿 사이의 실제 충돌 해결 방식(등록 순서가 아니라
  구체성 기반 우선순위)
- **RWD**: 브레이크포인트별 스타일 파라미터 — 전체 Elementor 컨트롤의
  20%가 `_tablet`/`_mobile` 반응형 변형을 갖고 있음을 실측으로 확인
- **커스텀 설정**: Border, Box Shadow, Typography, Background 뒤에
  공통으로 있는 Group Control 메커니즘(코어 Elementor, 무료)과 Custom CSS
  주입(진짜 Pro 전용, 훅으로 주입 — 추측이 아니라 소스코드로 검증)
- **Free vs Pro, 추측이 아니라 검증된 것**: 모든 위젯과 기능의 출처를
  실제 `elementor` vs `elementor-pro` 플러그인 디렉터리와 라이선스 게이트
  코드에 대조합니다. 이 프로젝트는 개발 중 한 번 Border/Box-Shadow 판단을
  잘못했습니다(Pro 전용이라고 추측했지만 실제로는 Free) — 소스코드와
  대조해서 바로잡았고, 그 수정 과정과 검증 방법 둘 다 문서화되어 있습니다

## 빠른 시작

```bash
git clone https://github.com/Moksa1123/elementor-headless.git
cd elementor-headless
python tools/install-skill.py --list                 # 지원 플랫폼 목록 보기
python tools/install-skill.py claude-code             # 현재 프로젝트에 설치
python tools/install-skill.py claude-code --global    # 전역(모든 프로젝트)으로 설치
```

전체 계약 내용은 `SKILL.md`, 데이터 모델 세부사항은 `references/`를
참고하세요.

## 저장소 구조

```
elementor-headless/
├── SKILL.md                        # 스킬 계약 — AI 어시스턴트가 자동으로 불러옵니다
├── README.md                       # 이 파일 (+ zh-TW / ja / ko 번역)
├── CLAUDE.md                       # AI 개발 규칙 + Free/Pro 규칙 + 정보 삭제 규칙
├── LICENSE                         # MIT
├── references/
│   ├── elementor-widgets-and-containers.md   # 컨테이너/위젯/다이나믹 태그 데이터 모델, 실측 검증
│   ├── elementor-style-system.md             # Group Control 메커니즘, Custom CSS, Free/Pro 검증 방법
│   ├── elementor-templates-and-conditions.md # 템플릿 CRUD, 완전한 표시/고급 조건 체계
│   ├── elementor-safe-edit.md                # 공유 템플릿 편집 절차, JSON 경로 탐색 원칙
│   ├── dynamic-ghost-text-pattern.md         # 정적 콘텐츠를 게시물별 동적 콘텐츠로 바꾸는 실전 예제
│   ├── wp-cli-safe-scripting.md              # 따옴표/이스케이프/파일 기반 실행 원칙
│   └── multiplatform-install-verification.md # 플랫폼별 설치 규칙과 검증 날짜
├── tools/
│   ├── extract-elementor-controls.php # `wp eval-file`로 실행 — 내 사이트에서 컨트롤 데이터 재추출
│   ├── ghost-glint-svg.py             # 독립 실행형 — 고스트 텍스트 SVG 비율 미리보기/조정
│   └── install-skill.py               # 멀티 플랫폼 설치기
├── data/
│   ├── platform-conventions.csv          # 플랫폼별 설치 경로와 검증 날짜
│   └── elementor-core-pro-controls.json  # 위젯 135개의 전체 컨트롤 스키마 (실제 운영 환경에서 추출)
└── assets/templates/platforms/*.json  # 플랫폼별 설치 설정
```

## 추측이 아니라 검증된 것

- **위젯 164개, 컨트롤 48,238개**를 실제 운영 중인 Elementor +
  Elementor Pro에서 추출 — 학습 데이터로 작성한 것이 아닙니다.
- **전체 위젯의 98%가 공유하는 9개의 "고급(Advanced)" 탭 섹션**, 각각의
  완전한 실제 컨트롤 목록.
- **모든 표시/고급 조건 타입**을 Elementor Pro의 `Condition_Base`
  하위 클래스에서 직접 열거, 여러 템플릿이 경쟁할 때의 구체성 기반
  우선순위 해결 로직까지 포함.
- **Free vs Pro 경계는 소스코드와 대조하여 검증**(플러그인 디렉터리 +
  라이선스 게이트 코드) — 기능이 얼마나 고급스러워 보이는지로 추측한
  것이 아닙니다.
- **멀티 플랫폼 설치 규칙**에는 검증 날짜가 기록되어 있고 독립적으로
  재확인되었습니다 — 지원하는 8개 플랫폼 중 3개가 자매 스킬 자체의 표가
  작성된 지 약 6주 만에 이미 바뀌어 있었습니다
  (`multiplatform-install-verification.md` 참고).

## 기여하기

`CONTRIBUTING.md`를 참고하세요. 이 프로젝트에서는 정보 삭제가 다른
저장소보다 훨씬 중요합니다 — PR을 보내기 전에 `CLAUDE.md`의 "정보 삭제
규칙" 섹션을 먼저 읽어주세요.

## 제작자

**moksa** ([moksaweb.com](https://moksaweb.com)) 개발 및 유지 관리. MIT 라이선스.
