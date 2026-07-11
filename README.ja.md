<div align="center">

# Elementor Headless

### JSON とメタデータを直接読み書きしてElementorページを構築・変更する。ビジュアルエディタ不要。Pro限定機能はすべて明示的にラベル付け。

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
  <a href="#クイックスタート"><strong>はじめる</strong></a> ·
  <a href="https://github.com/Moksa1123/elementor-headless"><strong>GitHub</strong></a> ·
  <a href="https://github.com/Moksa1123/rankmath-seo-wp"><strong>姉妹プロジェクト</strong></a> ·
  <a href="https://moksaweb.com"><strong>moksaweb.com</strong></a>
</p>

<p>
  <a href="README.md">English</a> ·
  <a href="README.zh-TW.md">繁體中文</a> ·
  <strong>日本語</strong> ·
  <a href="README.ko.md">한국어</a>
</p>

</div>

---

## これは何か

Elementorをヘッドレスに扱うアプローチ: ページはコンテナとウィジェットから
成るJSONツリーであり、各ウィジェットは型付けされたフィールドの `settings`
オブジェクトです。このスキルはAIエージェントに、実際に検証済みの
パラメータ全体像——ウィジェットコントロール、スタイルグループ、
レスポンシブブレークポイント、テンプレート条件、動的タグ——を提供し、
ビジュアルエディタを一切開かずにデータだけでページを構築・再構成できる
ようにします。

サイトのヘルスチェックやプラグイン監査ツール**ではありません**——それは
明確にスコープ外です。これは「診断」ではなく「構築」についてのスキルです。

## カバー範囲

- **テンプレート**: Theme Builderテンプレートの作成/読み込み/適用
  （`elementor_library` のCRUD、`_elementor_template_type`）
- **表示条件（Display Conditions）と高度な条件（Advanced Conditions）**:
  Include/Exclude 条件のタイプ・名前を完全網羅（general／singular／
  archive の3大分類と、Elementor Proが提供するすべてのサブ条件）。加えて、
  競合する複数テンプレート間の実際の解決方法（登録順ではなく、
  具体性に基づく優先度）
- **RWD**: ブレークポイントごとのスタイルパラメータ——全Elementor
  コントロールの20%が `_tablet`/`_mobile` レスポンシブバリアントを
  持つことを実測で確認済み
- **カスタム設定**: Border、Box Shadow、Typography、Backgroundの背後にある
  共通の Group Control メカニズム（コア Elementor、無料）と、
  Custom CSS注入（本物のPro限定機能、フックで注入——推測ではなくソースから
  検証済み）
- **Free vs Pro、推測ではなく検証済み**: すべてのウィジェットと機能の
  出所を、実際の `elementor` vs `elementor-pro` プラグインディレクトリと
  ライセンスゲートのコードと照合。このプロジェクトは開発中に一度
  Border/Box-Shadowの判定を誤り（Pro限定だと思い込んだが実際はFree）、
  ソースコードと照合して修正した経緯がある——その修正過程と検証方法の
  両方をドキュメント化している

## クイックスタート

```bash
git clone https://github.com/Moksa1123/elementor-headless.git
cd elementor-headless
python tools/install-skill.py --list                 # 対応プラットフォーム一覧
python tools/install-skill.py claude-code             # このプロジェクトにインストール
python tools/install-skill.py claude-code --global    # 全プロジェクト共通としてインストール
```

契約の全文は `SKILL.md`、データモデルの詳細は `references/` を参照。

## リポジトリ構成

```
elementor-headless/
├── SKILL.md                        # スキル契約——AIアシスタントが自動読込
├── README.md                       # 本ファイル（+ zh-TW／ja／ko 翻訳）
├── CLAUDE.md                       # AI開発規約 + Free/Pro規則 + サニタイズ規則
├── LICENSE                         # MIT
├── references/
│   ├── elementor-widgets-and-containers.md   # コンテナ/ウィジェット/動的タグのデータモデル、実測検証済み
│   ├── elementor-style-system.md             # Group Control機構、Custom CSS、Free/Pro検証方法
│   ├── elementor-templates-and-conditions.md # テンプレートCRUD、完全な表示/高度な条件
│   ├── elementor-safe-edit.md                # 共有テンプレート編集手順、JSONパス規律
│   ├── dynamic-ghost-text-pattern.md         # 静的→投稿ごとの動的コンテンツへの変換実例
│   ├── wp-cli-safe-scripting.md              # クォート/エスケープ/ファイル実行の規律
│   └── multiplatform-install-verification.md # プラットフォームごとのインストール規約と検証日
├── tools/
│   ├── extract-elementor-controls.php # `wp eval-file` で実行——自サイトでコントロールデータを再抽出
│   ├── ghost-glint-svg.py             # スタンドアロン——ゴーストテキストSVGの比率をプレビュー/調整
│   └── install-skill.py               # マルチプラットフォームインストーラー
├── data/
│   ├── platform-conventions.csv          # プラットフォームごとのインストールパスと検証日
│   └── elementor-core-pro-controls.json  # 135ウィジェット分の完全なコントロールスキーマ（実稼働環境から抽出）
└── assets/templates/platforms/*.json  # プラットフォームごとのインストール設定
```

## 推測ではなく、検証済み

- **164ウィジェット、48,238コントロール** を実際に稼働中のElementor +
  Elementor Proから抽出——学習データから書いたものではない。
- **全ウィジェットの98%に共通する9つの「Advanced」タブセクション**、
  それぞれの完全な実際のコントロールリスト。
- **すべての表示/高度な条件タイプ** を Elementor Pro の
  `Condition_Base` サブクラスから直接列挙、複数テンプレートが競合した
  場合の具体性ベースの優先度解決ロジックも含む。
- **Free vs Pro の境界線はソースコードと照合して検証**（プラグイン
  ディレクトリ + ライセンスゲートのコード）——機能がどれだけ高度に
  見えるかで推測したものではない。
- **マルチプラットフォームのインストール規約** には検証日が記載され、
  独立に再確認されている——対応8プラットフォームのうち3つは、姉妹
  スキル自身の表が書かれてからわずか約6週間の間にすでに変わっていた
  （詳細は `multiplatform-install-verification.md`）。

## コントリビュート

`CONTRIBUTING.md` を参照。このプロジェクトではサニタイズが他のリポジトリ
以上に重要——PRを送る前に `CLAUDE.md` の「サニタイズ規則」セクションを
読むこと。

## 作者

**moksa**（[moksaweb.com](https://moksaweb.com)）が開発・保守。MITライセンス。
