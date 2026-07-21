# elementor-headless

**用寫 JSON 的方式蓋 Elementor 頁面，不開編輯器。**

這是一個 [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)：
把 Elementor 完整的頁面編寫表面做成一個可查詢的資料庫，交給 AI coding agent
使用——而且資料庫裡的每一條聲明，都在真實站台上經過渲染、點擊、量測驗證，
因為 Elementor 從來不會在你寫錯的時候報錯。

```
192 widgets · 13 elements · 49,857 control pairs
the Kit's 773 Site Settings · 48 page settings · 29 document types
51 dynamic tags · 39 display conditions · every repeater's item fields
```

[English](README.md) · 繁體中文 · [日本語](README.ja.md) · [한국어](README.ko.md)

---

## 問題所在

Elementor 把頁面存成 post meta 裡的一棵 JSON 樹。把樹寫進去，頁面就存在了。
但 Elementor **不會驗證你寫的東西**——它照單全收，看得懂的就渲染，看不懂的
就默默丟掉。

全程沒有任何錯誤訊息。control 名稱打錯、該放物件的地方塞了字串、在 Free 站
上用了 Pro 才有的 control、把 `hide_tablet` 設成 `"yes"`（正確值其實是
`"hidden-tablet"`）：這些全都能順利存檔，然後安靜地不生效。一個 90% 正確的
頁面，看起來跟 100% 正確的頁面一模一樣——直到有人發現 padding 從來沒套上去。

所以要讓 agent 蓋 Elementor 頁面，過去只有兩條路：每次都去讀 Elementor 的
PHP 原始碼（很貴，而且讀完還是不知道 JSON 該長什麼樣），或者用猜的（錯得
無聲無息）。這個 skill 是第三條路：

```bash
$ python tools/el.py type slider
control type: slider   [FREE]  (elementor-core)

JSON value shape (what you write into _elementor_data settings):
  {"unit": "px", "size": "", "sizes": []}
```

## 運作方式

![architecture](assets/diagrams/architecture.svg)

三個階段。**Extraction** 每個 Elementor 版本跑一次，對著真實安裝抽取，由三
道 canary 把關——寧可中止，也不輸出劣化的資料。**Verification** 把每個
control、每個 widget、每個互動都放到真實站台上渲染一遍，再把實際發生的結果
寫回資料裡。**Query** 則是 agent 蓋頁面時唯一要做的事。

## 安裝

```bash
git clone https://github.com/Moksa1123/elementor-headless
cd elementor-headless
python tools/install-skill.py claude-code --global     # or: cursor, codex-cli, gemini-cli, ...
python tools/install-skill.py --list
```

支援 8 個平台：Claude Code、Claude.ai、Cursor、Codex CLI、Gemini CLI、Devin
（前身 Windsurf）、GitHub Copilot、Continue。各平台的安裝慣例已於 2026-07-11
重新查證——[八個裡有三個在六週內就變了](references/multiplatform-install-verification.md)，
所以這份清單是查出來的，不是想當然。升級時會順手清掉舊版留下的檔案：一個會
把去年的錯誤資料留在今年的正確資料旁邊的安裝器，比沒有安裝器更糟。

## 使用

裝好 skill 之後，直接用白話跟你的 agent 描述頁面就行。下面這些工具你自己一
個都不用碰（想碰當然也可以）——skill 會教 agent 跑完整個流程：

> 在 post 123 蓋一個 landing page：深色 hero、960px boxed、三張 icon-box
> 卡片排成一排、手機上改成直疊，再加一顆圓角 CTA 按鈕。這個站沒有
> Elementor Pro——只能用免費 widget。

agent 接到之後會做什麼、每一步靠哪個工具：

```
1. 查詢表面           el.py            有哪些 control、JSON value shape、
                                       各種 gate、Free 還是 Pro
2. 寫出樹             (agent 自己)     照著 shape 直接寫 _elementor_data
3. 寫入前先驗證       validate-page.py 不存在的 control、錯的 shape、未滿足
                                       的相依、Pro 用在 Free、缺的外掛
4. 透過 WP-CLI 套用   apply-page.php   4 個 meta key + 頁面設定 + 重建 CSS
                                       + 清掉渲染 HTML 快取
5. 驗證線上頁面       verify-live.py   穿過快取/CDN 的公開網址
```

第 1 到 3 步完全在本地進行——規劃和驗證根本不需要碰站台。第 4、5 步需要
WordPress 主機上的 WP-CLI（通常走 SSH）；只要能執行 `wp eval-file`，什麼管
道都行。

agent 靠的就是這些查詢——一次查詢只花幾百個 token，而且一次就把問題答完：

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

然後建構、檢查、上線：

```bash
python tools/el.py skeleton > page.json
python tools/validate-page.py page.json --target free --have woocommerce
wp eval-file tools/apply-page.php 123 page.json page-settings.json
python tools/verify-live.py page.json https://your-site/your-page/
```

- `validate-page.py` 抓的是 Elementor 自己不會抓的問題：不存在的 control、
  寫錯的 value shape、不合法的單位、無效的選項、重複的 id、三種未滿足的相依
  關係全數在內（條件是拿**預設值**下去評估的，所以只設 `success_message`
  沒開 `custom_messages` 會得到警告，而不是被默默退回預設訊息）、
  multi-select 的值、被塞進 class control 的數字 `0`、在 Free 目標上用了
  Pro 專屬 control，以及**目標站根本不可能有的 widget**。
- `apply-page.php` 寫入 4 個 meta key 和選配的頁面設定（包括 Canvas 真正需
  要的 `template` → `_wp_page_template` 分流）、重建編譯後的 CSS，**並且刪
  掉渲染 HTML 快取**——少做最後這一步，樹是對的，端出來的卻永遠是上一版頁
  面，而且沒有任何錯誤。
- `verify-live.py` 穿過快取和 CDN 抓公開網址，拿線上實際回傳的內容逐一核對
  樹、CSS 值和 wrapper class。

## 不是每個安裝都有每個 widget

**widget 表面是「站台」的屬性，不是 Elementor 的。**同一套 Elementor 4.1.4 /
Pro 4.1.2，在這台機器上註冊 148 個 widget，在另一台上是 192 個，而且兩邊都
沒壞——多出來的那些，需要第一台機器沒有的東西。缺了這層資訊的 schema 不是
不完整，是**錯的**：問它 `woocommerce-product-price`，它會斬釘截鐵地告訴你
Elementor 沒有這個 widget。

所以每個 widget 都記錄著自己需要什麼，直接從它所屬模組的 `is_active()` gate
讀出來——而且以 gate 為準，不是模組自己的 `EXPERIMENT_NAME` 常數；在學到這
一課之前，那個常數曾把 21 個實際有註冊、有渲染的 widget 標錯過。

| 需要什麼 | widget 數 |
|---|---|
| 什麼都不用——一直都在 | 104 |
| `plugin:woocommerce` | 29 |
| 某個外掛註冊的 WP 傳統 widget | 33 |
| `experiment:container` / `nested-elements` / `e_atomic_elements` / … | 26 |

`validate-page.py` 碰到目標站不可能有的 widget 會直接報錯；用
`--have woocommerce nested-elements` 告訴它站上有什麼。

**Elementor V4 的 atomic 元素（`e-heading`、`e-flexbox`、`e-form-*`，共 18
個）是另一套資料模型**——帶型別標記的 props 加上獨立的 `styles` 陣列，不是
`settings` + controls。這個 skill 能回報它們的 prop schema
（`el.py widget e-heading`），但不會假裝自己有能力驗證怎麼蓋它們。

## Token 成本，還有時間

**比讀 Elementor 原始碼省 86.8% 的 token，比整份載入 schema 省 99.4%。模型
讀入速度快約 5 倍；相較於載入 schema 則約快 118 倍。**工具延遲是實測的（每
次查詢中位數 316 ms）；讀入時間則是拿 token 數，用公開的 1,000 tok/s 參考速
率換算出來的——速率換掉，比值也不會變。你可以自己重現，腳本會寫出
`data/token-benchmark.csv`：

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| 任務 | 讀原始碼 | 載入 schema | **查詢** |
|---|---|---|---|
| 排一個 hero container（flex、boxed、響應式 padding） | 20,182 | 1,082,477 | **1,209** |
| 幫 heading 上樣式（顏色、typography、對齊） | 8,329 | 1,082,477 | **836** |
| 幫 button 上樣式（顏色、padding、圓角、hover） | 7,803 | 1,082,477 | **3,664** |
| 把任一 widget 的間距做成響應式 | 11,800 | 1,082,477 | **264** |
| 反查哪個 control 驅動某個 CSS 屬性 | — | 1,082,477 | **363** |
| **合計** | **48,114** | **1,082,477** | **6,336** |

節省幅度曾經是 89.1%，後來反而**往下掉**了——因為這個表面變得誠實
（WooCommerce、Kit、selector、repeater 欄位），schema 從 583k 長到 1.08M
token，更完整的答案自然要花更多 token。只會愈變愈好看的數字都是被挑選過
的；這裡的數字由腳本重新產生，往哪邊走就照實寫哪邊。

讓這一切成立的是兩件事：資料**用查的，從不整份載入**；還有每個傳統 widget
共用的那 211 個 Advanced 分頁 control **只存一份，而不是存 168 份**。token
計數用的是 tiktoken `cl100k_base`——OpenAI 的 tokenizer，不是 Claude 的，
所以絕對值會有正負 10% 左右的出入；但同一個 tokenizer 之下的比值是穩定的，
而這裡的主張本來就是比值
（[token-efficiency.md](references/token-efficiency.md)）。

## Free 與 Pro 是量出來的，不是猜的

Elementor Pro 會**把 control 注入免費 widget**：裝了 Pro 的站上，免費的
Heading widget 也帶著 Motion Effects、Sticky、Custom CSS、Display
Conditions 和 Custom Attributes。要是直接繼承 widget 的 tier，這 46 個就全
被標成「free」——你蓋的頁面在自己站上渲染得完美無缺，搬到 Free 站上，樣式
就無聲無息地消失。

所以 tier 是量出來的：Pro 開著抽一次，再用
`wp --skip-plugins=elementor-pro` 抽一次（只影響那一個 CLI process，對
production 站是安全的），然後 diff。同一套方法再往前推一個軸，就是
WooCommerce——它不只是加 29 個 widget，還會把 `product_query_exclude*` 注
入 Pro 自己的 loop widget；只有拿一份關掉 WooCommerce 的 dump 來對照，才知
道那些 control 到底是誰的。第三方污染也用同一招排除：Rank Math 會注入
`accordion`，Unlimited Elements 會注入 container——帶著它們一起抽出來的
schema，就會把這些 control 冒充成 Elementor 自家的一併出貨。

tier 不要用推理的。**Border 和 Box Shadow 看起來很高級，其實是免費的；
`_attributes` 看起來很陽春，其實要 Pro。**這個 repo 就曾經因為用推理代替量
測，把 Border 錯標成 Pro 出貨過。還有一件事：Pro 沒開的時候，Elementor
core 會註冊一批**名字跟真正的 Pro widget 一模一樣的宣傳用 stub**——把無
Pro 的 dump 照單全收，26 個 Pro widget 就會被讀成免費。

## 它準嗎？讓它自己證明。

別信它——測它。八道檢查、八個不同的問題，分別從不同的產出物讀答案：
control 堆疊、編譯後的樣式表、送達的 HTML、真瀏覽器的 computed style、真實
的滑鼠事件、穿過 CDN 的公開網址。**驗證器只能發現它所讀的那條通道裡的
bug**——這八道檢查每一道都存在，是因為更寬鬆的檢查曾經漏掉真實的問題。

**1. schema 跟你的安裝一致嗎？**

```bash
python tools/verify-schema.py mine.json --free-dump mine-free.json
```

走訪每一組 (owner, control)，核對型別與 Free/Pro 聲明，而且——因為 schema
記錄了每個 widget 的需求——它分得出「schema 錯了」和「這個站只是沒裝
WooCommerce」是兩回事，不會兩邊都亂喊狼來了。對兩個抽取站都 PASS；一有漂移
就以非零值退出，所以可以直接拿來擋部署。

**2. 每個聲稱會輸出 CSS 的 control，真的有輸出嗎？**

每個 control 都拿到一個**專屬於它的值**（一個獨一無二的色碼、一個獨一無二
的像素值），相依鏈自動求解，然後在**公開網址實際送達的**樣式表裡驗證輸出
——不是伺服器磁碟上的某個檔案：

```
25,259 CSS-driving controls    99.4% covered, 0 failures
33,448 responsive suffixes     each asserted inside ITS media query, with a value
                               distinct from desktop's, so a leak cannot pass
```

Elementor 自己的中繼資料錯的地方，以渲染結果為準：有 9 個 control 聲稱支援
某個響應式斷點、實際上卻從來不輸出，schema 現在對它們標記 `rwd-BROKEN`。

**3. 每個聲稱會輸出 class 的 control，class 真的有掛上 wrapper 嗎？**

有 3,308 個 control 的作用方式是在 wrapper 附加一個 class，而不是輸出
CSS——樣式表檢查在結構上就注定一個也看不到。這一項改從送達的 HTML 讀：
99.8% 掃過、0 個失敗，連 `classes_dictionary` 的舊值重對映
（`position: "top"` 渲染成 `elementor-position-block-start`）和裝置前綴
（`elementor-tablet-position-`，不是 `_tablet` 後綴）都包含在內。

**4. 真瀏覽器算出來的，跟宣告的一致嗎？**

一條規則可以躺在樣式表裡，卻在瀏覽器那一關被蓋掉——輸給 specificity、輸給
cascade，或者 selector 根本沒選中任何節點。`sweep-browser.py` 把每一頁放進
Chromium 打開，拿 Elementor 的宣告去比 `getComputedStyle`——而且是比在**規
則實際作用的那個節點**上（`data/css-selectors.csv` 就是為此存在的）：

```
48,873 probes across two live sites with different themes
25 of 26 override patterns IDENTICAL on both -> facts about Elementor,
   led by: _element_width's max-width is dead on every widget inside a
   container, killed by Elementor's own frontend.css at specificity (0,4,0)
 1 of 26 site-specific -> a fact about that theme, named by the data
```

**5. 每個 widget 拿到內容之後，真的渲染得出來嗎？**

在每個內容 control 裡種入獨一無二的標記（repeater 項目按抽取到的欄位建
構），**一頁只放一個 widget**——這樣一旦出現 JS 錯誤或渲染出零尺寸，就能
明確歸咎到唯一的那個 widget——每個都截元素截圖，跑三種視窗寬度：

```
168/168 placeable widgets across the two sites
  126 rendered — marker echo, real site content, or hidden-by-design
   42 correctly empty without site context (cart/checkout/loop on a bare page)
    0 broken
```

**6. 互動型 widget 真的會動嗎？**

在公開頁面上用真實的滑鼠事件測：

```
nested-tabs        click tab 2  -> content 2 shows, content 1 hides    PASS
nested-accordion   click item 2 -> <details> opens                     PASS
accordion          click item 2 -> body becomes visible                PASS
toggle             click item 1 -> body toggles open                   PASS
image-carousel     click next   -> active slide advances               PASS
```

還有 `:hover` 規則——任何靜態讀取都驗不了的東西——用真實的游標去 hover：
3,882 個探測點、297 個以值驗證；113 個被蓋掉的全是同元素的種值衝突（兩個
hover control 刻意對同一個屬性寫不同的值——總有一個要被蓋），在 CSV 裡逐列
標註。過程會先關掉 transition，而且報告裡明講有這道人為介入：transition 被
刻意設成 79 秒，開跑 200 ms 就去讀顏色，讀到的只是動畫中途的一格，做不得
準。

**7. 完整的工作流程端到端撐得住嗎？**

下面每一項都是 headless 蓋出來，再到線上站台用瀏覽器驗證：

- **Global colors**：把一個顏色附加進 kit 的 `custom_colors`、用
  `__globals__` 引用，最後計算出來的正是那個顏色
- **Dynamic tags**：`post-title` 綁定送達頁面的就是文章真正的標題
- **Display conditions**：設了 `logged_in` 條件的元素，在未登入的 HTML 裡
  整個不存在——是伺服器端拿掉的，不是 CSS 藏起來的
- **Theme Builder**：限定單一頁面的 header 只在那一頁渲染，其他地方都沒有
- **Popups**：`page_load` 觸發的彈窗，在未登入的瀏覽器裡如期打開
- **Loop Builder**：loop-item 範本加上 loop-grid，渲染出三篇真實文章
- **Forms**：未登入填表 → nonce → 資料庫寫入一列 → 自訂成功訊息
- **Canvas**：`template: elementor_canvas` 把佈景主題的頁首頁尾整個拿掉
  （靠 `_wp_page_template`——光靠頁面設定搆不到那裡）
- **Templates**：用 Elementor 自己的 JSON 格式匯出／匯入，媒體由它自己的
  hook 重新下載、掛回媒體庫

**8. 一般訪客拿到的頁面，這一切都在嗎？**

```bash
python tools/verify-live.py page.json https://your-site/your-page/
```

抓下公開網址和該頁連結的**每一份樣式表**（一頁的樣式分散在好幾個檔案裡——
Kit 的全域樣式放在另一個檔案），穿過 edge cache，逐一斷言樹、CSS 值和
wrapper class。樹被動過手腳它就會失敗——一個從來沒紅過的驗證器，稱不上驗
證器。[examples/demo-page.json](examples/demo-page.json) 就是一頁完整用這種
方式蓋出來的頁面：實際發布上線、從沒在編輯器裡開過，在三種視窗寬度下都通過
這道檢查。

## 陷阱

天真的做法會錯，而且錯法還可以一條一條編號，**整整十一種**——每一種都曾經
在這個 repo 裡真實出貨過才被抓到，如今每一種都變成一道 canary、一條驗證規
則或一個資料欄位。完整的記錄在
[extraction-traps.md](references/extraction-traps.md)：

1. WP-CLI 拿到的是被削過的 control 堆疊——46% 的 control 無聲消失
2. 響應式是兩套機制；`padding_tablet` 沒有 control 物件，卻能用
3. control 的 tier 不等於它所屬 widget 的 tier——Pro 會注入免費 widget
4. control 有三種被 gate 的方式；661 個 control 死在一個空的插值上
5. 響應式相依會在斷點上重新檢查一次
6. `is_responsive` 說得太滿——只有渲染知道真相
7. CSS 只是 control 能做的事的一半——有 3,308 個改成輸出 class
8. class 的值會被重對映，而它的裝置前綴是另一個字串
9. 直接寫 `_elementor_data` 會留下過期的渲染 HTML 快取——樹是對的，端出來
   的卻是上一版頁面；一次 1.7 萬個 control 的掃描就這樣全綠跑完過
10. widget 表面是安裝環境的屬性，不是 Elementor 的
11. 規則可以躺在樣式表裡卻被蓋掉——只有瀏覽器看得出來

還有幾條記在各自所屬的文件裡：Canvas 的 `template` 設定存在
`_wp_page_template`，不在頁面設定；library 範本需要
`elementor_library_type` **分類法**和 conditions **快取**，缺一個 Theme
Builder 就永遠看不到它；`theme-*` 系列 widget 的動態綁定是編輯器在插入當下
賦予的，headless 寫的樹得自己把 `__dynamic__` 寫進去；WP 傳統橋接 widget 的
設定全部收在 `settings.wp` 底下；`e_display_conditions` 是一個包著 JSON
**字串**的陣列——文件一度示範過的裸陣列存得進去，然後被無聲忽略。

## 裡面有什麼

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

- **Elementor V4 atomic 元素**：只能查詢。要蓋它們是另一套資料模型，這個
  skill 還不會寫。
- **情境相依的 widget**（購物車、結帳、文章留言、商品頁的各個元件）在空白
  頁上的驗證結果是「正確地空白」；它們完整的行為需要商店或文章情境，掃描不
  會憑空捏造。
- **綁定版本**：這裡的每一個數字都是在 Elementor 4.1.4 / Pro 4.1.2 上量出來
  的。新版本可能讓其中任何一項失效——所以每個驗證器都隨附出貨，可以對你自
  己的安裝重新跑一遍。
- `page_load` 以外的彈窗觸發條件、save-to-database 以外的表單動作、第三方外
  掛的 widget：抽取都有涵蓋，但還沒做端到端驗證。

## 在你自己的安裝上重新產生資料

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

## 跨頁面、跨站台重複使用區塊

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json
wp --user=1 eval-file tools/import-template.php hero-block.json
```

絕對不要用複製 `_elementor_data` 的方式把區塊搬去另一個站：媒體 control 存
的是 attachment 的 **id**，同一個 id 在別的站上是另一張圖。這兩支工具走
Elementor 自己的匯入路徑，讓它的 `on_import` hook 重新下載媒體。另外，
`[elementor-template id="123"]` 可以把任何已儲存的範本嵌進任何 WordPress 內
容——包括不靠 Pro 也能把區塊一層層嵌進頁面，用的是免費的 shortcode
widget。

## 貢獻

拿新版 Elementor 重新抽取，連同重新產生的 `data/` 開 PR——
`verify-schema.py` 會告訴你到底哪裡變了。詳見
[CONTRIBUTING.md](CONTRIBUTING.md)。

## 授權

MIT。由 **moksa** 打造與維護 · [moksaweb.com](https://moksaweb.com)

姊妹 skill：[rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
