<div align="center">

# Elementor Headless

### 直接讀寫 JSON 與 meta 資料來建構、修改 Elementor 頁面，不需要視覺化編輯器。每一個 Pro 專屬功能都明確標示。

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
  <a href="#快速開始"><strong>快速開始</strong></a> ·
  <a href="https://github.com/Moksa1123/elementor-headless"><strong>GitHub</strong></a> ·
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

## 這是什麼

用 headless 的方式對待 Elementor：一個頁面就是一棵由容器和 widget 組成的
JSON 樹，每個 widget 是一組型別化欄位的 `settings` 物件。這個 skill 給 AI
Agent 完整、有查證的參數地圖——widget 控制項、樣式群組、響應式斷點、版型
條件、動態標籤——讓它能完全透過資料結構建構或改造頁面，不用打開視覺化
編輯器。

**不是**網站健檢或外掛稽核工具——這是刻意排除在範圍外的。這個 skill 談的
是「建構」，不是「診斷」。

## 涵蓋範圍

- **範本（Templates）**：Theme Builder 版型的建立/讀取/套用機制
  （`elementor_library` CRUD、`_elementor_template_type`）
- **顯示條件（Display Conditions）與進階條件（Advanced Conditions）**：
  完整列出 Include/Exclude 條件的類型與名稱（general／singular／archive
  三大類，以及 Elementor Pro 提供的每一種子條件），加上多個版型互相競爭
  時實際怎麼解決衝突（依精確度決定優先序，不是依註冊順序）
- **RWD**：各斷點的樣式參數——實測驗證過全部 Elementor 控制項裡有 20%
  帶有 `_tablet`/`_mobile` 響應式變體
- **客製化設定（Custom Settings）**：Border、Box Shadow、Typography、
  Background 背後共用的 Group Control 機制（Elementor 核心功能，免費），
  以及自訂 CSS 注入（貨真價實的 Pro 專屬，透過 hook 注入——從原始碼查證，
  不是用猜的）
- **Free vs Pro，查證不是用猜的**：每個 widget 跟功能的來源都對照
  `elementor` 跟 `elementor-pro` 外掛目錄本身，以及授權檢查程式碼——這個
  專案開發過程中真的把 Border/Box-Shadow 判斷錯（以為是 Pro，其實是
  Free），後來對照原始碼才修正；修正過程跟查證方法都寫進文件裡

## 快速開始

```bash
git clone https://github.com/Moksa1123/elementor-headless.git
cd elementor-headless
python tools/install-skill.py --list                 # 查看支援哪些平台
python tools/install-skill.py claude-code             # 安裝到目前專案
python tools/install-skill.py claude-code --global    # 安裝成全域（所有專案都可用）
```

完整內容看 `SKILL.md`，資料模型細節在 `references/` 裡。

## 目錄結構

```
elementor-headless/
├── SKILL.md                        # Skill 主契約——AI 助理會自動載入
├── README.md                       # 本檔（＋ zh-TW／ja／ko 翻譯）
├── CLAUDE.md                       # AI 開發慣例＋Free/Pro 規則＋去敏感化規則
├── LICENSE                         # MIT
├── references/
│   ├── elementor-widgets-and-containers.md   # 容器/widget/動態標籤資料模型，實測驗證
│   ├── elementor-style-system.md             # Group Control 機制、自訂 CSS、Free/Pro 查證方法
│   ├── elementor-templates-and-conditions.md # 版型 CRUD、完整顯示/進階條件系統
│   ├── elementor-safe-edit.md                # 共用版型編輯流程、JSON path 導覽紀律
│   ├── dynamic-ghost-text-pattern.md         # 寫死內容改成依文章動態產生的完整案例
│   ├── wp-cli-safe-scripting.md              # 引號逃逸與檔案化執行的紀律
│   └── multiplatform-install-verification.md # 各平台安裝慣例的查證日期記錄
├── tools/
│   ├── extract-elementor-controls.php # 透過 `wp eval-file` 執行——在你自己的網站重新撈取控制項資料
│   ├── ghost-glint-svg.py             # 獨立工具——預覽/調整幽靈字 SVG 的比例
│   └── install-skill.py               # 多平台安裝器
├── data/
│   ├── platform-conventions.csv          # 各平台安裝路徑與查證日期
│   └── elementor-core-pro-controls.json  # 135 個 widget 的完整控制項結構，撈自實際安裝
└── assets/templates/platforms/*.json  # 各平台的安裝設定檔
```

## 有查證，不是憑猜的

- **164 個 widget、48,238 個控制項**，從實際安裝的 Elementor + Elementor
  Pro 撈出——不是用訓練資料寫的。
- **9 個「進階」分頁區塊，98% 的 widget 都通用**，每一個都有完整真實控制
  項清單。
- **每一種顯示/進階條件類型**，直接從 Elementor Pro 的 `Condition_Base`
  子類別列舉出來，含精確度優先序的衝突解決邏輯。
- **Free vs Pro 的界線對照原始碼查證**（外掛目錄＋授權檢查程式碼），不是
  憑功能看起來多進階去推測。
- **多平台安裝慣例**都標了查證日期並且獨立重新驗證過——8 個支援平台裡
  有 3 個，在跟姊妹 skill 自己的舊表格相隔約 6 週的時間裡就已經跟不上了
  （詳見 `multiplatform-install-verification.md`）。

## 貢獻

看 `CONTRIBUTING.md`。這個專案的去敏感化規則比一般 repo 更重要——送 PR
前先讀過 `CLAUDE.md` 的「去敏感化規則」章節。

## 作者

由 **moksa** 於 [moksaweb.com](https://moksaweb.com) 開發維護。MIT 授權。
