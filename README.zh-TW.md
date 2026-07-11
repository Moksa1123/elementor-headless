# elementor-headless

**直接把 JSON 寫出來建 Elementor 頁面，而不是去操作編輯器。**

這是一個 [Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)，
把 Elementor 完整的編輯面貌——**橫跨 135 個 widget 與 3 個元素、總共 37,964 個控制項**——
交到 AI coding agent 手上，而且是以一個可查詢的資料庫的形式，
而不是一份 583,555 token、它永遠讀不起的文件。

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

**比讀 Elementor 原始碼少 89.1% 的 token。比載入整份 schema 少 99.1%。**
自己重現一次——腳本會寫出 `data/token-benchmark.csv`：

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| 任務 | 讀原始碼 | 載入 schema | **查詢** |
|---|---|---|---|
| 排一個 hero 容器（flex、boxed、響應式 padding） | 20,182 | 583,555 | **964** |
| 設定標題樣式（顏色、字體排印、對齊） | 8,329 | 583,555 | **730** |
| 設定按鈕樣式（顏色、padding、圓角、hover） | 7,803 | 583,555 | **2,935** |
| 讓任一 widget 的間距變成響應式 | 11,800 | 583,555 | **243** |
| 找出是哪個控制項在驅動某個 CSS 屬性 | — | 583,555 | **363** |
| **總計** | **48,114** | **583,555** | **5,235** |

有兩件事讓它成立：資料是**用查的，從來不整份載入**；還有每個 widget 共用的那 211 個
Advanced 分頁控制項是**只存一次，而不是存 135 次**——它們佔了全部資料列的 75.6%，
把它們抽出來共用，schema 就縮小了 73.2%。

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
去測試它。三個驗證器，回答三個不同的問題。

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
controls asserted     16,778
  verified by value   15,508  (92.4%)   the exact value we wrote is in the CSS
  property only        1,270  ( 7.6%)   right property, value not literally assertable
  FAILED                   0  ( 0.0%)
```

逐一控制項的結果隨附在 `data/control-verification.csv`。

**4. 自己去看。** `examples/demo-page.json` 是一個真實已發布的頁面，
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
  elementor-schema.json    2.7 MB   完整的編輯面貌 - 用查的，從不整份載入
  controls.csv             2.0 MB   每個 widget／元素專屬的控制項
  common-controls.csv       39 KB   每個 widget 共用的那 211 個
  pro-only-controls.csv     33 KB   安全表
  pro-only-widgets.csv     3.0 KB
  control-types.csv        4.6 KB   全部 59 種 JSON 值形狀
  group-controls.csv       3.7 KB   16 個群組，以及它們展開成的扁平 key
  widgets.csv              8.2 KB   135 個 widget + 3 個元素
  breakpoints.csv          0.2 KB
  control-verification.csv          逐一控制項：它真的算繪得出來嗎？
  token-benchmark.csv               可重現的測量結果

tools/
  el.py                          查詢 schema - 主要入口
  validate-page.py               對頁面樹做飛行前檢查
  apply-page.php                 寫進去：meta + 重建 CSS + 備份
  extract-elementor-schema.php   dump 一個運行中的安裝
  build-indexes.py               dump -> 出貨用的資料檔
  verify-schema.py               這份 schema 跟你的安裝相符嗎？
  verify-render.py               Elementor 吐出來的真的是 schema 承諾的嗎？
  sweep-controls.py              算繪「每一個」控制項，並斷言它真的有效
  export-template.php            匯出成 Elementor 自己的 JSON 格式
  import-template.php            匯入一份，連同媒體，走 Elementor 自己的路徑
  benchmark-tokens.py            重現那些 token 數字
  install-skill.py               8 平台安裝器

references/   data-model · control-types · containers-and-layout · responsive
              templates-and-conditions · import-export · extraction-traps
              token-efficiency
examples/     demo-page.json - 上面那個已發布的頁面
```

## 四個陷阱

用最直覺的方式去抽這些資料，會在四個各自獨立的地方出錯，每一種都會產出一份
看起來很完整、實際上在說謊的 schema。這四個在被抓到之前，全都在這個 repo 裡出貨過。
詳細記錄寫在 [extraction-traps.md](references/extraction-traps.md)：

1. **對 Elementor 來說，WP-CLI 看起來像前台**，所以它回傳的是精簡版的控制項堆疊：
   **46% 的控制項和大約 100% 的分頁／標籤 metadata 就這樣消失了**，而且沒有任何錯誤。
   抽取器停掉了那條路徑，而且放了兩隻金絲雀——寧可中止，也不吐出殘缺的資料。
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
   你就什麼都拿不到，而且是無聲的。這一個是把全部 16,778 個控制項都算繪出來、
   再真的去看，才浮現出來的。

## 參與貢獻

拿更新版的 Elementor 重新抽取一次，然後帶著重新產生的 `data/` 開一個 PR——
`verify-schema.py` 會明確告訴你有哪些東西變了。請看
[CONTRIBUTING.md](CONTRIBUTING.md)。

## 授權

MIT。由 **moksa** 打造並維護 · [moksaweb.com](https://moksaweb.com)

姊妹 skill：[rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
