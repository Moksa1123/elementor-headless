# elementor-headless

**直接把 JSON 寫出來建 Elementor 頁面，而不是去操作編輯器。**

這是一個 [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)，
把 Elementor 完整的編輯面貌——**橫跨 192 個 widget 與 13 個元素的 49,857 個控制項，
加上 Kit 的 773 個 Site Settings、48 個頁面設定、29 種 document 類型、51 個
dynamic tag、39 個 display condition，以及每一個 repeater 的項目欄位**——
以一個可查詢的資料庫的形式交到 AI coding agent 手上，
而不是一份它永遠讀不起的文件。

每一個 widget 還帶著**站台必須具備什麼、它才會存在**這項資訊：有 29 個需要
WooCommerce 外掛，36 個需要開啟某個 Elementor experiment。省略這件事的 schema
不是不完整，而是錯的——問它 `woocommerce-product-price`，它會信心十足地告訴你，
Elementor 沒有這個 widget。

[English](README.md) · 繁體中文 · [日本語](README.ja.md) · [한국어](README.ko.md)

---

## 為什麼

Elementor 把頁面以一棵 JSON 樹的形式存在 post meta 裡。把樹寫進去，頁面就存在了。
但 Elementor **不會驗證你寫了什麼**——它把你的值原封不動存起來，看得懂的就算繪出來，
剩下的默默丟掉。

不會有錯誤訊息。拼錯的控制項名稱、該放物件的地方放了字串、在 Free 站台上用了
Pro 專屬的控制項：這些全都會乾乾淨淨地存進去，在你自己的機器上算繪得好好的，
然後在真正要緊的地方悄悄失效。

所以一個要建 Elementor 頁面的 agent 只有兩條路：每次都去讀 Elementor 的 PHP 原始碼
（很貴——而且讀完還是不會告訴你 JSON 長什麼樣），或者用猜的（默默地錯）。
這個 skill 是第三條路。

```bash
$ python tools/el.py type slider
control type: slider   [FREE]  (elementor-core)

JSON value shape (what you write into _elementor_data settings):
  {"unit": "px", "size": "", "sizes": []}
```

## 運作方式

![architecture](assets/diagrams/architecture.svg)

三個階段。抽取只需要對**你自己的**站台、每個 Elementor 版本跑一次。
在那之後的一切都只是查詢。

## 安裝

```bash
git clone https://github.com/Moksa1123/elementor-headless
cd elementor-headless
python tools/install-skill.py claude-code --global     # or: cursor, codex-cli, gemini-cli, ...
python tools/install-skill.py --list
```

支援 8 個平台：Claude Code、Claude.ai、Cursor、Codex CLI、Gemini CLI、Devin
（前身 Windsurf）、GitHub Copilot、Continue。安裝慣例已於 2026-07-11 重新查證——
[8 個裡有 3 個在六週內就已經跟不上了](references/multiplatform-install-verification.md)，
所以這些是實際查過的，不是憑假設。

## 使用

```bash
python tools/el.py widgets --tier free --grep box   # find a widget
python tools/el.py widget heading --tab style       # its style controls
python tools/el.py container --tab layout           # flex + grid, with conditions
python tools/el.py css border-radius                # reverse lookup by CSS property
python tools/el.py group typography                 # what a group control expands into
python tools/el.py breakpoints                      # the responsive suffixes
python tools/el.py pro --check custom_css align     # exits 1 if any of these needs Pro
```

接著就是建構、檢查、上線：

```bash
python tools/el.py skeleton > page.json
python tools/validate-page.py page.json --target free
wp eval-file tools/apply-page.php 123 page.json
```

`validate-page.py` 會抓出 Elementor 不會抓的東西：不存在的控制項名稱、錯誤的值形狀、
不合法的單位、無效的選項、重複的 id、未滿足的條件，以及在 Free 目標上使用了
Pro 專屬的控制項。

## Token 成本

**比讀 Elementor 原始碼少 86.8% 的 token，比載入整份 schema 少 99.4%。
以模型讀取換算約快 5 倍，對上載入 schema 則約快 118 倍**（實測工具延遲：
每次查詢中位數 316 ms；讀取時間是以公開揭露的 1,000 tok/s 參考速率從 token
數換算出來的——改變這個速率，比例也不會動）。自己重現一次——腳本會寫出
`data/token-benchmark.csv`：

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| 任務 | 讀原始碼 | 載入 schema | **查詢** |
|---|---|---|---|
| 排一個 hero 容器（flex、boxed、響應式 padding） | 20,182 | 1,082,477 | **1,209** |
| 設定標題樣式（顏色、字體排印、對齊） | 8,329 | 1,082,477 | **836** |
| 設定按鈕樣式（顏色、padding、圓角、hover） | 7,803 | 1,082,477 | **3,664** |
| 讓任一 widget 的間距變成響應式 | 11,800 | 1,082,477 | **264** |
| 找出是哪個控制項在驅動某個 CSS 屬性 | — | 1,082,477 | **363** |
| **總計** | **48,114** | **1,082,477** | **6,336** |

隨著這份表面變得誠實（WooCommerce、Kit、selector、repeater 欄位），schema 從
583k 長到了 1.08M token，節省比例也從 89.1% 往下掉了——更豐富的答案就是要花
更多 token。只會一路變好看的數字，是被人挑選過的；這些數字是由腳本重新產生的，
往哪個方向動，就照哪個方向寫。

有兩件事讓它成立：資料是**用查的，從來不整份載入**；還有每個 widget 共用的那 211 個
Advanced 分頁控制項是**只存一次，而不是存 168 次**——它們佔了全部資料列的大多數，
把它們抽出來共用，schema 才有辦法維持在可查詢的狀態。

測量使用 tiktoken 的 `cl100k_base`——那是 OpenAI 的 tokenizer，不是 Claude 的，
所以絕對數字大約會有 ±10% 的落差。但在同一個 tokenizer 底下，兩份文字之間的比例是穩定的，
而比例才是這裡要主張的東西。方法與注意事項：
[token-efficiency.md](references/token-efficiency.md)。

## Free 與 Pro 是量出來的，不是猜出來的

Elementor Pro 會**把控制項注入到免費的 widget 裡**。在裝了 Pro 的站台上打開免費的
Heading widget，你會發現它的 Advanced 分頁裡坐著 Motion Effects、Sticky、Custom CSS、
Display Conditions 和 Custom Attributes。如果直接沿用 widget 本身的 tier，
這些每一個都會被標成「free」——然後你建出來的頁面在你這邊算繪得完美無缺，
一裝到 Free 站台上樣式就掉光了。

所以 tier 是量出來的。抽取兩次——一次載入 Pro，一次用
`wp --skip-plugins=elementor-pro`（它只影響那一個 CLI 程序；不會停用任何東西，
所以在正式站上跑是安全的）——然後比對差異：

| | Free 4.1.4 | + Pro 4.1.2 |
|---|---|---|
| widget | 64 | **135** |
| 每個 widget 都有的控制項 | 165 | **211**（+46） |
| `container` 上的控制項 | 277 | **356**（+79） |
| 控制項型別 | 52 | **59** |
| 群組控制項 | 11 | **16** |

Pro 注入到**每一個** widget 的那 46 個是：所有 `motion_fx_*`（37 個）、`sticky*`
（6 個）、`custom_css`、`_attributes`、`e_display_conditions`。

不要用推理去判斷 tier。**Border 和 Box Shadow 看起來很高級，但它們是免費的。
`_attributes` 看起來很基本，但它是 Pro。** 這個 repo 就曾經把 Border 誤標成 Pro
出貨過一次，就是因為用推理而不是用量的。

## 它準確嗎？讓它自己證明給你看。

這份 schema 來自 Elementor 4.1.4 / Pro 4.1.2。你的可能不一樣。別相信它——
去測試它。八個檢查，回答八個不同的問題，各自讀取不同的產出物：控制項堆疊、編譯後的樣式表、送達的 HTML、真實瀏覽器的計算樣式、真實指標事件，以及穿過 CDN 的公開網址。

**1. 這份 schema 跟你的安裝相符嗎？**

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

一旦發現偏移就會以非零狀態結束，所以可以拿它來當部署的關卡。

**2. 用這份 schema 建出來的頁面，算繪出的 CSS 真的是 schema 承諾的那樣嗎？**

schema 說明了每個控制項驅動哪些 CSS 屬性。這個驗證器會真的把頁面建出來，
讀回 Elementor 編譯出的樣式表，然後逐一檢查每一項——包括每個響應式的 key
是不是真的落在*那個斷點的* media query 裡面。

```bash
python tools/verify-render.py examples/demo-page.json rendered.css --post-id 9176
```

```
CSS property assertions: 94/94 passed
PASS
```

**3. schema 裡的每一個控制項，真的都能動嗎？**

`verify-render.py` 只涵蓋某個頁面剛好用到的那些控制項——在示範頁上是 94 個。
`sweep-controls.py` 負責剩下的：它會替每一個宣稱會驅動 CSS 的控制項合成一個合法的值，
解出讓它真正生效所需要的相依鏈，把它算繪出來，然後斷言那個值確實跑出來了。每個控制項
拿到的值都是**它專屬的**（一個獨特的十六進位色碼、一個獨特的像素尺寸），所以只要通過，
就代表*那個控制項*產生了*那個值*——而不是別的東西剛好寫了一個相似的屬性。

```bash
python tools/sweep-controls.py plan --out sweep/ --post-id <draft post>
# apply each batch, capture post-<id>.css
python tools/sweep-controls.py check sweep/ --out data/control-verification.csv
```

```
DESKTOP  (18,853 CSS-driving controls)
  verified by value   17,421  (92.4%)   the exact value we wrote is in the CSS
  property only        1,270  ( 6.7%)   right property, value not literally assertable
  FAILED                   0  ( 0.0%)
  skipped, untested      162  ( 0.9%)   no test could be built for these
  covered                      99.1%

RESPONSIVE SUFFIXES  (25,404 _tablet / _mobile keys, each asserted inside ITS
                      breakpoint's media query, with a value distinct from
                      desktop's, so a leak cannot pass)
  verified by value   24,568  (96.7%)
  FAILED                  17  ( 0.1%)
```

逐一控制項的結果隨附在 `data/control-verification.csv` - 包含被 `skipped` 的那些，
所以覆蓋率這個數字永遠不可能在看不到它們的情況下被讀到。

**而且這個 sweep 會反過來修正抽取器。** `build-indexes.py --verification` 會把算繪出來的
結果折回 schema 裡：有 9 個控制項宣稱自己支援某個響應式斷點，實際上根本不會吐出東西
（`hotspot.width_tablet` 完全不產生任何 CSS，已在隔離環境下驗證）。它們現在被標記為
`responsive_broken`，`el.py` 會印出 `rwd-BROKEN:`，而 `validate-page.py` 只要你寫了其中
一個就會報錯。要是沒有真的去算繪，這 9 個到現在都還會以「可正常運作的響應式控制項」
的身分待在 schema 裡。

**4. 把每一個吐出 CLASS 而不是 CSS 的控制項掃過一遍。** 樣式表的 sweep 根本看不到這些
控制項——而它們有 2,573 個（`_position`、`hide_tablet`、每一個 `view` / `shape` / `align`
控制項，還有那些 transform）。這一個驗證器讀的是**算繪出來的 HTML**，並且斷言那個 class
真的出現在 wrapper 上。

```bash
python tools/sweep-classes.py plan --out classsweep/ --post-id <draft post>
bash classsweep/RUN.sh
python tools/sweep-classes.py check classsweep/ --out data/class-verification.csv
```

```
CLASS-EMITTING CONTROLS  (2,573)
  verified by class     2,042  (79.4%)   the class we predicted is on the wrapper
  FAILED                    0  ( 0.0%)
  host never rendered     523  (20.3%)   the WIDGET produces no markup on a bare page,
                                         so there is no wrapper - not a pass, not a fail
  skipped, untestable       8  ( 0.3%)
PER-DEVICE CLASS PREFIXES  306    246 verified
classes_dictionary REMAPS   10     10 verified
```

跑了它才發現三件事，是其他任何東西都發現不了的：

- **`apply-page.php` 留下了一份過期的算繪 HTML 快取。** Elementor 會把它算繪出來的
  markup 存在 `_elementor_element_cache` 這個 post meta 裡，然後直接拿它回吐。
  Elementor 自己的儲存路徑會清掉它；直接寫 meta 則不會。所以文章更新了，CSS 也正確
  重建了，`_elementor_data` 讀回來一字不差——而頁面繼續送出**上一次的 markup**，
  完全沒有錯誤。在這個 bug 還活著的時候，CSS 的 sweep 橫跨 17,421 個控制項全綠，
  因為 CSS 是另一個檔案，我們每次都重建。第一次跑 HTML sweep 一分鐘就抓到它：
  全部 14 個批次回來的內容 byte 完全相同。
- **`validate-page.py` 一直在退回一個算繪得好好的頁面。** `icon-box` 的
  `position: "top"` 不在選項清單裡，而 Elementor 的 `classes_dictionary` 反正也會把它
  重新對映成 `block-start`。這是一個假的錯誤，現在改成一則提示。
- **schema 對 tablet 上的 class 說了錯的話。** 一個響應式的 class 控制項在*每個裝置上有
  不同的前綴*（是 `elementor-tablet-position-`，不是一個 `_tablet` 後綴），
  而抽取器一直把這些變體折疊在一起，把裝置前綴丟掉了。

**5. 每一個可放置的 widget，逐一做功能測試，一頁一個。** 控制項的 sweep 問的是
「每個設定能不能動」；這一項問的是更前面的那個問題——給了內容，widget 會把它
算繪出來嗎？在每一個內容控制項裡種入獨一無二的標記（repeater 項目是用抽取出的
欄位建出來的），一頁只放一個 widget，這樣 JS 錯誤或零尺寸的算繪都能明確歸咎到
唯一的一個 widget 上，每個 widget 一張元素截圖，跑三種 viewport。

```
168/168 placeable widgets  (85 core+pro on one site, 62 WooCommerce+bridges and
                            21 experiment-gated on another)
  126 rendered  - marker echo, real site content, or hidden-by-design
   42 correctly empty without site context (cart/checkout/loop on a bare page)
    0 broken
```

逐一 widget 的結果在 `data/widget-verification.csv`；每個有算繪出來的 widget
在 `shots/` 各有一張 PNG。

**6. 互動行為，用真實的指標去驅動。** 對互動式 widget 來說，算繪正確只是一半。
五個行為在公開頁面上被真的點擊過：

```
nested-tabs        click tab 2   -> content 2 shows, content 1 hides   PASS
nested-accordion   click item 2  -> <details> opens                    PASS
accordion          click item 2  -> body becomes visible               PASS
toggle             click item 1  -> body toggles open                  PASS
image-carousel     click next    -> active slide advances              PASS
```

至於那些 `:hover` 規則——任何靜態讀取都驗證不了——是用一個真實的指標去驅動的：
把游標移到 pseudo-class 所在的那個節點上，對宣告實際落地的那個節點讀
`getComputedStyle`，再跟送達的樣式表比對。transition 會先被停用，而且有揭露：
在一個被種入 79 秒 transition 的動畫進行到 200ms 時去讀顏色，比的是動畫中途的
一格對上終點狀態。

```
3,882 :hover probes, pointer-driven, on the live public pages
    verified          297   hovered, computed, matches the declaration
    OVERRIDDEN        113   all same-element seed collisions: the sweep sets two
                            hover controls that write the SAME property on the
                            same node (hover_size vs hover_bg_width), and one of
                            two deliberately different values must lose
    no-target-node  2,292   hover branches whose node needs content or state
    not-comparable  1,180   values the browser normalises
```


**7. 驗證「公開訪客」實際拿到的那個頁面。** 上面那一切讀的都是機器**內部**的產物——
從伺服器磁碟上抓的一個 CSS 檔案、從一次 PHP 呼叫吐出來的 HTML。
**這些沒有一個是訪客真正收到的東西。** 佈景主題、頁面快取、Varnish 和 CDN 全都夾在中間，
它們任何一個都可能送出別的東西，而伺服器端的每一項檢查依舊全綠。
這就是陷阱 9 再往外推一層。

```bash
python tools/verify-live.py examples/demo-page.json https://moksaweb.com/elementor-headless-demo/
```

```
GET https://moksaweb.com/elementor-headless-demo/
    113,397 bytes   x-cache=HIT  age=200
GET .../elementor/css/post-11.css      1,238 bytes     <- the Kit's globals
GET .../elementor/css/post-9176.css    5,411 bytes     <- the page
GET .../elementor/css/post-47.css      9,009 bytes
GET .../elementor/css/post-52.css     18,470 bytes
    -> 4 stylesheet(s), 34,131 bytes total

elements delivered      : 8/8
CSS properties delivered: 94  (across 46 settings)
  value-exact           : 43  (the exact value this tree asks for is in the delivered CSS)
  property only         : 3  (Elementor rewrites the value; the sweep already proved which)
wrapper-class assertions: 17 passed
not assertable          : 24 settings drive neither CSS nor a class

PASS - the page a visitor receives contains every element of the tree,
       the stylesheet it links carries every property the schema promised,
       and every wrapper carries the classes it should.
```

注意那四個樣式表。**一個頁面的樣式是被拆散在好幾個檔案裡的**——Kit 帶著全域的顏色和字體，
頁面自己帶著它自己的。這裡其他每一個驗證器都只從磁碟上讀一個 `post-<id>.css`，
那從結構上就註定是一幅不完整的圖。這一個讀的是頁面實際*連結*出去的那些檔案，
而且是穿過快取讀的（`x-cache=HIT`）——那才是訪客唯一會承認的「它能動」的定義。

**8. 自己去看。** `examples/demo-page.json` 是一個真實已發布的頁面，
除了這個 skill 之外什麼都沒用到。Elementor 編輯器從來沒有在它上面被打開過。

**https://moksaweb.com/elementor-headless-demo/**

## 在頁面之間、站台之間重複使用區塊

用的是 Elementor 自己的 JSON 交換格式——也就是編輯器裡 Export / Import Template
兩顆按鈕背後的那個檔案：

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json
wp --user=1 eval-file tools/import-template.php hero-block.json <target_post_id>
```

**絕對不要靠複製 `_elementor_data` 把一個區塊搬到另一個站台。** 媒體控制項存的是
attachment id，而那個 id 在另一個站台指向的是*另一張圖片*——或者根本什麼都沒有。
Elementor 的 `on_export` 會把 id 換成 url，`on_import` 則會把它重新下載進目標站台的
媒體庫。直接複製原始 meta，圖片就會默默壞掉，或是默默變成錯的圖片。這些工具會呼叫
Elementor 自己的匯入路徑，好讓那些 hook 真的跑到。來回實測結果：寫入 82 個設定，
遺失 0 個，被改動 0 個。

## 盒子裡有什麼

```
data/
  elementor-schema.json    3.2 MB   完整的編輯面貌 - 用查的，從不整份載入
  controls.csv             2.0 MB   每個 widget／元素專屬的控制項
  common-controls.csv       39 KB   每個 widget 共用的那 210 個
  pro-only-controls.csv     33 KB   安全表
  pro-only-widgets.csv     3.0 KB
  control-types.csv        4.6 KB   全部 59 種 JSON 值形狀
  group-controls.csv       3.7 KB   16 個群組，以及它們展開成的扁平 key
  widgets.csv              8.3 KB   135 個 widget + 3 個元素
  breakpoints.csv          0.2 KB
  control-verification.csv          逐一控制項：它真的吐出它宣稱的那個 CSS 嗎？
  class-verification.csv            逐一控制項：它真的吐出它宣稱的那個 CLASS 嗎？
  browser-verification*.csv         逐一控制項：Chromium 真的把它「計算」出來了嗎？（2 個站台）
  widget-verification.csv           逐一 widget：它真的算繪出自己的內容嗎？（168 個）
  hover-verification.csv            逐一 :hover 規則，用真實指標驅動
  dynamic-tags.csv                  __dynamic__ 的那塊表面，51 個 tag
  css-selectors.csv                 每個控制項的 CSS 實際落在哪個節點上
  token-benchmark.csv               可重現的 token 與延遲測量結果

tools/
  el.py                          查詢 schema - 主要入口
  validate-page.py               對頁面樹做飛行前檢查
  apply-page.php                 寫進去：meta + 重建 CSS + HTML 快取 + 備份
  extract-elementor-schema.php   dump 一個運行中的安裝
  build-indexes.py               dump + sweep 結果 -> 出貨用的資料檔
  verify-schema.py               這份 schema 跟你的安裝相符嗎？
  verify-render.py               Elementor 吐出來的真的是 schema 承諾的嗎？
  verify-live.py                 穿過 CDN 之後，公開頁面上真的有它嗎？
  verify-browser.py              真實的 Chromium 有在對的節點上把它「計算」出來嗎？
  verify-interactions.py         tab 會切換、accordion 會打開、carousel 會前進嗎？
  sweep-controls.py              算繪每一個 CSS 控制項，斷言樣式表
  sweep-classes.py               算繪每一個 CLASS 控制項，斷言 HTML
  sweep-browser.py               宣告值對計算值，每一個控制項，在 Chromium 裡
  sweep-widgets.py               每一個 widget 的功能測試，一頁一個，附截圖
  sweep-hover.py                 每一條 :hover 規則，用真實指標驅動
  export-template.php            匯出成 Elementor 自己的 JSON 格式
  import-template.php            匯入一份，連同媒體，走 Elementor 自己的路徑
  benchmark-tokens.py            重現那些 token 數字
  install-skill.py               8 平台安裝器

references/   data-model · control-types · containers-and-layout · responsive
              templates-and-conditions · import-export · extraction-traps
              token-efficiency
examples/     demo-page.json - 上面那個已發布的頁面
```

## 九個陷阱

用最直覺的方式去做這件事，會在九個各自獨立的地方出錯，每一種都會產出一份看起來很完整、
實際上在說謊的 skill。**這九個在被抓到之前，全都在這個 repo 裡出貨過**——有些是靠讀
Elementor 的原始碼才發現的，其餘的只有把每一個控制項都算繪出來、再真的去看跑出什麼，
才會浮現。詳細記錄寫在
[extraction-traps.md](references/extraction-traps.md)：

1. **對 Elementor 來說，WP-CLI 看起來像前台**，所以它回傳的是精簡版的控制項堆疊：
   **46% 的控制項和大約 100% 的分頁／標籤 metadata 就這樣消失了**，而且沒有任何錯誤。
   抽取器停掉了那條路徑，而且放了三隻金絲雀——寧可中止，也不吐出殘缺的資料。
2. **響應式是兩套機制**，而最直覺的測試只會找到其中一套。整個系統裡**任何地方**
   都沒有 `padding_tablet` 這個控制項物件——但 `padding_tablet` 是能用的。
   靠「找有後綴的兄弟控制項」來偵測響應式，會漏掉 padding、margin、
   width、字體大小和 gap。（修正之後，從 9.8% → 30.1% 的控制項。）
3. **控制項的 tier 不是它所屬 widget 的 tier**，因為 Pro 會注入到免費的 widget 裡。
   要用量的，不要用繼承的。
4. **一個控制項可以被三種不同的方式閘控**，而 `condition` 只是其中一種。有 152 個控制項
   *只*被一種進階的布林形式閘控，那套形式還有自己的運算子。另外有 499 個控制項會把*另一個*
   控制項的值內插進自己的 CSS 裡——只要那個值是空的，Elementor 就會把整條宣告整個丟掉，
   而且是在所有已載明的條件都滿足、也不會有任何錯誤的情況下。設了漸層角度卻沒設漸層顏色，
   你就什麼都拿不到，而且是無聲的。
5. **響應式控制項的相依關係會在斷點上被重新檢查一次。** 設了 `X_tablet` 卻沒設
   `Y_tablet`，桌機算繪得完美無缺，tablet 卻無聲地一片空白。有 1,433 個響應式後綴
   什麼都沒吐出來，原因正是這個。
6. **`is_responsive` 承諾得太多。** `hotspot.width` 帶著跟 `container.padding` 一模一樣的
   旗標；但 `padding_tablet` 能用，`width_tablet` 卻什麼都不吐。只有算繪知道真相——
   所以 sweep 會把它的結果餵回去，修正 schema。
7. **CSS 只是一個控制項能做的事情的一半。** 有 2,573 個控制項是靠在 wrapper 上加一個
   **class** 來起作用的，其中 1,894 個完全不吐任何 CSS——所以樣式表的 sweep 不管跑得
   多綠，都不可能看見它們存在。它們全都是靠「Elementor 註冊了一個 `prefix_class`，
   所以大概能動吧」這種理由在這裡出貨的。
8. **class 控制項的值會被重新對映，而且它的前綴會隨裝置改變。**
   `position: "top"` 不在選項清單裡，但它照樣算繪出 `elementor-position-block-start`
   （`classes_dictionary`）。`position_tablet` 算繪出來的是
   `elementor-**tablet**-position-…`，而不是在 class 上加一個 `_tablet` 後綴。switcher 存的是
   它的 `return_value`，所以 `hide_tablet: "yes"` 算繪出 `elementor-yes`，什麼都沒隱藏到。
   還有，`"columns": 0` 什麼都不吐，但 `"columns": "0"` 可以動。
9. **寫入 `_elementor_data` 會留下一份過期的算繪 HTML 快取。** 文章更新了，CSS 重建了，
   meta 讀回來一字不差——而頁面永遠繼續送出它**上一次的 markup**，完全沒有錯誤。
   在這個 bug 還活著的時候，一次橫跨 17,421 個控制項的 CSS sweep 跑出全綠，
   因為 CSS 是另一個檔案，我們每次都重建。

陷阱 9 一句話就說完了這整個專案的核心論點：**一個驗證器只找得到它所讀的那個通道裡的
bug。** 在一個通道裡跑出全綠，對其他通道什麼都沒說。

## 參與貢獻

拿更新版的 Elementor 重新抽取一次，然後帶著重新產生的 `data/` 開一個 PR——
`verify-schema.py` 會明確告訴你有哪些東西變了。請看
[CONTRIBUTING.md](CONTRIBUTING.md)。

## 授權

MIT。由 **moksa** 打造並維護 · [moksaweb.com](https://moksaweb.com)

姊妹 skill：[rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
