# elementor-headless

**에디터를 조작하는 대신 JSON을 직접 작성해서 Elementor 페이지를 만듭니다.**

AI 코딩 에이전트에게 Elementor의 저작 표면 전체를 질의 가능한 데이터베이스로
제공하는 [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)입니다
— 그리고 그 안의 모든 주장을 라이브 사이트에서 렌더링하고, 클릭하고, 측정해서
증명합니다. 무언가를 잘못 써도 Elementor는 절대 오류를 내지 않기 때문입니다.

```
192 widgets · 13 elements · 49,857 control pairs
the Kit's 773 Site Settings · 48 page settings · 29 document types
51 dynamic tags · 39 display conditions · every repeater's item fields
```

[English](README.md) · [繁體中文](README.zh-TW.md) · [日本語](README.ja.md) · 한국어

---

## 문제

Elementor는 페이지를 post meta 안의 JSON 트리로 저장합니다. 트리를 쓰면 페이지가
생깁니다. 하지만 Elementor는 **작성한 내용을 검증하지 않습니다** — 값을 그대로
저장하고, 이해하는 것만 렌더링하며, 나머지는 조용히 버립니다.

오류는 없습니다. 철자가 틀린 컨트롤 이름, 객체가 와야 할 자리에 들어간 문자열,
Free 사이트에 쓴 Pro 전용 컨트롤, `"hidden-tablet"`이었어야 할
`hide_tablet: "yes"` — 전부 깔끔하게 저장되고, 조용히 아무 일도 하지 않습니다.
90% 맞은 페이지는 누군가 padding이 전혀 적용되지 않았다는 것을 알아채기 전까지
100% 맞은 페이지와 똑같아 보입니다.

따라서 Elementor 페이지를 만드는 에이전트에게는 두 가지 선택지가 있었습니다.
매번 Elementor의 PHP 소스를 읽는 것(비싸고, 그래도 JSON shape는 알려주지
않습니다)과 추측하는 것(조용히 틀립니다)입니다. 이 스킬이 세 번째 선택지입니다:

```bash
$ python tools/el.py type slider
control type: slider   [FREE]  (elementor-core)

JSON value shape (what you write into _elementor_data settings):
  {"unit": "px", "size": "", "sizes": []}
```

## 동작 방식

![architecture](assets/diagrams/architecture.svg)

세 단계입니다. **Extraction**은 Elementor 버전마다 한 번, 라이브 install을
대상으로 실행되며, 품질이 저하된 데이터는 내보내기를 거부하는 canary 3개가 지킵니다.
**Verification**은 모든 컨트롤·위젯·인터랙션을 라이브 사이트에서 렌더링하고,
실제로 일어난 일을 데이터에 다시 반영합니다. **Query**는 빌드 시점에 에이전트가
하는 일의 전부입니다.

## 설치

```bash
git clone https://github.com/Moksa1123/elementor-headless
cd elementor-headless
python tools/install-skill.py claude-code --global     # or: cursor, codex-cli, gemini-cli, ...
python tools/install-skill.py --list
```

8개 플랫폼: Claude Code, Claude.ai, Cursor, Codex CLI, Gemini CLI, Devin
(구 Windsurf), GitHub Copilot, Continue. 각 플랫폼의 규약은 2026-07-11에
재검증했습니다 — [8개 중 3개가 6주 사이에 바뀌어
있었으므로](references/multiplatform-install-verification.md), 규약은 가정하지
않고 확인합니다. 업그레이드는 이전 버전이 남긴 것을 정리합니다. 작년의 틀린
데이터셋을 올해의 맞는 데이터셋 옆에 남겨 두는 installer는 installer가 없느니만
못합니다.

## 사용법

조회는 이렇게 합니다 — 질의 한 번에 약 700토큰이 들고, 그 한 번으로 완전한
답이 나옵니다:

```bash
python tools/el.py widgets --tier free --grep box    # find a widget
python tools/el.py widget heading --tab style        # its style controls, with every gate
python tools/el.py container --tab layout            # flex + grid, conditions included
python tools/el.py css border-radius                 # reverse lookup by CSS property
python tools/el.py type dimensions                   # the JSON value shape
python tools/el.py group typography                  # what a group control expands into
python tools/el.py tags --group post                 # dynamic tags (__dynamic__)
python tools/el.py page-settings                     # hide_title, CANVAS, page background
python tools/el.py kit --section section_global_colors   # Site Settings / global colors
python tools/el.py doctypes                          # legal _elementor_template_type values
python tools/el.py widgets --requires woocommerce    # what needs what to exist
python tools/el.py pro --check custom_css align      # exits 1 if any of these needs Pro
```

그다음 만들고, 검사하고, 배포합니다:

```bash
python tools/el.py skeleton > page.json
python tools/validate-page.py page.json --target free --have woocommerce
wp eval-file tools/apply-page.php 123 page.json page-settings.json
python tools/verify-live.py page.json https://your-site/your-page/
```

- `validate-page.py`는 Elementor가 잡아 주지 않는 것을 잡습니다: 알 수 없는
  컨트롤, 잘못된 value shape, 허용되지 않는 단위, 유효하지 않은 옵션, 중복 id,
  세 종류의 미충족 의존성 전부(조건을 **기본값** 기준으로 평가하므로,
  `custom_messages` 없이 `success_message`를 설정하면 조용히 기본값으로
  대체되는 대신 경고가 납니다), multi-select 값, class 컨트롤에 들어간 숫자
  `0`, Free 대상 사이트의 Pro 전용 컨트롤, 그리고 **대상 사이트에 아예 존재할
  수 없는
  위젯**까지.
- `apply-page.php`는 meta key 4개와 선택적 페이지 설정(Canvas에 실제로 필요한
  `template` → `_wp_page_template` 분리 포함)을 쓰고, 컴파일된 CSS를 다시
  만들며, **렌더링된 HTML 캐시를 삭제합니다** — 이 마지막 단계를 건너뛰면
  올바른 트리가 이전 페이지를 영원히 서빙하고, 오류는 나지 않습니다.
- `verify-live.py`는 공개 URL을 캐시/CDN을 거쳐 가져와서, 트리와 CSS 값과
  wrapper class를 실제로 응답으로 내려온 내용과 대조합니다.

## 모든 위젯이 모든 install에 존재하는 것은 아니다

**위젯 표면은 Elementor의 속성이 아니라 사이트(SITE)의 속성입니다.** 같은
Elementor 4.1.4 / Pro 4.1.2가 어떤 머신에서는 148개 위젯을 등록하고 다른
머신에서는 192개를 등록하는데, 어느 쪽도 고장 난 것이 아닙니다 — 추가된
위젯들은 첫 번째 머신에 없는 무언가를 필요로 할 뿐입니다. 이것이 빠진 스키마는
불완전한 것이 아니라 **틀린** 것입니다. 그런 스키마에
`woocommerce-product-price`를 물어보면, Elementor에 그런 위젯은 없다고 아주
자신 있게 답합니다.

그래서 모든 위젯에는 필요한 것이 함께 기록됩니다. Elementor 소스에서 해당 모듈
자신의 `is_active()` 게이트를 읽어낸 값입니다 — 그리고 권위 있는 것은 그
게이트이지 모듈 자신의 `EXPERIMENT_NAME` 상수가 아닙니다. 그 상수는 이 교훈을
배우기 전까지, 등록되어 렌더링까지 되는 위젯 21개에 잘못된 라벨을 붙여
놓았습니다:

| 필요한 것 | 위젯 수 |
|---|---|
| 없음 — 항상 존재 | 104 |
| `plugin:woocommerce` | 29 |
| 일부 플러그인이 등록하는 WP legacy 위젯 | 33 |
| `experiment:container` / `nested-elements` / `e_atomic_elements` / … | 26 |

`validate-page.py`는 대상 사이트가 가질 수 없는 위젯에 오류를 냅니다. 사이트가
무엇을 갖고 있는지는 `--have woocommerce nested-elements`로 알려 주십시오.

**Elementor V4 atomic elements(`e-heading`, `e-flexbox`, `e-form-*`, 총 18개)는
다른 데이터 모델입니다** — `settings` + 컨트롤이 아니라 type-tagged props와
별도의 `styles` 배열입니다. 이 스킬은 그 prop 스키마는 보고하지만
(`el.py widget e-heading`), 빌드를 검증할 수 있는 척은 하지 않습니다.

## 토큰 비용, 그리고 시간

**Elementor 소스를 읽는 것보다 토큰 86.8% 절감. 스키마를 통째로 로드하는
것보다 99.4% 절감. 모델 ingest 기준 약 5배, 스키마 로드 대비 약 118배
빠릅니다.** 도구 지연 시간은 측정값입니다(질의당 중앙값 316 ms). ingest 시간은
공개된 기준율 1,000 tok/s에서 토큰 수로 도출한 값입니다 — 기준율을 바꿔도
비율은 움직이지 않습니다. 직접 재현해 보십시오. 스크립트가
`data/token-benchmark.csv`를 씁니다:

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| 작업 | 소스 읽기 | 스키마 로드 | **질의** |
|---|---|---|---|
| hero container 배치(flex, boxed, 반응형 padding) | 20,182 | 1,082,477 | **1,209** |
| heading 스타일링(색, typography, 정렬) | 8,329 | 1,082,477 | **836** |
| button 스타일링(색, padding, radius, hover) | 7,803 | 1,082,477 | **3,664** |
| 아무 위젯이나 spacing을 반응형으로 만들기 | 11,800 | 1,082,477 | **264** |
| 어떤 컨트롤이 특정 CSS property를 만드는지 찾기 | — | 1,082,477 | **363** |
| **합계** | **48,114** | **1,082,477** | **6,336** |

절감률은 원래 89.1%였습니다. **내려갔습니다** — 표면이 정직해지면서
(WooCommerce, Kit, selector, repeater 필드) 스키마가 583k에서 1.08M 토큰으로
커졌고, 더 풍부한 답에는 더 많은 토큰이 듭니다. 좋아지기만 하는 숫자는
큐레이션된 숫자입니다. 이 숫자들은 어느 방향으로 움직이든 스크립트가 다시
생성합니다.

이것이 성립하는 이유는 두 가지입니다. 데이터는 **로드되지 않고 질의만 되며**,
모든 classic 위젯이 공유하는 Advanced 탭 컨트롤 211개는 168번이 아니라 **한
번만 저장됩니다**. 토큰 수는 tiktoken `cl100k_base`로 셌습니다 — Claude가
아니라 OpenAI의 tokenizer이므로 절대값은 대략 ±10% 흔들리지만, 같은 tokenizer
아래의 비율은 안정적이고, 주장하는 것은 그 비율입니다
([token-efficiency.md](references/token-efficiency.md)).

## Free vs Pro는 추측이 아니라 측정이다

Elementor Pro는 **free 위젯에 컨트롤을 주입합니다**: Pro 사이트의 free Heading
위젯에는 Motion Effects, Sticky, Custom CSS, Display Conditions, Custom
Attributes가 붙어 있습니다. 위젯의 tier를 그대로 물려받으면 이 46개가 전부
"free"로 라벨링됩니다 — 그렇게 만든 페이지는 내 환경에서는 완벽하게 렌더링된
뒤, Free install에서 스타일을 잃습니다.

그래서 tier는 측정합니다. Pro를 로드한 상태로 한 번,
`wp --skip-plugins=elementor-pro`로 한 번(그 CLI 프로세스 하나에만 영향을
주므로 production에서도 안전합니다) 추출해서 diff합니다. 같은 방법을 한 축 더
확장한 것이 WooCommerce입니다. WooCommerce는 위젯 29개만 추가하는 것이 아니라 Pro
자신의 loop 위젯에 `product_query_exclude*`를 주입하는데, 그 컨트롤들이 누구
것인지는 WooCommerce를 끈 dump만이 밝혀 줍니다. 서드파티 오염도 같은 방식으로
배제합니다: Rank Math는 `accordion`에, Unlimited Elements는 container에
주입하며, 이들을 로드한 채 추출한 스키마는 그 컨트롤들을 Elementor의 것인 양
담은 채 배포됩니다.

tier를 추론하지 마십시오. **Border와 Box Shadow는 premium처럼 보이지만
free입니다. `_attributes`는 basic처럼 보이지만 Pro입니다.** 이 repo는 측정 대신
추론했다가 Border를 Pro로 잘못 라벨링해서 배포한 적이 있습니다. 그리고
Elementor core는 Pro가 꺼져 있을 때 **진짜 Pro 위젯과 정확히 같은 이름의 promo
stub**을 등록합니다 — Pro 없는 dump를 액면 그대로 받아들이면 Pro 위젯 26개가
free로 읽힙니다.

## 정확한가? 직접 증명하게 하라

믿지 말고 시험하십시오. 여덟 개의 검사가 서로 다른 여덟 개의 질문에 대한 답을,
서로 다른 산출물에서 읽어냅니다: 컨트롤 스택, 컴파일된 stylesheet, 전달된 HTML, 실제
브라우저의 computed style, 실제 pointer 이벤트, 그리고 CDN을 거친 공개 URL.
**verifier는 자기가 읽는 채널의 버그만 찾습니다** — 이 검사 하나하나가, 더
순진한 검사가 실제 문제를 놓쳤기 때문에 존재합니다.

**1. 스키마가 내 install과 일치하는가?**

```bash
python tools/verify-schema.py mine.json --free-dump mine-free.json
```

모든 (owner, control) 쌍을 순회하며 type과 Free/Pro 주장을 검사하고 — 스키마가
각 위젯의 요구 사항을 명시하므로 — "스키마가 틀렸다"와 "이 install에
WooCommerce가 없다"를 구분해서, 어느 쪽에 대해서도 헛소동을 벌이지 않습니다.
두 추출 사이트 모두에서 PASS하며, drift가 있으면 non-zero로 종료하므로 deploy를
게이트할 수 있습니다.

**2. CSS를 만드는 모든 컨트롤이 실제로 그 CSS를 내보내는가?**

모든 컨트롤에 **자기만의 고유한 값**(서로 다른 hex 색, 서로 다른 픽셀 크기)을
주고, 의존성 체인은 자동으로 풀며, 그 출력을 서버 디스크의 파일이 아니라
**공개 URL이 전달한** stylesheet 안에서 assert합니다:

```
25,259 CSS-driving controls    99.4% covered, 0 failures
33,448 responsive suffixes     each asserted inside ITS media query, with a value
                               distinct from desktop's, so a leak cannot pass
```

Elementor 자신의 메타데이터가 틀린 곳에서는 렌더링된 결과가 이깁니다: 컨트롤
9개가 실제로는 내보내지 않는 responsive breakpoint를 지원한다고 표시하고
있고, 스키마는 이제 해당 컨트롤에 `rwd-BROKEN`이라고 기록합니다.

**3. class를 내보내는 모든 컨트롤이 wrapper에 그 class를 붙이는가?**

3,308개 컨트롤은 CSS를 내보내는 대신 wrapper class를 덧붙이는 방식으로
동작합니다 — stylesheet 검사는 이들을 구조적으로 감지할 수 없습니다. 그래서
전달된 HTML에서 읽어냅니다: 99.8%를 스윕했고 실패는 0건이며, `classes_dictionary`의
legacy remap(`position: "top"`이 `elementor-position-block-start`로 렌더링됨)과
장치별 prefix(`_tablet` suffix가 아니라 `elementor-tablet-position-`)까지 포함합니다.

**4. 실제 브라우저가 선언된 것을 COMPUTE하는가?**

규칙은 파일 안에 있으면서도 질 수 있습니다 — specificity에, cascade에,
아무것도 매치하지 않는 selector에. `sweep-browser.py`는 모든 페이지를
Chromium으로 열고 Elementor의 선언을 **그 규칙이 실제로 겨냥하는 노드에서**
`getComputedStyle`과 비교합니다(`data/css-selectors.csv`가 존재하는 이유가
바로 이것입니다):

```
48,873 probes across two live sites with different themes
25 of 26 override patterns IDENTICAL on both -> facts about Elementor,
   led by: _element_width's max-width is dead on every widget inside a
   container, killed by Elementor's own frontend.css at specificity (0,4,0)
 1 of 26 site-specific -> a fact about that theme, named by the data
```

**5. 모든 위젯이, 콘텐츠를 주면, 실제로 렌더링하는가?**

모든 콘텐츠 컨트롤에 고유 marker를 심고(repeater 항목은 추출된 필드로 구성),
JS 오류나 zero-size 렌더가 정확히 하나의 위젯에 귀속되도록 **페이지당 위젯
하나**, 각각 element screenshot, viewport 3종:

```
168/168 placeable widgets across the two sites
  126 rendered — marker echo, real site content, or hidden-by-design
   42 correctly empty without site context (cart/checkout/loop on a bare page)
    0 broken
```

**6. 인터랙티브 위젯은 실제로 인터랙트하는가?**

공개 페이지 위에서의 실제 pointer 이벤트:

```
nested-tabs        click tab 2  -> content 2 shows, content 1 hides    PASS
nested-accordion   click item 2 -> <details> opens                     PASS
accordion          click item 2 -> body becomes visible                PASS
toggle             click item 1 -> body toggles open                   PASS
image-carousel     click next   -> active slide advances               PASS
```

그리고 어떤 정적 읽기로도 검증할 수 없는 `:hover` 규칙은 실제 pointer로
구동합니다: probe 3,882건, 값으로 검증된 것 297건. override 113건은 전부
same-element seed 충돌(hover 컨트롤 두 개가 같은 property에 일부러 다른 값을
쓰는 경우 — 하나는 져야 합니다)이며, 행 단위로 분류되어 있습니다. transition은
먼저 비활성화하고 그 개입을 공개합니다: 79초짜리 seeded transition의 200 ms
시점에 읽은 색은 애니메이션 중간 프레임이지 판정이 아닙니다.

**7. workflow는 끝까지 성립하는가?**

아래 각각을 headless로 만든 뒤, 라이브 사이트에서 브라우저로 검증했습니다:

- **Global colors**: kit의 `custom_colors`에 색을 추가하고 `__globals__`로
  참조하면 정확히 그 색으로 compute됩니다
- **Dynamic tags**: `post-title` 바인딩이 포스트의 실제 제목을 전달합니다
- **Display conditions**: `logged_in` 조건이 걸린 element는 익명 HTML에
  존재하지 않습니다 — CSS로 숨겨진 것이 아니라 서버 측에서 제거된 것입니다
- **Theme Builder**: 한 페이지로 scope된 header가 거기서만 렌더링되고 다른
  어디에서도 렌더링되지 않습니다
- **Popups**: `page_load` 트리거 popup이 익명 브라우저에서 열립니다
- **Loop Builder**: loop-item template + loop-grid가 실제 포스트 3개를
  렌더링합니다
- **Forms**: 익명 입력 → nonce → 데이터베이스 row → custom success message
- **Canvas**: `template: elementor_canvas`가 테마 chrome을 제거합니다(page
  settings만으로는 닿지 않는 `_wp_page_template`을 통해서)
- **Templates**: Elementor 자체 JSON 포맷으로 export/import하며, 미디어는
  Elementor 자체 hook이 rehost합니다

**8. 일반 방문자가 받는 페이지에 이 전부가 들어 있는가?**

```bash
python tools/verify-live.py examples/demo-page.json https://moksaweb.com/elementor-headless-demo/
```

공개 URL과 **그 페이지가 링크하는 모든 stylesheet**(페이지의 스타일은 여러
파일에 나뉘어 있습니다 — Kit의 globals는 별도 파일에 들어 있습니다)를 edge cache를
거쳐 가져와서, 트리 + CSS 값 + wrapper class를 assert합니다. 변조된 트리에서는
실패합니다 — 한 번도 빨간불이 들어온 적 없는 verifier는 verifier가
아닙니다.

demo 페이지는 실제로 존재하고, 게시되어 있으며, 에디터에서 열린 적이 한 번도
없습니다: **https://moksaweb.com/elementor-headless-demo/**

## 함정들

이 일을 순진하게 하면 **번호가 붙은 열한 가지 방식으로** 틀립니다 — 하나하나가
잡히기 전에 이 repo에서 실제로 배포됐고, 지금은 각각 canary, validator 규칙,
또는 data 필드가 되어 있습니다. 전체 write-up은
[extraction-traps.md](references/extraction-traps.md)에 있습니다:

1. WP-CLI는 잘려 나간 컨트롤 스택을 받습니다 — 컨트롤의 46%가 소리 없이
   사라집니다
2. responsive는 두 가지 메커니즘입니다. `padding_tablet`은 컨트롤 객체가
   없는데도 동작합니다
3. 컨트롤의 tier는 그 위젯의 tier가 아닙니다 — Pro는 free 위젯에 주입합니다
4. 컨트롤은 세 가지 방식으로 게이트됩니다. 컨트롤 661개는 빈 interpolated 값에서
   죽습니다
5. responsive 의존성은 breakpoint에서 다시 검사됩니다
6. `is_responsive`는 과잉 약속합니다 — 렌더링만이 압니다
7. CSS는 컨트롤이 할 수 있는 일의 절반일 뿐입니다 — 3,308개는 대신 class를
   내보냅니다
8. class 값은 remap되고, 그 장치 prefix는 다른 문자열입니다
9. `_elementor_data`를 쓰면 오래된 렌더링 HTML 캐시가 남습니다 — 올바른 트리가
   이전 페이지를 서빙하고, 17k 컨트롤 스윕이 그 위에서 green으로 돌았습니다
10. 위젯 표면은 Elementor가 아니라 install의 속성입니다
11. 규칙은 stylesheet 안에 있으면서도 질 수 있습니다 — 브라우저만이 그것을
    봅니다

여기에, 각자 해당하는 자리에 문서화된 것들이 더 있습니다: Canvas의 `template`
설정은 page settings가 아니라 `_wp_page_template`에 저장됩니다. library
template에는 `elementor_library_type` **taxonomy**와 conditions **cache**가
필요하며, 없으면 Theme Builder는 그것을 영영 보지 못합니다. `theme-*` 위젯은
삽입 시점에 에디터에게서 dynamic 바인딩을 받으므로, headless 트리는
`__dynamic__`을 직접 써야 합니다. WP legacy bridge는 모든 것을 `settings.wp`
아래로 받습니다. `e_display_conditions`는 JSON **문자열**을 감싼 배열이며, 예전
문서가 보여 주던 bare 배열은 멀쩡히 저장되고 조용히 무시됩니다.

## 무엇이 들어 있나

```
data/
  elementor-schema.json      the full surface - queried, never loaded
  controls.csv               every (owner, control) pair, greppable
  common-controls.csv        the 211 shared by every classic widget
  pro-only-controls.csv      the safety table       pro-only-widgets.csv
  control-types.csv          all value shapes       group-controls.csv
  widgets.csv                incl. per-widget requirements
  dynamic-tags.csv           the __dynamic__ surface, 51 tags
  css-selectors.csv          which node each control's CSS actually lands on
  control-verification.csv   per-control: does it emit the CSS it claims?
  class-verification.csv     per-control: does it emit the CLASS it claims?
  browser-verification*.csv  per-control: does Chromium COMPUTE it? (2 sites)
  widget-verification.csv    per-widget: does it render its content? (168)
  hover-verification.csv     per :hover rule, driven by a real pointer
  token-benchmark.csv        reproducible token AND latency measurements

tools/
  el.py                      query the schema - the front door
  validate-page.py           pre-flight a tree, incl. what the target site can have
  apply-page.php             meta + page settings + CSS rebuild + HTML-cache purge
  extract-elementor-schema.php   dump a live install (3 canaries)
  build-indexes.py           dumps + sweep results -> shipped data
  verify-schema.py           does the schema match your install?
  verify-render.py           does Elementor emit what was promised?
  verify-live.py             does the PUBLIC page have it, through the CDN?
  verify-browser.py          does Chromium COMPUTE it, on the right node?
  verify-interactions.py     do tabs switch, accordions open, carousels advance?
  sweep-controls.py          every CSS control, delivered stylesheet
  sweep-classes.py           every CLASS control, delivered HTML
  sweep-browser.py           declared vs computed, every control, in Chromium
  sweep-widgets.py           every widget functionally, one per page, screenshots
  sweep-hover.py             every :hover rule, real pointer
  sweep-frontend.sh          capture what the public URL actually serves, per batch
  export-template.php        Elementor's own JSON format out
  import-template.php        and back in, media handled by Elementor's own hooks
  benchmark-tokens.py        reproduce the token and time numbers
  install-skill.py           8-platform installer, prunes stale files

references/   data-model · control-types · containers-and-layout · responsive
              templates-and-conditions · import-export · extraction-traps
              token-efficiency · multiplatform-install-verification
examples/     demo-page.json - the published proof page
```

## 정직한 한계

- **Elementor V4 atomic elements**: 질의 전용입니다. 이들을 빌드하는 것은 이
  스킬이 아직 쓰지 못하는 다른 데이터 모델입니다.
- **컨텍스트 의존 위젯**(cart, checkout, post comments, product 관련 요소)은 빈
  페이지에서 "correctly empty"로 검증됩니다. 완전한 동작에는 어떤 스윕도
  지어낼 수 없는 store 또는 post 컨텍스트가 필요합니다.
- **버전에 묶여 있음**: 여기 있는 모든 숫자는 Elementor 4.1.4 / Pro 4.1.2에서
  측정됐습니다. 새 버전은 그중 무엇이든 무효화할 수 있습니다 — 그래서 모든
  verifier가 함께 배포되고, *사용 중인* install에 대해 다시 실행됩니다.
- `page_load` 이외의 popup 트리거, `save-to-database` 이외의 form action,
  그리고 서드파티 addon 위젯은 추출은 되지만 E2E 검증은 되지 않았습니다.

## 내 install에 맞게 재생성

```bash
# three dumps, ONE axis changing at a time - see CLAUDE.md for why this matters
wp --skip-plugins="<all but elementor,elementor-pro,woocommerce>" eval-file tools/extract-elementor-schema.php core+pro > iso-woo.json
wp --skip-plugins="<all but elementor,woocommerce>"               eval-file tools/extract-elementor-schema.php core+pro > iso-free-woo.json
wp --skip-plugins="<all but elementor,elementor-pro>"             eval-file tools/extract-elementor-schema.php core+pro > iso-pro.json

python tools/build-indexes.py iso-woo.json --free-dump iso-free-woo.json \
    --gated-dump woocommerce=iso-pro.json \
    --verification data/control-verification.csv \
    --class-verification data/class-verification.csv --out data/
python tools/verify-schema.py iso-woo.json --free-dump iso-free-woo.json   # must exit 0
```

## 페이지와 사이트를 넘나드는 블록 재사용

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json
wp --user=1 eval-file tools/import-template.php hero-block.json
```

블록을 사이트 간에 `_elementor_data` 복사로 옮기지 마십시오: 미디어 컨트롤은
attachment **id**를 저장하고, 그 id는 다른 사이트에서는 다른 이미지를
뜻합니다. 이 도구들은 Elementor 자체 import 경로를 거치므로 `on_import` hook이
미디어를 다시 내려받습니다. 그리고 `[elementor-template id="123"]`은 저장된
어떤 template이든 어떤 WordPress 콘텐츠에나 embed합니다 — free shortcode
위젯을 통해 Pro 없이 블록을 페이지에 중첩하는 것까지 가능합니다.

## 기여

새 버전의 Elementor를 대상으로 다시 추출하고, 재생성한 `data/`로 PR을 여십시오 —
무엇이 바뀌었는지는 `verify-schema.py`가 정확히 알려 줍니다.
[CONTRIBUTING.md](CONTRIBUTING.md)를 참고하십시오.

## 라이선스

MIT. **moksa**가 만들고 유지 관리합니다 · [moksaweb.com](https://moksaweb.com)

자매 스킬: [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
