<div align="center">

# WP Elementor Ops

### WordPress + Elementor サイトを安全に監査・編集するスキル。実際の本番環境で起きたミスと、その修正法を組み込み済み。

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
  <a href="#クイックスタート"><strong>はじめる</strong></a> ·
  <a href="https://github.com/Moksa1123/wp-elementor-ops"><strong>GitHub</strong></a> ·
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

## こんなときに使う

- **「このWordPressサイトをヘルスチェックして」「不要なプラグインはどれ？」**
  ——推測ではなく、プラグインの*本物の*ブロック名・ショートコードタグ・
  オプションキーをまず突き止める（スラッグからの推測こそ、このスキルが
  最も防ぎたいミスその1）。実際の使用箇所を照合し、「孤立メディア」の
  誤検知トラップを回避する。
- **「共有Elementorテンプレートを編集したい」**——`_elementor_data` の JSON
  構造をオフバイワンなしで辿り、投稿ごとに変える必要がある内容は静的な
  ウィジェットではなく動的ショートコードに変換し、キャッシュを正しいレイヤー
  順でフラッシュする。
- **「このElementorウィジェットにはどんな設定があるの？」**——実際に稼働中の
  Elementor + Elementor Pro から抽出したデータ（164ウィジェット、48,238個の
  コントロール、推測ではなく実測）と、全ウィジェットの98%に共通する
  「Advancedタブ」セクションの完全な記録。
- **「変更したのに反映されない」**——実際のインシデントから得たキャッシュ
  レイヤーと、圧縮/スクリーンショット縮小に関するデバッグの注意点。

## クイックスタート

```bash
git clone https://github.com/Moksa1123/wp-elementor-ops.git
cd wp-elementor-ops
python tools/install-skill.py --list                 # 対応プラットフォーム一覧
python tools/install-skill.py claude-code             # このプロジェクトにインストール
python tools/install-skill.py claude-code --global    # 全プロジェクト共通としてインストール
```

契約の全文は `SKILL.md`、背景にある手法は `references/` を参照。

## リポジトリ構成

```
wp-elementor-ops/
├── SKILL.md                        # スキル契約——AIアシスタントが自動読込
├── README.md                       # 本ファイル（+ zh-TW／ja／ko 翻訳）
├── CLAUDE.md                       # AI開発規約とサニタイズ規則
├── LICENSE                         # MIT
├── references/
│   ├── plugin-audit-methodology.md         # 使用判定の前に「本物の」シグネチャを見つける
│   ├── elementor-safe-edit.md              # 共有テンプレートの安全な編集手順
│   ├── elementor-widgets-and-containers.md # コンテナ/ウィジェット/動的タグのデータモデル、実測検証済み
│   ├── dynamic-ghost-text-pattern.md       # 静的→投稿ごとの動的コンテンツへの変換実例
│   ├── wp-cli-safe-scripting.md            # クォート/エスケープ/ファイル実行の規律
│   └── multiplatform-install-verification.md # プラットフォームごとのインストール規約と検証日
├── tools/
│   ├── audit-plugin-usage.php         # `wp eval-file` で実行——実際の使用状況を照合
│   ├── audit-orphan-media.php         # `wp eval-file` で実行——誤検知防止付き孤立メディア検出
│   ├── extract-elementor-controls.php # `wp eval-file` で実行——自サイトでコントロールデータを再抽出
│   ├── ghost-glint-svg.py             # スタンドアロン——ゴーストテキストSVGの比率をプレビュー/調整
│   └── install-skill.py               # マルチプラットフォームインストーラー
├── data/
│   ├── platform-conventions.csv          # プラットフォームごとのインストールパスと検証日
│   └── elementor-core-pro-controls.json  # 135ウィジェット分の完全なコントロールスキーマ（実稼働環境から抽出）
└── assets/templates/platforms/*.json  # プラットフォームごとのインストール設定
```

## なぜこのプロジェクトが存在するのか

本番稼働中のWooCommerce + Elementor Proサイトでの実際のデバッグから生まれた:
あるプラグインは、*推測した*ブロック名で検索して何もヒットしなかったために
無効化されたが、*本物の*名前（作者独自のネームスペース）は実際に10件の公開
記事で使われていた。共有Elementorテンプレートの装飾テキストは、それを使う
すべての投稿で同一の内容にハードコードされていた。「孤立メディア」の一斉
チェックは、ACF画像フィールド経由で実際に参照されていたファイルを、無関係な
閲覧数カウンターのメタデータを実際の参照と誤認したことで、危うく誤検知する
ところだった。ここにあるリファレンスはすべて、そうした実際の出来事の一つに
遡れる——最初に間違えた部分も含めて、そしてこのプロジェクト自身の監査ツールが
開発中に見つけた本物のバグ（`wp eval-file` はUnix CLIのような `--` 区切りや
`--flag=value` 構文をサポートしていない）も含めて。

## 推測ではなく、検証済み

このリポジトリには「たぶん合ってる」では不十分だという理由だけで存在する
ものが2つある:

- **Elementorのデータモデル**（`elementor-widgets-and-containers.md`、
  `data/elementor-core-pro-controls.json`）は、実際に稼働中のインストール
  のウィジェット登録情報を問い合わせて抽出したものであり、学習データや
  記憶から書いたものではない。実際の抽出で本物のギャップが見つかった箇所
  （Border/Box-Shadow/Custom CSSは、単純な `get_controls()` 呼び出しでは
  発火しないフックを通じてElementor Proが注入するもの）は、そのままギャップ
  として明記している。
- **マルチプラットフォームのインストール規約**（`multiplatform-install-verification.md`）
  には検証日が記載され、独立に再確認されている——対応8プラットフォームの
  うち3つは、姉妹スキル自身の表が書かれてからわずか約6週間の間にすでに
  変わっていた。

## コントリビュート

`CONTRIBUTING.md` を参照。このプロジェクトではサニタイズが他のリポジトリ
以上に重要——実サイトから派生した内容を含むPRを送る前に、`CLAUDE.md` の
「サニタイズ規則」セクションを読むこと。

## 作者

**moksa**（[moksaweb.com](https://moksaweb.com)）が開発・保守。MITライセンス。
