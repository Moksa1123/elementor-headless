<div align="center">

# WP Elementor Ops

### 安全稽核與編輯 WordPress + Elementor 網站的技能。真實踩過的坑，連同修法一起附上。

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
  <a href="#快速開始"><strong>快速開始</strong></a> ·
  <a href="https://github.com/Moksa1123/wp-elementor-ops"><strong>GitHub</strong></a> ·
  <a href="https://github.com/Moksa1123/rankmath-seo-wp"><strong>姊妹專案</strong></a> ·
  <a href="https://moksaweb.com"><strong>moksaweb.com</strong></a>
</p>

<p>
  <a href="README.md">English</a> ·
  <strong>繁體中文</strong> ·
  <a href="README.ja.md">日本語</a> ·
  <a href="README.ko.md">한국어</a>
</p>

</div>

---

## 這個 skill 用在哪裡

- **「幫我健檢這個 WordPress 網站」／「哪些外掛可以刪？」**——先找出外掛真正的
  block/shortcode/option 簽章再去搜尋（用外掛 slug 用猜的，是這個 skill 最想
  避免的第一號錯誤），比對真實用量，並防範「孤兒媒體」的誤判陷阱。
- **「幫我改這個共用的 Elementor 版型」**——正確導覽 `_elementor_data` 的 JSON
  結構不會少算一層、需要因文章而異的內容時改用動態 shortcode 而不是寫死內容、
  快取要按正確順序分層清除。
- **「這個 Elementor 元件到底有哪些設定？」**——一份從實際安裝的 Elementor +
  Elementor Pro 撈出來的真實資料（164 個 widget、48,238 個控制項，實測不是
  用猜的），加上 98% 的 widget 都共用的「進階」分頁區塊完整記錄。
- **「我改完怎麼沒有生效？」**——真實事故整理出的快取層級與截圖縮放/壓縮除錯筆記。

## 快速開始

```bash
git clone https://github.com/Moksa1123/wp-elementor-ops.git
cd wp-elementor-ops
python tools/install-skill.py --list                 # 查看支援哪些平台
python tools/install-skill.py claude-code             # 安裝到目前專案
python tools/install-skill.py claude-code --global    # 安裝成全域（所有專案都可用）
```

完整內容看 `SKILL.md`，方法論細節在 `references/` 裡。

## 目錄結構

```
wp-elementor-ops/
├── SKILL.md                        # Skill 主契約——AI 助理會自動載入
├── README.md                       # 本檔（＋ zh-TW／ja／ko 翻譯）
├── CLAUDE.md                       # AI 開發慣例與去敏感化規則
├── LICENSE                         # MIT
├── references/
│   ├── plugin-audit-methodology.md         # 判斷用量前要先找到「真正的」簽章
│   ├── elementor-safe-edit.md              # 共用版型的安全編輯流程
│   ├── elementor-widgets-and-containers.md # 容器/widget/動態標籤資料模型，實測驗證
│   ├── dynamic-ghost-text-pattern.md       # 寫死內容改成依文章動態產生的完整案例
│   ├── wp-cli-safe-scripting.md            # 引號逃逸與檔案化執行的紀律
│   └── multiplatform-install-verification.md # 各平台安裝慣例的查證日期記錄
├── tools/
│   ├── audit-plugin-usage.php         # 透過 `wp eval-file` 執行——比對真實用量
│   ├── audit-orphan-media.php         # 透過 `wp eval-file` 執行——孤兒媒體偵測（含誤判防護）
│   ├── extract-elementor-controls.php # 透過 `wp eval-file` 執行——在你自己的網站重新撈取控制項資料
│   ├── ghost-glint-svg.py             # 獨立工具——預覽/調整幽靈字 SVG 的比例
│   └── install-skill.py               # 多平台安裝器
├── data/
│   ├── platform-conventions.csv          # 各平台安裝路徑與查證日期
│   └── elementor-core-pro-controls.json  # 135 個 widget 的完整控制項結構，撈自實際安裝
└── assets/templates/platforms/*.json  # 各平台的安裝設定檔
```

## 為什麼會有這個專案

源自一個正式營運的 WooCommerce + Elementor Pro 網站的真實除錯過程：一支外掛
因為用猜的 block 名稱搜尋不到結果而被停用，但它真正的名稱（作者自己的
namespace）其實正在 10 篇上線文章裡使用中。一個共用的 Elementor 版型，裝飾用
的文字被寫死成每篇文章都顯示一樣的內容。一次「孤兒媒體」清查差點誤刪透過
ACF 圖片欄位真的有被引用的檔案，起因是先前把不相關的瀏覽次數計數器誤認成
真實引用。這裡的每一份參考文件都能追溯回其中一次真實事故——包括第一次做錯
的部分，也包括這個專案自己的稽核工具在開發過程中發現的真實 bug（`wp eval-file`
不支援 Unix CLI 那種 `--` 分隔符或 `--flag=value` 語法）。

## 有查證，不是憑猜的

這個 repo 裡有兩件事，存在的理由就是「感覺對」不夠：

- **Elementor 的資料模型**（`elementor-widgets-and-containers.md`、
  `data/elementor-core-pro-controls.json`）是實際查詢一個真實安裝的 widget
  註冊清單撈出來的，不是憑訓練資料或記憶寫的。查證過程中真的有撈不到的部分
  （Border／Box-Shadow／自訂 CSS，這些是 Elementor Pro 透過 hook 動態注入的，
  單純呼叫 `get_controls()` 不會觸發），這個缺口就老實寫成缺口，沒有硬掰。
- **多平台安裝慣例**（`multiplatform-install-verification.md`）都標了查證日期
  並且獨立重新驗證過——8 個支援平台裡有 3 個，在跟姊妹專案自己的舊表格相隔約
  6 週的時間裡，設定就已經跟不上了。

## 貢獻

看 `CONTRIBUTING.md`。這個專案的去敏感化規則比一般 repo 更重要——PR 如果包含
從真實網站衍生出來的任何內容，先讀過 `CLAUDE.md` 的「去敏感化規則」章節。

## 作者

由 **moksa** 於 [moksaweb.com](https://moksaweb.com) 開發維護。MIT 授權。
