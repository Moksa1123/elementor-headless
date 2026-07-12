# elementor-headless

**用寫 JSON 的方式建 Elementor 頁面，而不是去操作編輯器。**

這是一個 [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)，
把 Elementor 完整的編輯表面以可查詢資料庫的形式交給 AI coding agent——並且
透過在真實站台上實際渲染、點擊與量測，證明其中每一項宣稱，因為當你寫錯時，
Elementor 從來不會報錯。

```
192 widgets · 13 elements · 49,857 control pairs
the Kit's 773 Site Settings · 48 page settings · 29 document types
51 dynamic tags · 39 display conditions · every repeater's item fields
```

[English](README.md) · 繁體中文 · [日本語](README.ja.md) · [한국어](README.ko.md)

---

## 問題所在

Elementor 把頁面存成 post meta 裡的一棵 JSON 樹。把樹寫進去，頁面就存在。但
Elementor **不會驗證你寫了什麼**——它儲存你的值，渲染它看得懂的部分，其餘
默默丟掉。

沒有任何錯誤。拼錯的 control 名稱、該放物件的地方放了字串、Free 站台上用了
Pro 專屬 control、一個應該寫成 `"hidden-tablet"` 卻寫成 `hide_tablet: "yes"`：
全部都能順利存檔，然後安靜地什麼也不做。一個 90% 正確的頁面看起來和 100%
正確的頁面一模一樣，直到有人發現 padding 從來沒生效過。

因此要建 Elementor 頁面的 agent 只有兩條路：每次都去讀 Elementor 的 PHP
原始碼（昂貴，而且還是看不出 JSON 的形狀），或者用猜的（默默出錯）。這個
skill 是第三條路：

```bash
$ python tools/el.py type slider
control type: slider   [FREE]  (elementor-core)

JSON value shape (what you write into _elementor_data settings):
  {"unit": "px", "size": "", "sizes": []}
```

## 運作方式

![architecture](assets/diagrams/architecture.svg)

三個階段。**Extraction（抽取）**每個 Elementor 版本執行一次，對著真實安裝跑，
配有三道 canary，一旦資料劣化就拒絕輸出。**Verification（驗證）**在真實站台上
渲染每一個 control、widget 與互動，並把實際發生的結果回寫進資料。
**Query（查詢）**則是 agent 在建頁時唯一要做的事。

## 安裝

```bash
git clone https://github.com/Moksa1123/elementor-headless
cd elementor-headless
python tools/install-skill.py claude-code --global     # or: cursor, codex-cli, gemini-cli, ...
python tools/install-skill.py --list
```

8 個平台：Claude Code、Claude.ai、Cursor、Codex CLI、Gemini CLI、Devin
（前身 Windsurf）、GitHub Copilot、Continue。各平台慣例於 2026-07-11 重新
驗證——[8 個裡有 3 個在六週內已經漂移](references/multiplatform-install-verification.md)，
所以這些慣例是查核出來的，不是假設出來的。升級時會清掉前一版留下的檔案：
一個把去年的錯誤資料集留在今年正確資料集旁邊的安裝器，比沒有安裝器更糟。

## 使用

查東西——一次查詢約花 700 個 token，而且答案完整：

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

接著建頁、檢查、上線：

```bash
python tools/el.py skeleton > page.json
python tools/validate-page.py page.json --target free --have woocommerce
wp eval-file tools/apply-page.php 123 page.json page-settings.json
python tools/verify-live.py page.json https://your-site/your-page/
```

- `validate-page.py` 抓出 Elementor 不會抓的：未知的 control、錯誤的值形狀、
  不合法的單位、無效的選項、重複的 id、三種未滿足的相依（包括對照**預設值**
  評估的 conditions，所以設了 `success_message` 卻沒設 `custom_messages` 會
  得到警告，而不是默默退回預設）、多選值、把 `0` 當數字寫進 class 類
  control、Free 目標站上的 Pro 專屬 control，以及**目標站台根本不可能擁有的
  widget**。
- `apply-page.php` 寫入 4 個 meta key、選用的頁面設定（包括 Canvas 真正需要
  的 `template` → `_wp_page_template` 拆分）、重建編譯後的 CSS **並刪除已
  渲染的 HTML 快取**——漏掉最後這一步，一棵正確的樹會永遠端出前一版頁面，
  而且沒有任何錯誤。
- `verify-live.py` 穿過快取／CDN 抓取公開 URL，把樹、CSS 值與 wrapper class
  對照實際從線路上傳回來的內容逐一斷言。

## 不是每個安裝都有每個 widget

**widget 表面是「站台」的屬性，不是 Elementor 的屬性。**同一套 Elementor
4.1.4 / Pro 4.1.2 在一台機器上註冊 148 個 widget，在另一台上是 192 個，而且
什麼都沒壞——多出來的那些需要第一台機器沒有的東西。缺了這件事的 schema
不是不完整，而是**錯的**：問它 `woocommerce-product-price`，它會信心十足地
回答 Elementor 沒有這個 widget。

所以每個 widget 都帶著它需要什麼的資訊，直接從其 module 在 Elementor 原始碼
裡自己的 `is_active()` gate 讀出——而且以 gate 為準，不是 module 自己的
`EXPERIMENT_NAME` 常數；在學到這個教訓之前，那個常數把 21 個已註冊、能渲染
的 widget 標錯了：

| 需要什麼 | widget 數 |
|---|---|
| 什麼都不需要——一直都在 | 104 |
| `plugin:woocommerce` | 29 |
| 某個外掛註冊的 WP legacy widget | 33 |
| `experiment:container` / `nested-elements` / `e_atomic_elements` / … | 26 |

`validate-page.py` 遇到目標站台不可能擁有的 widget 會直接報錯；用
`--have woocommerce nested-elements` 告訴它站台實際有什麼。

**Elementor V4 atomic elements（`e-heading`、`e-flexbox`、`e-form-*`，共 18
個）是另一套資料模型**——帶型別標記的 props 加上獨立的 `styles` 陣列，不是
`settings` + controls。這個 skill 會回報它們的 prop schema
（`el.py widget e-heading`），並拒絕假裝自己能驗證用它們建頁。

## Token 成本，還有時間

**比讀 Elementor 原始碼少 86.8% 的 token，比載入整份 schema 少 99.4%。模型
讀入約快 5 倍，對比載入 schema 約快 118 倍。**工具延遲是實測的（每次查詢
中位數 316 ms）；讀入時間是由 token 數在一個公開揭露的 1,000 tok/s 參考速率
下推導出來的——改變速率，比值不會動。自己重現一次；腳本會寫出
`data/token-benchmark.csv`：

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| 任務 | 讀原始碼 | 載入 schema | **查詢** |
|---|---|---|---|
| 排一個 hero container（flex、boxed、響應式 padding） | 20,182 | 1,082,477 | **1,209** |
| 設定 heading 樣式（顏色、typography、對齊） | 8,329 | 1,082,477 | **836** |
| 設定 button 樣式（顏色、padding、圓角、hover） | 7,803 | 1,082,477 | **3,664** |
| 讓任一 widget 的間距變成響應式 | 11,800 | 1,082,477 | **264** |
| 找出哪個 control 驅動某個 CSS 屬性 | — | 1,082,477 | **363** |
| **總計** | **48,114** | **1,082,477** | **6,336** |

節省幅度曾經是 89.1%。它是**下降**的——因為這個表面變得誠實（WooCommerce、
Kit、selector、repeater 欄位），schema 從 583k 長到 1.08M token，而更豐富的
答案要花更多 token。只會往好的方向走的數字是被人為挑選過的；這些數字由腳本
重新產生，不管往哪個方向走。

兩件事讓它成立：資料是**用查的，從不整份載入**，以及每個 classic widget 共用
的 211 個 Advanced 分頁 control **只存一份，而不是存 168 次**。token 計數用
tiktoken 的 `cl100k_base`——那是 OpenAI 的 tokenizer，不是 Claude 的，所以
絕對數字會有大約 ±10% 的偏移；同一個 tokenizer 底下的比值是穩定的，而比值
才是這裡的主張（[token-efficiency.md](references/token-efficiency.md)）。

## Free 與 Pro 是量出來的，不是猜的

Elementor Pro 會**把 control 注入免費 widget**：Pro 站台上的免費 Heading
widget 帶著 Motion Effects、Sticky、Custom CSS、Display Conditions 與 Custom
Attributes。若直接繼承 widget 的 tier，這 46 個全都會被標成「free」——你建
的頁面在你這邊渲染得完美無缺，然後在 Free 安裝上樣式掉光。

所以 tier 是量出來的：載入 Pro 抽一次，用 `wp --skip-plugins=elementor-pro`
再抽一次（只影響那一個 CLI process；對正式站是安全的），然後 diff。同一套
方法再往前推一個軸，就是 WooCommerce——它不只是加 29 個 widget，還把
`product_query_exclude*` 注入 Pro 自己的 loop widget，只有一份關掉
WooCommerce 的 dump 才能揭露那些 control 是誰的。第三方污染也用同樣方式
排除：Rank Math 注入 `accordion`，Unlimited Elements 注入 container，帶著
它們抽出來的 schema 會把它們的 control 當成 Elementor 的出貨。

不要用推理判斷 tier。**Border 和 Box Shadow 看起來很高級，其實是免費的。
`_attributes` 看起來很基本，其實是 Pro。**這個 repo 就曾經因為用推理而不是
量測，把 Border 誤標成 Pro 出貨過一次。而且 Elementor core 在 Pro 關閉時會
註冊**名字和真正的 Pro widget 一模一樣的 promo stub**——把無 Pro 的 dump
照單全收，26 個 Pro widget 就會被讀成免費。

## 它準嗎？讓它自己證明。

別信它——測它。八道檢查、八個不同的問題，從不同的產物讀出來：control
堆疊、編譯後的樣式表、實際送達的 HTML、真實瀏覽器的 computed style、真實的
指標事件，以及穿過 CDN 的公開 URL。**驗證器只找得到它所讀取的那條通道裡的
bug**——這裡每一道檢查的存在，都是因為某個更淺的檢查漏掉過真實的問題。

**1. schema 和你的安裝相符嗎？**

```bash
python tools/verify-schema.py mine.json --free-dump mine-free.json
```

逐一走訪每個 (owner, control) 配對，檢查型別與 Free/Pro 宣稱，而且——因為
schema 記載了每個 widget 的需求——能把「schema 錯了」和「這個安裝沒有
WooCommerce」區分開來，而不是對兩者都亂喊狼來了。對兩個抽取站台都 PASS；
出現漂移時以非零結束，所以可以拿來擋部署。

**2. 每個會產生 CSS 的 control 真的有輸出它的 CSS 嗎？**

每個 control 拿到一個**專屬於它**的值（一個獨一無二的 hex 顏色、一個獨一
無二的像素尺寸），相依鏈自動求解，輸出則是在**公開 URL 實際送達的**樣式表裡
斷言——不是伺服器磁碟上的某個檔案：

```
25,259 CSS-driving controls    99.4% covered, 0 failures
33,448 responsive suffixes     each asserted inside ITS media query, with a value
                               distinct from desktop's, so a leak cannot pass
```

當 Elementor 自己的 metadata 是錯的，以渲染結果為準：有 9 個 control 宣稱
支援某個響應式斷點卻從不輸出，schema 現在對它們標記 `rwd-BROKEN`。

**3. 每個輸出 class 的 control 真的把 class 放上 wrapper 了嗎？**

有 2,573 個 control 的作用方式是在 wrapper 附加一個 class，而不是輸出
CSS——樣式表檢查對它們全部在結構上是盲的。從送達的 HTML 讀出：98.2% 掃過、
0 個失敗，包括 `classes_dictionary` 的 legacy 重對映（`position: "top"` 渲染
成 `elementor-position-block-start`）以及各裝置的前綴（是
`elementor-tablet-position-`，不是 `_tablet` 後綴）。

**4. 真實瀏覽器真的把宣告的值「計算」出來了嗎？**

一條規則可以躺在檔案裡卻輸掉——輸給 specificity、輸給 cascade、輸給一個
什麼都選不到的 selector。`sweep-browser.py` 在 Chromium 裡打開每一頁，把
Elementor 的宣告和 `getComputedStyle` 比對，而且是在**規則實際命中的那個
節點上**比（這正是 `data/css-selectors.csv` 存在的理由）：

```
48,873 probes across two live sites with different themes
25 of 26 override patterns IDENTICAL on both -> facts about Elementor,
   led by: _element_width's max-width is dead on every widget inside a
   container, killed by Elementor's own frontend.css at specificity (0,4,0)
 1 of 26 site-specific -> a fact about that theme, named by the data
```

**5. 每個 widget 拿到內容之後真的渲染出來了嗎？**

在每個內容 control 裡種入獨一無二的標記（repeater 項目用抽取出的欄位建構），
**一頁只放一個 widget**，所以任何 JS 錯誤或零尺寸渲染都能歸因到唯一一個
widget，每個 widget 各拍一張元素截圖，三種 viewport：

```
168/168 placeable widgets across the two sites
  126 rendered — marker echo, real site content, or hidden-by-design
   42 correctly empty without site context (cart/checkout/loop on a bare page)
    0 broken
```

**6. 互動式 widget 真的能互動嗎？**

在公開頁面上打真實的指標事件：

```
nested-tabs        click tab 2  -> content 2 shows, content 1 hides    PASS
nested-accordion   click item 2 -> <details> opens                     PASS
accordion          click item 2 -> body becomes visible                PASS
toggle             click item 1 -> body toggles open                   PASS
image-carousel     click next   -> active slide advances               PASS
```

至於 `:hover` 規則——任何靜態讀取都無法驗證——由真實指標驅動：3,882 個
探測、297 個以值驗證通過；113 個 override 全數是同元素的 seed 碰撞（兩個
hover control 對同一個屬性寫入刻意不同的值——必有一個輸），逐列分類。過程
會先關閉 transition 並揭露這項介入：在一個被 seed 成 79 秒的 transition 開始
200 ms 後讀到的顏色，是動畫中間的一格，不是判決。

**7. 工作流程端到端撐得住嗎？**

以下每一項都以 headless 方式建好，再於真實站台上用瀏覽器驗證：

- **Global colors**：把一個顏色附加進 kit 的 `custom_colors`，透過
  `__globals__` 引用，計算結果正是那個顏色
- **Dynamic tags**：`post-title` 綁定送出文章真正的標題
- **Display conditions**：加了 `logged_in` 條件的元素在匿名 HTML 裡不存
  在——是在伺服器端被丟掉，不是被 CSS 藏起來
- **Theme Builder**：範圍限定在單一頁面的 header 只在那一頁渲染，其他地方
  都沒有
- **Popups**：`page_load` 觸發的 popup 在匿名瀏覽器裡打開
- **Loop Builder**：loop-item 範本加 loop-grid 渲染出三篇真實文章
- **Forms**：匿名填寫 → nonce → 資料庫紀錄 → 自訂成功訊息
- **Canvas**：`template: elementor_canvas` 移除佈景主題的外框（透過
  `_wp_page_template`，光靠頁面設定碰不到）
- **Templates**：用 Elementor 自己的 JSON 格式匯出／匯入，媒體由它自己的
  hook 重新落地

**8. 公開訪客拿到的頁面包含全部這些嗎？**

```bash
python tools/verify-live.py examples/demo-page.json https://moksaweb.com/elementor-headless-demo/
```

抓取公開 URL 以及**該頁連結的每一張樣式表**（一頁的樣式分散在好幾個檔案
裡——Kit 的全域樣式住在另一個檔案），穿過 edge cache，並斷言樹、CSS 值與
wrapper class。對被竄改的樹它會失敗——一個從來沒紅過的驗證器不是驗證器。

示範頁是真實的、已發布的，而且從未在編輯器裡打開過：
**https://moksaweb.com/elementor-headless-demo/**

## 陷阱

用直覺的做法做上面任何一件事都會錯，而且有**十一種可以編號的錯法**——每一
種都曾在這個 repo 裡真的出過貨才被抓到，如今每一種都變成一道 canary、一條
驗證規則或一個資料欄位。完整寫在
[extraction-traps.md](references/extraction-traps.md)：

1. WP-CLI 拿到的是被削過的 control 堆疊——46% 的 control 無聲消失
2. 響應式是兩套機制；`padding_tablet` 沒有 control 物件卻能用
3. control 的 tier 不等於它所屬 widget 的 tier——Pro 會注入免費 widget
4. control 有三種被 gate 的方式；499 個 control 死在一個空的插值上
5. 響應式相依會在斷點上重新檢查一次
6. `is_responsive` 說得太滿——只有渲染知道真相
7. CSS 只是 control 能做的事的一半——有 2,573 個改成輸出 class
8. class 值會被重對映，而它的裝置前綴是另一個字串
9. 寫入 `_elementor_data` 會留下過期的已渲染 HTML 快取——正確的樹端出前
   一版頁面，而一次 17k control 的掃描曾壓著這個 bug 跑到全綠
10. widget 表面是安裝的屬性，不是 Elementor 的屬性
11. 一條規則可以在樣式表裡卻「輸掉」——只有瀏覽器看得見

還有那些寫在各自所屬文件裡的：Canvas 的 `template` 設定存在
`_wp_page_template`，不在頁面設定裡；library 範本需要
`elementor_library_type` **taxonomy** 和 conditions 的**快取**，否則 Theme
Builder 永遠看不見它；`theme-*` widget 的 dynamic 綁定是編輯器在插入當下
給的，所以 headless 的樹要自己把 `__dynamic__` 寫進去；WP legacy 橋接把所有
東西收在 `settings.wp` 底下；`e_display_conditions` 是一個包著 JSON
**字串**的陣列，而文件過去示範的裸陣列存起來沒問題、然後被無聲忽略。

## 盒子裡有什麼

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

## 誠實的限制

- **Elementor V4 atomic elements**：僅支援查詢。建構它們是另一套資料模型，
  這個 skill 還不會寫。
- **依賴情境的 widget**（購物車、結帳、文章留言、商品零件）在空白頁上驗證為
  「正確地空白」；它們的完整行為需要商店或文章情境，任何掃描都不會憑空捏造。
- **綁定版本**：這裡的每一個數字都是在 Elementor 4.1.4 / Pro 4.1.2 上量出來
  的。新版本可能讓其中任何一項失效——所以每一個驗證器都隨附出貨，可以對
  *你的*安裝重新執行。
- `page_load` 以外的 popup 觸發條件、`save-to-database` 以外的表單動作，
  以及第三方擴充的 widget，都有抽取但未經 E2E 驗證。

## 為你的安裝重新產生

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

## 跨頁面、跨站台重用區塊

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json
wp --user=1 eval-file tools/import-template.php hero-block.json
```

絕對不要用複製 `_elementor_data` 的方式在站台之間搬區塊：媒體 control 存的
是附件 **id**，而同一個 id 在另一個站台上是另一張圖。這些工具走 Elementor
自己的匯入路徑，讓它的 `on_import` hook 重新下載媒體。另外
`[elementor-template id="123"]` 可以把任何已儲存的範本嵌進任何 WordPress
內容——包括不靠 Pro 就把區塊巢狀進頁面，用的是免費的 shortcode widget。

## 貢獻

拿新版 Elementor 重新抽取，帶著重新產生的 `data/` 開 PR——`verify-schema.py`
會確切告訴你什麼變了。見 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 授權

MIT。由 **moksa** 打造與維護 · [moksaweb.com](https://moksaweb.com)

姊妹 skill：[rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
