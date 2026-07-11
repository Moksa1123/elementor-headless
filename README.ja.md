# elementor-headless

**エディタを操作するのではなく、JSON を書いて Elementor ページを構築する。**

AI コーディングエージェントに Elementor のオーサリング面すべて —
**135 ウィジェットと 3 エレメントにまたがる 37,964 コントロール** — を、
到底読み切れない 583,555 トークンのドキュメントとしてではなく、
クエリ可能なデータベースとして渡す
[Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview) です。

[English](README.md) · [繁體中文](README.zh-TW.md) · 日本語 · [한국어](README.ko.md)

---

## なぜ

Elementor はページを post meta 内の JSON ツリーとして保存します。ツリーを書けば、ページは存在します。
しかし Elementor は **書いた内容を検証しません**。値をそのまま保存し、理解できるものだけをレンダリングし、
残りは黙って捨てます。

エラーは出ません。スペルを間違えたコントロール、オブジェクトが入るべき場所の文字列、Free サイト上の
Pro 専用コントロール。どれも問題なく保存され、手元のマシンではきれいに描画され、そして肝心なところで
静かに何もしません。

つまり Elementor ページを構築するエージェントの選択肢は 2 つです。毎回 Elementor の PHP ソースを読む
（高コスト — しかもそれでも JSON の形は分からない）か、推測する（黙って間違える）か。このスキルは
3 つめの選択肢です。

```bash
$ python tools/el.py type slider
control type: slider   [FREE]  (elementor-core)

JSON value shape (what you write into _elementor_data settings):
  {"unit": "px", "size": "", "sizes": []}
```

## 仕組み

![architecture](assets/diagrams/architecture.svg)

3 つのフェーズ。抽出は Elementor のバージョンごとに 1 回、**あなたの**サイトに対して実行します。
それ以降はすべてクエリです。

## インストール

```bash
git clone https://github.com/Moksa1123/elementor-headless
cd elementor-headless
python tools/install-skill.py claude-code --global     # or: cursor, codex-cli, gemini-cli, ...
python tools/install-skill.py --list
```

8 プラットフォーム対応: Claude Code、Claude.ai、Cursor、Codex CLI、Gemini CLI、Devin
（旧 Windsurf）、GitHub Copilot、Continue。規約は 2026-07-11 に再検証済み —
[8 つのうち 3 つが 6 週間でずれていた](references/multiplatform-install-verification.md)ので、
仮定せず実際に確認しています。

## 使い方

```bash
python tools/el.py widgets --tier free --grep box   # find a widget
python tools/el.py widget heading --tab style       # its style controls
python tools/el.py container --tab layout           # flex + grid, with conditions
python tools/el.py css border-radius                # reverse lookup by CSS property
python tools/el.py group typography                 # what a group control expands into
python tools/el.py breakpoints                      # the responsive suffixes
python tools/el.py pro --check custom_css align     # exits 1 if any of these needs Pro
```

そして構築し、チェックし、出荷する。

```bash
python tools/el.py skeleton > page.json
python tools/validate-page.py page.json --target free
wp eval-file tools/apply-page.php 123 page.json
```

`validate-page.py` は Elementor が捕まえないものを捕まえます。未知のコントロール名、誤った値の形、
不正な単位、無効なオプション、重複した id、満たされていない条件、そして Free ターゲット上の
Pro 専用コントロール。

## トークンコスト

**Elementor のソースを読む場合よりトークン 89.1% 削減。スキーマを読み込む場合より 99.1% 削減。**
再現できます — スクリプトが `data/token-benchmark.csv` を書き出します。

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| タスク | ソースを読む | スキーマを読み込む | **クエリ** |
|---|---|---|---|
| ヒーローコンテナのレイアウト（flex、boxed、レスポンシブな padding） | 20,182 | 583,555 | **964** |
| 見出しのスタイリング（色、タイポグラフィ、配置） | 8,329 | 583,555 | **730** |
| ボタンのスタイリング（色、padding、radius、hover） | 7,803 | 583,555 | **2,935** |
| 任意のウィジェットの余白をレスポンシブにする | 11,800 | 583,555 | **243** |
| ある CSS プロパティを制御しているコントロールを探す | — | 583,555 | **363** |
| **合計** | **48,114** | **583,555** | **5,235** |

効く理由は 2 つあります。データは**クエリするだけで、決して読み込まない**こと。そして、すべての
ウィジェットが共有する 211 個の Advanced タブのコントロールを、**135 回ではなく 1 回だけ格納**して
いること。これらは全行の 75.6% を占めるため、括り出すだけでスキーマは 73.2% 縮みます。

計測は tiktoken の `cl100k_base` によるもの — Claude ではなく OpenAI のトークナイザーなので、
絶対値はおおよそ ±10% ずれます。同一トークナイザー下での 2 つのテキスト間の比率は安定しており、
主張しているのはその比率です。手法と留意点は
[token-efficiency.md](references/token-efficiency.md) に。

## Free と Pro は推測ではなく計測

Elementor Pro は**無料ウィジェットにコントロールを注入します**。Pro が入ったサイトで無料の Heading
ウィジェットを開けば、Advanced タブに Motion Effects、Sticky、Custom CSS、Display Conditions、
Custom Attributes が並んでいます。ウィジェットのティアをそのまま継承すると、これらすべてが「free」と
ラベル付けされ — そうして作ったページは自分の環境では完璧に描画され、Free 環境ではスタイルを失います。

だからティアは計測します。2 回抽出し — 1 回は Pro を読み込んだ状態、もう 1 回は
`wp --skip-plugins=elementor-pro`（影響するのはその CLI プロセスだけで、プラグインが無効化される
わけではないため本番環境でも安全）で — 差分を取ります。

| | Free 4.1.4 | + Pro 4.1.2 |
|---|---|---|
| ウィジェット | 64 | **135** |
| すべてのウィジェットに載るコントロール | 165 | **211** (+46) |
| `container` のコントロール | 277 | **356** (+79) |
| コントロールタイプ | 52 | **59** |
| グループコントロール | 11 | **16** |

Pro が**すべての**ウィジェットに注入する 46 個: すべての `motion_fx_*`（37）、`sticky*`（6）、
`custom_css`、`_attributes`、`e_display_conditions`。

ティアを推論で決めないでください。**Border と Box Shadow は高機能に見えますが無料です。
`_attributes` は基本的に見えますが Pro です。** このリポジトリも一度、計測せず推論した結果、
Border を Pro と誤ってラベル付けしたまま出荷しました。

## 本当に正確なのか。証明させてください。

スキーマは Elementor 4.1.4 / Pro 4.1.2 から取得したものです。あなたの環境は違うかもしれません。
信用せず、テストしてください。検証ツールは 2 つ、問いも 2 つです。

**1. スキーマはあなたのインストールと一致するか。**

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

ずれがあれば非ゼロで終了するので、デプロイのゲートに使えます。

**2. スキーマから構築したページは、スキーマが約束した CSS を実際にレンダリングするか。**

スキーマは、各コントロールがどの CSS プロパティを制御するかを示します。これはページを実際に構築し、
Elementor がコンパイルしたスタイルシートを読み戻して、そのすべてを検証します — 各レスポンシブキーが
*そのブレークポイントの*メディアクエリの中に入っているかどうかまで含めて。

```bash
python tools/verify-render.py examples/demo-page.json rendered.css --post-id 9176
```

```
CSS property assertions: 94/94 passed
PASS
```

**3. 実物を見る。** `examples/demo-page.json` は、このスキルだけで構築された実在の公開ページです。
Elementor エディタは一度も開かれていません。

**https://moksaweb.com/elementor-headless-demo/**

## 同梱物

```
data/
  elementor-schema.json    2.7 MB   オーサリング面の全体 - クエリするもので、読み込むものではない
  controls.csv             2.0 MB   ウィジェット/エレメント固有のコントロール全件
  common-controls.csv       39 KB   全ウィジェットが共有する 211 個
  pro-only-controls.csv     33 KB   安全確認用テーブル
  pro-only-widgets.csv     3.0 KB
  control-types.csv        4.6 KB   59 種類すべての JSON 値の形
  group-controls.csv       3.7 KB   16 グループと、それが展開されるフラットキー
  widgets.csv              8.2 KB   135 ウィジェット + 3 エレメント
  breakpoints.csv          0.2 KB
  token-benchmark.csv               再現可能な計測結果

tools/
  el.py                          スキーマにクエリする - 正面入口
  validate-page.py               ページツリーの事前チェック
  apply-page.php                 書き込む: meta + CSS 再構築 + バックアップ
  extract-elementor-schema.php   稼働中のインストールをダンプする
  build-indexes.py               ダンプ -> 同梱データファイル
  verify-schema.py               スキーマはあなたのインストールと一致するか?
  verify-render.py               Elementor はスキーマが約束したものを出力するか?
  benchmark-tokens.py            トークン数値を再現する
  install-skill.py               8 プラットフォーム対応インストーラ

references/   data-model · control-types · containers-and-layout · responsive
              templates-and-conditions · extraction-traps · token-efficiency
examples/     demo-page.json - 上記の公開ページ
```

## 3 つの罠

このデータを素朴に抽出すると、3 つの別々のかたちで間違えます。どれも、完全に見えて嘘をついている
スキーマを生みます。3 つとも、発覚する前にこのリポジトリで実際に出荷されました。詳細は
[extraction-traps.md](references/extraction-traps.md) に。

1. **WP-CLI は Elementor からはフロントエンドに見える**ため、痩せたコントロールスタックが返ってきます。
   **コントロールの 46%、そしてタブ/ラベルのメタデータのほぼ 100% が消え**、しかもエラーは出ません。
   抽出ツールはこの経路を無効化し、劣化したデータを出力するくらいなら中断する 2 つのカナリアを備えています。
2. **レスポンシブは 2 つの機構**であり、素直なテストでは片方しか見つかりません。`padding_tablet` という
   コントロールオブジェクトは*どこにも存在しません* — それでも `padding_tablet` は動きます。
   サフィックス付きの兄弟を探してレスポンシブを検出する方法では、padding、margin、width、font size、
   gap を取りこぼしていました。（修正後、コントロールの 9.8% → 30.1%。）
3. **コントロールのティアは、そのウィジェットのティアではありません。** Pro が無料ウィジェットに
   注入するからです。継承ではなく、計測。

## コントリビュート

より新しい Elementor に対して再抽出し、再生成した `data/` を添えて PR を送ってください —
`verify-schema.py` が、何が変わったかを正確に教えてくれます。
[CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## ライセンス

MIT。制作・保守: **moksa** · [moksaweb.com](https://moksaweb.com)

姉妹スキル: [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
