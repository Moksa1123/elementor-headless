# elementor-headless

**エディタを操作するのではなく、JSON を書いて Elementor ページを構築する。**

AI コーディングエージェントに、Elementor のオーサリング面すべて —
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
信用せず、テストしてください。検証は 5 つ、問いも 5 つとも違い、読む対象も 5 つとも違います。

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

**3. スキーマ内のすべてのコントロールは、本当に動作するのか。**

`verify-render.py` がカバーするのは、そのページがたまたま使っているコントロールだけです — デモページ
では 94 個。`sweep-controls.py` が残りをカバーします。CSS を制御すると主張するすべてのコントロールに
ついて正当な値を合成し、それを効かせるために必要な依存の連鎖を解き、レンダリングし、その値が実際に
出力されたことをアサートします。各コントロールには**そのコントロール固有の**値（それぞれ異なる 16 進
カラー、それぞれ異なるピクセルサイズ）が与えられるので、パスしたということは*そのコントロール*が
*その値*を生み出したという意味になります。何か別のものが似たプロパティを書いた、ではなく。

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

コントロール単位の結果は `data/control-verification.csv` に同梱しています — `skipped` のものも
含めてあるので、カバレッジの数字をそれらを抜きにして読むことはできません。

**そしてスイープは抽出ツールを訂正します。** `build-indexes.py --verification` は、レンダリング結果を
スキーマに折り返します。9 個のコントロールは、決して出力しないレスポンシブブレークポイントを宣伝して
います（`hotspot.width_tablet` は CSS を一切生成しないことを、単独で検証済み）。これらは現在
`responsive_broken` としてフラグが立ち、`el.py` は `rwd-BROKEN:` と表示し、`validate-page.py` は
それを書けばエラーにします。レンダリングしなければ、9 個すべてが動作するレスポンシブコントロールとして
スキーマに残ったままだったでしょう。

**4. CSS ではなくクラスを出力するすべてのコントロールをスイープする。** スタイルシートのスイープでは
これらはまったく見えません — しかも 2,573 個あります（`_position`、`hide_tablet`、あらゆる `view` /
`shape` / `align` コントロール、そして transform 系）。こちらは**レンダリング後の HTML** を読み、
ラッパーに付いたクラスをアサートします。

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

これを走らせて、他の何をもってしても見つけられなかったものが 3 つ出てきました。

- **`apply-page.php` が、古いレンダリング済み HTML キャッシュを残していた。** Elementor は自身が
  レンダリングしたマークアップを `_elementor_element_cache` という post meta に保持し、それをそのまま
  返します。Elementor 自身の保存経路はこれをクリアしますが、meta を直接書き込む場合はクリアされません。
  結果、投稿は更新され、CSS も正しく再構築され、`_elementor_data` を読み戻せば完全に正しいのに —
  ページは**以前のマークアップ**を返し続け、エラーは一切出ませんでした。CSS スイープはこのバグが
  生きたまま 17,421 個のコントロールを通してグリーンで走りました。CSS は常に再構築される別ファイル
  だからです。最初の HTML スイープは 1 分で捕まえました。14 バッチすべてがバイト単位で同一だったのです。
- **`validate-page.py` が、完璧にレンダリングされるページを却下していた。** `icon-box` の
  `position: "top"` はオプションリストに存在せず、しかも Elementor の `classes_dictionary` はそれを
  `block-start` に読み替えます。誤ったエラーであり、現在は注記に変更しました。
- **スキーマが、タブレットで間違ったクラスを主張していた。** レスポンシブなクラス系コントロールは
  *デバイスごとに異なる prefix* を持ちます（`_tablet` サフィックスではなく
  `elementor-tablet-position-`）。抽出ツールはバリアントを潰し、デバイスの prefix を捨てていました。

**5. 一般の訪問者が受け取るページを検証する。** ここまでのすべては、マシンの内側にあるアーティファクトを
読んでいます — サーバのディスク上の CSS ファイル、PHP 呼び出しから出てきた HTML。**そのどれも、訪問者が
受け取るものではありません。** テーマ、ページキャッシュ、Varnish、そして CDN がすべてあいだに挟まっており、
どれもが別のものを配信しうるのに、サーバ側のチェックはすべてグリーンのままです。これは罠 9 を、もう
1 層外側に押し出したものです。

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

スタイルシートが 4 つあることに注目してください。**ページのスタイリングは複数のファイルに分割されます** —
Kit がグローバルな色とフォントを、ページが自分自身の分を持ちます。ここにある他の検証ツールはどれも、
ディスク上の単一の `post-<id>.css` を読んでおり、それは構造的に不完全な絵です。こちらは、ページが実際に
*リンクしている*ものを、キャッシュ越しに（`x-cache=HIT`）読みます。訪問者が「動いている」と認めるであろう
定義は、それだけです。

**6. 実物を見る。** `examples/demo-page.json` は、このスキルだけで構築された実在の公開ページです。
Elementor エディタは一度も開かれていません。

**https://moksaweb.com/elementor-headless-demo/**

## ページ間・サイト間でブロックを再利用する

Elementor 自身の JSON 交換フォーマット — エディタの Export / Import Template ボタンの裏側にある
ファイルです。

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json
wp --user=1 eval-file tools/import-template.php hero-block.json <target_post_id>
```

**`_elementor_data` をコピーしてサイト間でブロックを移動させては絶対にいけません。** メディア系の
コントロールは添付ファイルの id を保存しており、その id は移動先のサイトでは*別の画像*を指します —
あるいは何も指しません。Elementor の `on_export` は id を url に置き換え、`on_import` はそれを
移動先のメディアライブラリへ再ダウンロードします。生の meta をコピーすれば、画像は黙って壊れるか、
黙って別の画像に化けます。ここで提供するツールは Elementor 自身のインポート経路を呼び出し、これらの
フックを確実に通します。ラウンドトリップの計測結果は、記述した設定 82 件、失われたもの 0、
変化したもの 0。

## 同梱物

```
data/
  elementor-schema.json    3.2 MB   オーサリング面の全体 - クエリするもので、読み込むものではない
  controls.csv             2.0 MB   ウィジェット/エレメント固有のコントロール全件
  common-controls.csv       39 KB   全ウィジェットが共有する 210 個
  pro-only-controls.csv     33 KB   安全確認用テーブル
  pro-only-widgets.csv     3.0 KB
  control-types.csv        4.6 KB   59 種類すべての JSON 値の形
  group-controls.csv       3.7 KB   16 グループと、それが展開されるフラットキー
  widgets.csv              8.3 KB   135 ウィジェット + 3 エレメント
  breakpoints.csv          0.2 KB
  control-verification.csv          コントロール単位: 主張どおりの CSS を出力するか?
  class-verification.csv            コントロール単位: 主張どおりのクラスを出力するか?
  token-benchmark.csv               再現可能な計測結果

tools/
  el.py                          スキーマにクエリする - 正面入口
  validate-page.py               ページツリーの事前チェック
  apply-page.php                 書き込む: meta + CSS 再構築 + HTML キャッシュ + バックアップ
  extract-elementor-schema.php   稼働中のインストールをダンプする
  build-indexes.py               ダンプ + スイープ結果 -> 同梱データファイル
  verify-schema.py               スキーマはあなたのインストールと一致するか?
  verify-render.py               Elementor はスキーマが約束したものを出力するか?
  verify-live.py                 CDN 越しの公開ページに、それは載っているか?
  sweep-controls.py              CSS 系コントロールを全件レンダリングし、スタイルシートをアサートする
  sweep-classes.py               クラス系コントロールを全件レンダリングし、HTML をアサートする
  export-template.php            Elementor 自身の JSON 形式でエクスポートする
  import-template.php            Elementor 自身の経路で、メディアごとインポートする
  benchmark-tokens.py            トークン数値を再現する
  install-skill.py               8 プラットフォーム対応インストーラ

references/   data-model · control-types · containers-and-layout · responsive
              templates-and-conditions · import-export · extraction-traps
              token-efficiency
examples/     demo-page.json - 上記の公開ページ
```

## 9 つの罠

これを素朴にやると、9 つの別々のかたちで間違えます。どれも、完全に見えて嘘をつくスキルを生みます。
**9 つとも、発覚する前にこのリポジトリで実際に出荷されました** — いくつかは Elementor のソースを
読んで、残りはすべてのコントロールをレンダリングして出てきたものを見て、初めて分かりました。詳細は
[extraction-traps.md](references/extraction-traps.md) に。

1. **WP-CLI は Elementor からはフロントエンドに見える**ため、痩せたコントロールスタックが返ってきます。
   **コントロールの 46%、そしてタブ/ラベルのメタデータのほぼ 100% が消え**、しかもエラーは出ません。
   抽出ツールはこの経路を無効化し、劣化したデータを出力するくらいなら中断する 3 つのカナリアを備えています。
2. **レスポンシブは 2 つの機構**であり、素直なテストでは片方しか見つかりません。`padding_tablet` という
   コントロールオブジェクトは*どこにも存在しません* — それでも `padding_tablet` は動きます。
   サフィックス付きの兄弟を探してレスポンシブを検出する方法では、padding、margin、width、font size、
   gap を取りこぼしていました。（修正後、コントロールの 9.8% → 30.1%。）
3. **コントロールのティアは、そのウィジェットのティアではありません。** Pro が無料ウィジェットに
   注入するからです。継承ではなく、計測。
4. **コントロールのゲートのかかり方は 3 通りあり**、`condition` はそのうちの 1 つにすぎません。
   152 個のコントロールは、独自の演算子を持つ高度なブール形式によって*のみ*ゲートされています。
   さらに 499 個のコントロールは、*別の*コントロールの値を自分の CSS に補間します — その別の値が
   空だと、Elementor は宣言全体を捨てます。文書化された条件はすべて満たされていて、エラーも出ないのに、
   です。グラデーションの色を指定せずにグラデーションの角度だけ設定すれば、何も出てきません。黙って。
5. **レスポンシブコントロールの依存関係は、ブレークポイントで再チェックされます。** `X_tablet` を
   設定して `Y_tablet` を設定しなければ、デスクトップは完璧に描画され、タブレットは黙って空になります。
   1,433 個のレスポンシブサフィックスが、まさにこの理由で何も出力していませんでした。
6. **`is_responsive` は過大な約束をします。** `hotspot.width` は `container.padding` と同じフラグを
   持っています。`padding_tablet` は動き、`width_tablet` は何も出力しません。知っているのはレンダリング
   だけです — だからスイープはその結果を折り返し、スキーマを訂正します。
7. **CSS はコントロールができることの半分にすぎません。** 2,573 個のコントロールはラッパーに
   **クラス**を付けることで作用し、そのうち 1,894 個は CSS を一切出力しません — つまりスタイルシートの
   スイープは、どれだけグリーンで走ろうと、それらの存在すら見ることができません。ここではその全部が
   「Elementor が `prefix_class` を登録しているのだから、おそらく動くだろう」という根拠だけで出荷されて
   いました。
8. **クラス系コントロールの値は読み替えられ、prefix はデバイスごとに変わります。**
   `position: "top"` はオプションリストに存在しないのに `elementor-position-block-start` を
   レンダリングします（`classes_dictionary`）。`position_tablet` は
   `elementor-**tablet**-position-…` をレンダリングするのであって、クラスに `_tablet` サフィックスが
   付くのではありません。switcher は `return_value` を保存するので、`hide_tablet: "yes"` は
   `elementor-yes` をレンダリングし、何も隠しません。そして `"columns": 0` は何も出力せず、
   `"columns": "0"` は動きます。
9. **`_elementor_data` を書き込むと、古いレンダリング済み HTML キャッシュが残ります。** 投稿は更新され、
   CSS は再構築され、meta を読み戻せば完全に正しい — それでもページは**以前のマークアップ**を、永遠に、
   エラーも出さずに返し続けます。17,421 個のコントロールを通す CSS スイープが、このバグが生きたまま
   グリーンで走りました。CSS は常に再構築される別ファイルだからです。

罠 9 は、このプロジェクトの主張そのものを 1 行で表しています。**検証ツールは、自分が読むチャネルの
バグしか見つけられません。** あるチャネルでグリーンだったことは、他のチャネルについて何も語りません。

## コントリビュート

より新しい Elementor に対して再抽出し、再生成した `data/` を添えて PR を送ってください —
`verify-schema.py` が、何が変わったかを正確に教えてくれます。
[CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## ライセンス

MIT。制作・保守: **moksa** · [moksaweb.com](https://moksaweb.com)

姉妹スキル: [rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
