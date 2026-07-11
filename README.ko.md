# elementor-headless

**에디터를 조작하는 대신 JSON을 직접 작성해서 Elementor 페이지를 만듭니다.**

AI 코딩 에이전트에게 Elementor의 저작 표면 전체 — **135개 위젯과 3개 요소에 걸친 37,964개
컨트롤** — 를, 도저히 읽어 들일 수 없는 583,555 토큰짜리 문서가 아니라 질의 가능한 데이터베이스로
제공하는 [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)입니다.

[English](README.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · 한국어

---

## 왜 필요한가

Elementor는 페이지를 post meta 안의 JSON 트리로 저장합니다. 트리를 쓰면 페이지가 생깁니다.
하지만 Elementor는 **작성한 내용을 검증하지 않습니다.** 값을 그대로 저장하고, 이해할 수 있는
것만 렌더링하며, 나머지는 조용히 버립니다.

오류는 나지 않습니다. 철자가 틀린 컨트롤, 객체가 와야 할 자리에 들어간 문자열, Free 사이트에
쓴 Pro 전용 컨트롤. 이 모두가 깔끔하게 저장되고, 내 환경에서는 멀쩡하게 렌더링되며, 정작
중요한 곳에서는 조용히 아무 일도 하지 않습니다.

그래서 Elementor 페이지를 만드는 에이전트에게는 두 가지 선택지밖에 없습니다. 매번 Elementor의
PHP 소스를 읽거나(비싸고, 그마저도 JSON 형태는 알려주지 않습니다), 아니면 추측하거나(조용히
틀립니다). 이 스킬은 세 번째 선택지입니다.

```bash
$ python tools/el.py type slider
control type: slider   [FREE]  (elementor-core)

JSON value shape (what you write into _elementor_data settings):
  {"unit": "px", "size": "", "sizes": []}
```

## 동작 방식

![architecture](assets/diagrams/architecture.svg)

세 단계로 이루어집니다. 추출은 Elementor 버전마다 한 번, **본인의** 사이트를 대상으로 실행합니다.
그 이후는 전부 질의입니다.

## 설치

```bash
git clone https://github.com/Moksa1123/elementor-headless
cd elementor-headless
python tools/install-skill.py claude-code --global     # or: cursor, codex-cli, gemini-cli, ...
python tools/install-skill.py --list
```

8개 플랫폼을 지원합니다. Claude Code, Claude.ai, Cursor, Codex CLI, Gemini CLI, Devin
(구 Windsurf), GitHub Copilot, Continue. 각 플랫폼의 규약은 2026-07-11에 다시 검증했으며,
[8개 중 3개가 6주 만에 바뀌어 있었습니다](references/multiplatform-install-verification.md).
그래서 가정하지 않고 매번 확인합니다.

## 사용법

```bash
python tools/el.py widgets --tier free --grep box   # find a widget
python tools/el.py widget heading --tab style       # its style controls
python tools/el.py container --tab layout           # flex + grid, with conditions
python tools/el.py css border-radius                # reverse lookup by CSS property
python tools/el.py group typography                 # what a group control expands into
python tools/el.py breakpoints                      # the responsive suffixes
python tools/el.py pro --check custom_css align     # exits 1 if any of these needs Pro
```

그다음 만들고, 검사하고, 배포합니다.

```bash
python tools/el.py skeleton > page.json
python tools/validate-page.py page.json --target free
wp eval-file tools/apply-page.php 123 page.json
```

`validate-page.py`는 Elementor가 잡아주지 않는 것들을 잡아냅니다. 존재하지 않는 컨트롤 이름,
잘못된 값 형태, 허용되지 않는 단위, 유효하지 않은 옵션, 중복된 id, 충족되지 않은 조건, 그리고
Free 타깃에 쓰인 Pro 전용 컨트롤입니다.

## 토큰 비용

**Elementor 소스를 읽는 것보다 토큰이 89.1% 적고, 스키마를 통째로 로드하는 것보다 99.1%
적습니다.** 직접 재현해 보십시오. 스크립트가 `data/token-benchmark.csv`를 씁니다.

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| 작업 | 소스 읽기 | 스키마 로드 | **질의** |
|---|---|---|---|
| 히어로 컨테이너 레이아웃 잡기 (flex, boxed, 반응형 padding) | 20,182 | 583,555 | **964** |
| 제목 스타일링 (색상, 타이포그래피, 정렬) | 8,329 | 583,555 | **730** |
| 버튼 스타일링 (색상, padding, radius, hover) | 7,803 | 583,555 | **2,935** |
| 임의의 위젯 여백을 반응형으로 만들기 | 11,800 | 583,555 | **243** |
| 어떤 컨트롤이 특정 CSS 속성을 제어하는지 찾기 | — | 583,555 | **363** |
| **합계** | **48,114** | **583,555** | **5,235** |

두 가지가 이를 가능하게 합니다. 데이터를 **로드하지 않고 질의만 한다는 점**, 그리고 모든 위젯이
공유하는 211개의 Advanced 탭 컨트롤을 **135번이 아니라 한 번만 저장한다는 점**입니다. 이 컨트롤들이
전체 행의 75.6%를 차지하므로, 밖으로 빼내는 것만으로 스키마가 73.2% 줄어듭니다.

측정에는 tiktoken `cl100k_base`를 사용했습니다. Claude가 아니라 OpenAI의 토크나이저이므로 절대
수치는 대략 ±10% 정도 달라집니다. 다만 같은 토크나이저 아래에서 두 텍스트 사이의 비율은
안정적이며, 이 문서가 주장하는 것은 그 비율입니다. 방법론과 주의사항은
[token-efficiency.md](references/token-efficiency.md)를 참고하십시오.

## Free와 Pro의 구분은 추측이 아니라 측정한 것입니다

Elementor Pro는 **무료 위젯 안으로 컨트롤을 주입합니다.** Pro가 설치된 사이트에서 무료 Heading
위젯을 열어보면 Advanced 탭에 Motion Effects, Sticky, Custom CSS, Display Conditions,
Custom Attributes가 들어 있습니다. 위젯의 등급을 그대로 물려받게 하면 이들 전부가 "free"로
표시되고, 그렇게 만든 페이지는 내 환경에서는 완벽하게 렌더링되다가 Free 설치 환경에서는 스타일이
사라집니다.

그래서 등급을 측정합니다. 두 번 추출합니다. 한 번은 Pro를 로드한 상태로, 한 번은
`wp --skip-plugins=elementor-pro`로 (이 옵션은 해당 CLI 프로세스 하나에만 영향을 주며 어떤
플러그인도 비활성화되지 않으므로 프로덕션에서도 안전합니다) 실행한 뒤, 둘을 diff합니다.

| | Free 4.1.4 | + Pro 4.1.2 |
|---|---|---|
| 위젯 | 64 | **135** |
| 모든 위젯이 갖는 컨트롤 | 165 | **211** (+46) |
| `container`의 컨트롤 | 277 | **356** (+79) |
| 컨트롤 타입 | 52 | **59** |
| 그룹 컨트롤 | 11 | **16** |

Pro가 **모든** 위젯에 주입하는 46개는 다음과 같습니다. 모든 `motion_fx_*` (37개), `sticky*`
(6개), `custom_css`, `_attributes`, `e_display_conditions`.

등급을 추론하려 하지 마십시오. **Border와 Box Shadow는 고급스러워 보이지만 무료입니다.
`_attributes`는 기본적으로 보이지만 Pro입니다.** 이 저장소도 측정 대신 추론에 의존한 탓에
Border를 Pro로 잘못 표시한 채 배포한 적이 한 번 있습니다.

## 정확한가? 직접 증명하게 하십시오.

이 스키마는 Elementor 4.1.4 / Pro 4.1.2에서 나왔습니다. 당신의 환경은 다를 수 있습니다.
믿지 말고 검사하십시오. 검증기는 세 개이고, 서로 다른 세 가지 질문에 답합니다.

**1. 스키마가 내 설치 환경과 일치하는가?**

```bash
wp eval-file tools/extract-elementor-schema.php core+pro > mine.json
wp --skip-plugins=elementor-pro eval-file tools/extract-elementor-schema.php core+pro > mine-free.json
python tools/verify-schema.py mine.json --free-dump mine-free.json
```

```
checked 37,964 (owner, control) pairs from the shipped schema
Free/Pro claims checked on free widgets/elements: 15,969
FAILURES: 0
PASS
```

차이가 발견되면 0이 아닌 코드로 종료하므로 배포 게이트로 쓸 수 있습니다.

**2. 스키마로 만든 페이지가 스키마가 약속한 CSS를 실제로 렌더링하는가?**

스키마는 각 컨트롤이 어떤 CSS 속성을 제어하는지 알려줍니다. 이 검증기는 실제로 페이지를 만들고,
Elementor가 컴파일한 스타일시트를 다시 읽어 들여 전부 대조합니다. 각 반응형 키가 *해당
브레이크포인트의* 미디어 쿼리 안에 들어갔는지까지 확인합니다.

```bash
python tools/verify-render.py examples/demo-page.json rendered.css --post-id 9176
```

```
CSS property assertions: 94/94 passed
PASS
```

**3. 스키마에 있는 모든 컨트롤이 정말로 동작하는가?**

`verify-render.py`는 해당 페이지가 마침 사용하는 컨트롤만 다룹니다. 데모 페이지에서는 94개입니다.
`sweep-controls.py`는 나머지를 다룹니다. CSS를 제어한다고 되어 있는 모든 컨트롤에 대해 유효한
값을 합성하고, 그 값이 실제로 반영되도록 필요한 의존성 사슬을 풀고, 렌더링한 뒤, 그 값이 나왔는지
단언합니다. 각 컨트롤에는 **그 컨트롤에만 고유한** 값(서로 다른 hex 색상, 서로 다른 픽셀 크기)을
부여하므로, 통과했다는 것은 *그 컨트롤이* *그 값을* 만들어냈다는 뜻입니다. 다른 무언가가 비슷한
속성을 썼다는 뜻이 아닙니다.

```bash
python tools/sweep-controls.py plan --out sweep/ --post-id <draft post>
# apply each batch, capture post-<id>.css
python tools/sweep-controls.py check sweep/ --out data/control-verification.csv
```

```
controls asserted     16,778
  verified by value   15,508  (92.4%)   the exact value we wrote is in the CSS
  property only        1,270  ( 7.6%)   right property, value not literally assertable
  FAILED                   0  ( 0.0%)
```

컨트롤별 결과는 `data/control-verification.csv`로 함께 제공됩니다.

**4. 직접 보십시오.** `examples/demo-page.json`은 오직 이 스킬만으로 만들어 실제로 발행한
페이지입니다. Elementor 에디터는 한 번도 연 적이 없습니다.

**https://moksaweb.com/elementor-headless-demo/**

## 페이지와 사이트 사이에서 블록 재사용하기

Elementor 자체의 JSON 교환 형식입니다. 에디터의 Export / Import Template 버튼 뒤에 있는 바로
그 파일입니다.

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json
wp --user=1 eval-file tools/import-template.php hero-block.json <target_post_id>
```

**`_elementor_data`를 복사해서 사이트 사이로 블록을 옮기지 마십시오.** 미디어 컨트롤은 첨부파일
id를 저장하는데, 그 id는 다른 사이트에서 *전혀 다른 이미지*를 가리키거나 아무것도 가리키지
않습니다. Elementor의 `on_export`는 id를 url로 바꾸고, `on_import`는 그것을 대상 사이트의 미디어
라이브러리로 다시 내려받습니다. 원본 meta를 그대로 복사하면 이미지가 조용히 깨지거나, 조용히 엉뚱한
이미지로 바뀝니다. 이 도구들은 그 훅을 타도록 Elementor 자체의 import 경로를 호출합니다. 왕복
측정 결과는 다음과 같습니다. 작성한 설정 82개, 손실 0개, 변경 0개.

## 무엇이 들어 있나

```
data/
  elementor-schema.json    2.7 MB   전체 표면 - 질의할 뿐, 절대 로드하지 않음
  controls.csv             2.0 MB   위젯/요소 고유 컨트롤 전부
  common-controls.csv       39 KB   모든 위젯이 공유하는 211개
  pro-only-controls.csv     33 KB   안전장치 테이블
  pro-only-widgets.csv     3.0 KB
  control-types.csv        4.6 KB   59가지 JSON 값 형태 전부
  group-controls.csv       3.7 KB   16개 그룹과 그것이 펼쳐지는 평탄한 키들
  widgets.csv              8.2 KB   위젯 135개 + 요소 3개
  breakpoints.csv          0.2 KB
  control-verification.csv          컨트롤별: 실제로 렌더링되는가?
  token-benchmark.csv               재현 가능한 측정값

tools/
  el.py                          스키마 질의 - 정문
  validate-page.py               페이지 트리 사전 점검
  apply-page.php                 쓰기: meta + CSS 재빌드 + 백업
  extract-elementor-schema.php   실제 설치 환경 덤프
  build-indexes.py               덤프 -> 배포용 데이터 파일
  verify-schema.py               스키마가 내 설치 환경과 일치하는가?
  verify-render.py               Elementor가 스키마의 약속대로 출력하는가?
  sweep-controls.py              모든 컨트롤을 렌더링해서 동작을 단언
  export-template.php            Elementor 자체 JSON 형식으로 내보내기
  import-template.php            미디어까지 포함해 Elementor 자체 경로로 가져오기
  benchmark-tokens.py            토큰 수치 재현
  install-skill.py               8개 플랫폼 설치기

references/   data-model · control-types · containers-and-layout · responsive
              templates-and-conditions · import-export · extraction-traps
              token-efficiency
examples/     demo-page.json - 위에 있는 발행된 페이지
```

## 네 가지 함정

이 데이터를 순진하게 추출하면 서로 다른 네 가지 방식으로 틀리며, 각각 완전해 보이지만 거짓말을
하는 스키마를 만들어냅니다. 넷 다 잡아내기 전에 이 저장소에서 실제로 배포된 적이 있습니다.
정리한 글은 [extraction-traps.md](references/extraction-traps.md)에 있습니다.

1. **WP-CLI는 Elementor에게 프런트엔드처럼 보입니다.** 그래서 Elementor는 축약된 컨트롤 스택을
   돌려줍니다. **컨트롤의 46%와 탭/라벨 메타데이터의 약 100%가 사라지는데**, 오류는 나지
   않습니다. 추출기는 그 경로를 비활성화하고, 품질이 저하된 데이터를 내보내느니 차라리 중단하도록
   카나리아 두 개를 둡니다.
2. **반응형은 두 가지 메커니즘입니다.** 그리고 뻔한 방식으로 테스트하면 하나만 발견됩니다.
   `padding_tablet`이라는 컨트롤 객체는 *어디에도* 존재하지 않습니다 — 그런데 `padding_tablet`은
   동작합니다. 접미사가 붙은 형제 컨트롤을 찾는 방식으로 반응형을 감지하면 padding, margin,
   width, 폰트 크기, gap을 놓칩니다. (수정 후 컨트롤의 9.8% → 30.1%.)
3. **컨트롤의 등급은 그 위젯의 등급이 아닙니다.** Pro가 무료 위젯 안으로 주입하기 때문입니다.
   상속한 것이 아니라 측정한 것입니다.
4. **컨트롤은 서로 다른 세 가지 방식으로 게이트될 수 있고**, `condition`은 그중 하나에
   불과합니다. 152개 컨트롤은 자체 연산자를 가진 고급 불리언 형식*으로만* 게이트됩니다. 그리고
   499개 컨트롤은 *다른* 컨트롤의 값을 자신의 CSS에 보간합니다. 그 다른 값이 비어 있으면
   Elementor는 선언 전체를 버립니다. 문서화된 조건은 전부 충족되어 있고 오류도 나지 않습니다.
   그라디언트 색상 없이 그라디언트 각도만 설정하면 아무것도 나오지 않습니다. 조용히 말입니다.
   이 함정은 16,778개 컨트롤을 전부 렌더링해서 들여다본 끝에야 드러났습니다.

## 기여하기

더 새로운 Elementor 버전에 대해 다시 추출한 뒤, 재생성된 `data/`와 함께 PR을 열어주십시오.
`verify-schema.py`가 무엇이 바뀌었는지 정확히 알려줍니다.
[CONTRIBUTING.md](CONTRIBUTING.md)를 참고하십시오.

## 라이선스

MIT. **moksa**가 만들고 유지 관리합니다 · [moksaweb.com](https://moksaweb.com)

자매 스킬: [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
