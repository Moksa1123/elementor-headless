# elementor-headless

**Elementor ページはエディタを操作して作るのではなく、JSON を直接書いて作る。**

AI コーディングエージェントに Elementor のオーサリングサーフェス全体を
クエリ可能なデータベースとして与える
[Agent Skill](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview)。
そして、そこに書かれたすべての主張を、実サイト上でのレンダリング・クリック・
計測によって証明する。Elementor は何を間違えてもエラーを一切出さないからだ。

```
192 widgets · 13 elements · 49,857 control pairs
the Kit's 773 Site Settings · 48 page settings · 29 document types
51 dynamic tags · 39 display conditions · every repeater's item fields
```

[English](README.md) · [繁體中文](README.zh-TW.md) · 日本語 · [한국어](README.ko.md)

---

## 問題

Elementor はページを post meta 内の JSON ツリーとして保存する。ツリーを書けば
ページは存在する。だが Elementor は**書いた内容を検証しない** — 値をそのまま
保存し、理解できた分だけレンダリングし、残りは黙って捨てる。

エラーは出ない。コントロール名のタイポ、オブジェクトを置くべき場所の文字列、
Free サイト上の Pro 専用コントロール、`"hidden-tablet"` と書くべきところの
`hide_tablet: "yes"`。どれも問題なく保存され、静かに何もしない。90% 正しい
ページは、誰かが「padding が一度も効いていない」と気づくまで、100% 正しい
ページと見分けがつかない。

したがって Elementor ページを組むエージェントの選択肢は 2 つだった。毎回
Elementor の PHP ソースを読む(高コストで、しかも JSON の形は分からない)か、
推測する(黙って間違える)か。このスキルは第 3 の選択肢だ：

```bash
$ python tools/el.py type slider
control type: slider   [FREE]  (elementor-core)

JSON value shape (what you write into _elementor_data settings):
  {"unit": "px", "size": "", "sizes": []}
```

## 仕組み

![architecture](assets/diagrams/architecture.svg)

3 フェーズ。**Extraction(抽出)** は Elementor のバージョンごとに 1 回、
稼働中の環境に対して実行され、劣化データの出力を拒否する 3 つの
カナリアを備える。**Verification(検証)** はすべてのコントロール・
ウィジェット・インタラクションを実サイト上でレンダリングし、実際に起きた
ことをデータに書き戻す。**Query(クエリ)** は、ビルド時にエージェントが
行う唯一の操作だ。

## インストール

```bash
git clone https://github.com/Moksa1123/elementor-headless
cd elementor-headless
python tools/install-skill.py claude-code --global     # or: cursor, codex-cli, gemini-cli, ...
python tools/install-skill.py --list
```

8 プラットフォーム対応：Claude Code、Claude.ai、Cursor、Codex CLI、
Gemini CLI、Devin(旧 Windsurf)、GitHub Copilot、Continue。各プラットフォームの
インストール先の慣例は 2026-07-11 に再検証済み —
[8 つのうち 3 つは 6 週間でドリフトしていた](references/multiplatform-install-verification.md)
ため、前提にせずチェックしている。アップグレード時は前バージョンが残した
ファイルを掃除する。去年の間違ったデータセットを今年の正しいものの隣に
放置するインストーラは、無い方がマシだ。

## 使い方

スキルをインストールしたら、あとはエージェントにページを説明するだけだ。
下記のツールを自分の手で実行する必要はない(そうしたければ話は別だが) —
このスキルがエージェントに一連のループを教え込む：

> post 123 にランディングページを作って：ダークなヒーロー、960px の boxed、
> 横一列に並んでモバイルでは縦積みになる icon-box カード 3 枚、角丸の CTA
> ボタン。このサイトに Elementor Pro は入っていない — Free ウィジェットのみで。

エージェントがこれをどう処理し、各ステップをどのツールが担うのか：

```
1. サーフェスをクエリする el.py            どのコントロールが存在するか、その
                                           JSON 値の形、ゲート、Free か Pro か
2. ツリーを書く           (エージェント)   _elementor_data を値の形どおりに書く
3. 書き込む前に検証する   validate-page.py 未知のコントロール、間違った値の形、
                                           未充足の依存、Free 上の Pro、不足プラグイン
4. WP-CLI 経由で適用する  apply-page.php   4 つの meta キー + ページ設定 + CSS 再構築
                                           + レンダリング済み HTML キャッシュのパージ
5. 公開ページを検証する   verify-live.py   公開 URL を、キャッシュ/CDN 越しに
```

ステップ 1-3 は完全にローカルで完結する — 設計と検証にサイトは一切要らない。
ステップ 4-5 は WordPress ホスト上の WP-CLI が必要だ(通常は SSH 経由)。
`wp eval-file` を実行できる経路なら何でもいい。

エージェントが頼りにするクエリ — 1 クエリ数百トークンで、完結した答えが返る：

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

組んで、検証して、出す：

```bash
python tools/el.py skeleton > page.json
python tools/validate-page.py page.json --target free --have woocommerce
wp eval-file tools/apply-page.php 123 page.json page-settings.json
python tools/verify-live.py page.json https://your-site/your-page/
```

- `validate-page.py` は Elementor が捕まえないものを捕まえる：未知の
  コントロール、間違った値の形、不正な単位、無効なオプション、id の重複、
  3 種類すべての未充足依存(条件は**デフォルト値**に対して評価されるため、
  `custom_messages` なしで `success_message` を設定すると、黙ってフォール
  バックする代わりに警告が出る)、複数選択の値、class 系コントロールへの
  数値の `0`、Free ターゲット上の Pro 専用コントロール、そして
  **ターゲットサイトがそもそも持ち得ないウィジェット**。
- `apply-page.php` は 4 つの meta キーと、省略可能なページ設定(Canvas が実際に
  必要とする `template` → `_wp_page_template` への振り分けを含む)を書き込み、
  コンパイル済み CSS を再構築し、**レンダリング済み HTML キャッシュを削除
  する** — 最後のこれを飛ばすと、正しいツリーがエラーひとつ出さずに前の
  ページを永遠に配信し続ける。
- `verify-live.py` はキャッシュ/CDN 越しに公開 URL を取得し、実際に
  配信されてきたレスポンスに対して、ツリー・CSS 値・ラッパークラスをアサートする。

## すべてのウィジェットがすべての環境に存在するわけではない

**ウィジェットサーフェスは Elementor 側ではなく、サイト側で決まる性質だ。** 同じ Elementor 4.1.4 / Pro 4.1.2 でも、あるマシンでは
148 ウィジェット、別のマシンでは 192 ウィジェットが登録され、どちらも
壊れてはいない — 増えた分は、最初のマシンに無い何かを必要としているだけだ。
これを持たないスキーマは不完全なのではなく、**間違っている**。
`woocommerce-product-price` について尋ねると、完全な自信をもって
「Elementor にそんなウィジェットは無い」と答えるからだ。

そこで各ウィジェットは自分の必要条件を持つ。Elementor のソースにある
モジュール自身の `is_active()` ゲートから読み取ったものだ — 信頼すべきはこの
ゲートであって、モジュール自身の `EXPERIMENT_NAME` 定数ではない。この教訓を
学ぶまで、その定数は登録済みでレンダリングもされる 21 ウィジェットに
誤ったラベルを付けていた：

| 必要条件 | ウィジェット数 |
|---|---|
| なし — 常に存在する | 104 |
| `plugin:woocommerce` | 29 |
| 何らかのプラグインが登録する WP レガシーウィジェット | 33 |
| `experiment:container` / `nested-elements` / `e_atomic_elements` / … | 26 |

`validate-page.py` はターゲットサイトが持ち得ないウィジェットをエラーにする。
サイトが実際に持っているものは `--have woocommerce nested-elements` で伝える。

**Elementor V4 のアトミック要素(全 18 個。`e-heading`、`e-flexbox`、
`e-form-*` など)は別のデータモデルだ** — 型タグ付きの props と独立した `styles` 配列
であり、`settings` + コントロールではない。このスキルはその prop スキーマを
報告する(`el.py widget e-heading`)が、構築まで検証できるかのように
装うことはしない。

## トークンコストと時間

**Elementor のソースを読むより 86.8% 少ないトークン。スキーマをロードする
より 99.4% 少ない。モデル取り込みで約 5 倍、スキーマロード比で約 118 倍
速い。** ツールのレイテンシは実測値(クエリあたり中央値 316 ms)。取り込み
時間はトークン数から、開示済みの基準レート 1,000 tok/s で導出している —
レートを変えても比率は動かない。自分の手で再現してほしい。スクリプトが
`data/token-benchmark.csv` を書き出す：

```bash
pip install tiktoken
python tools/benchmark-tokens.py --elementor-src /path/to/plugins/elementor
```

| タスク | ソース読解 | スキーマ全ロード | **クエリ** |
|---|---|---|---|
| ヒーローコンテナのレイアウト(flex、boxed、レスポンシブ padding) | 20,182 | 1,082,477 | **1,209** |
| 見出しのスタイリング(色、タイポグラフィ、配置) | 8,329 | 1,082,477 | **836** |
| ボタンのスタイリング(色、padding、radius、hover) | 7,803 | 1,082,477 | **3,664** |
| 任意のウィジェットの余白をレスポンシブ化 | 11,800 | 1,082,477 | **264** |
| CSS プロパティを駆動するコントロールの逆引き | — | 1,082,477 | **363** |
| **合計** | **48,114** | **1,082,477** | **6,336** |

節約率は以前 89.1% だった。それが**下がった** — サーフェスが正直になる
(WooCommerce、Kit、セレクタ、リピータフィールド)につれてスキーマは 583k
から 1.08M トークンへ成長し、リッチな答えはトークンを食う。改善しかしない
数字はキュレーションされている。ここの数字はスクリプトで再生成され、
どちらに動こうがそのまま載せる。

成立させているのは 2 点：データは**ロードされず、必ずクエリされる**こと、
そして全クラシックウィジェットが共有する 211 個の Advanced タブコントロールが
**168 回ではなく 1 回だけ格納される**こと。トークン数は tiktoken
`cl100k_base` による — Claude ではなく OpenAI のトークナイザなので絶対値は
±10% 程度ずれるが、同一トークナイザ下での比率は安定しており、主張して
いるのは比率のほうだ
([token-efficiency.md](references/token-efficiency.md))。

## Free と Pro は推測ではなく実測

Elementor Pro は**Free ウィジェットにコントロールを注入する**。Pro サイト上の
Free の Heading ウィジェットには Motion Effects、Sticky、Custom CSS、Display
Conditions、Custom Attributes が付いてくる。ウィジェットの tier をそのまま
継承すると、この 46 個がすべて「free」とラベル付けされ — 自分の環境では完璧に
レンダリングされるページが、Free 環境でスタイルを失う。

だから tier は実測する。Pro をロードした状態で 1 回、
`wp --skip-plugins=elementor-pro`(その 1 つの CLI プロセスにしか影響しない。
本番環境でも安全)で 1 回抽出し、差分を取る。同じ手法をもう 1 軸進めたのが
WooCommerce だ。WooCommerce は 29 ウィジェットを足すだけではない — Pro 自身の
ループウィジェットに `product_query_exclude*` を注入し、WooCommerce を切った
ダンプだけが、それらのコントロールの持ち主を明かす。サードパーティ汚染も
同じ方法で除外している。Rank Math は `accordion` に、Unlimited Elements は
コンテナに注入し、それらをロードしたまま抽出したスキーマは、そうしたプラグインの
コントロールを Elementor 製として出荷してしまう。

tier について推論するな。**Border と Box Shadow はプレミアムに見えるが free。
`_attributes` は地味に見えるが Pro だ。** このリポジトリは一度、実測ではなく
推論で Border を Pro と誤ってラベル付けし、そのまま出荷した。さらに Elementor コアは、Pro が
無効のとき**本物の Pro ウィジェットと完全に同名のプロモ用スタブ**を登録する —
Pro なしのダンプを額面どおり受け取ると、26 個の Pro ウィジェットが free と
して読めてしまう。

## 正確なのか？証明させろ。

信用するな — テストしろ。8 つのチェック、8 つの異なる問い、それぞれ異なる
アーティファクトからの読み出し：コントロールスタック、コンパイル済み
スタイルシート、配信された HTML、実ブラウザの computed styles、実ポインタ
イベント、CDN 越しの公開 URL。**ベリファイアは、自分が読むチャネルの中の
バグしか見つけられない** — この 8 つはどれも、より甘いチェックが実在するバグを
見逃したからこそ存在している。

**1. スキーマは手元の環境と一致しているか？**

```bash
python tools/verify-schema.py mine.json --free-dump mine-free.json
```

すべての (owner, control) ペアを走査し、型と Free/Pro の主張を確認する。
そしてスキーマが各ウィジェットの必要条件を明示しているおかげで、「スキーマが
間違っている」と「この環境に WooCommerce が無い」を区別し、どちらについても
誤警報を出さない。両方の抽出サイトに対して PASS し、ドリフトが
あれば非ゼロで終了するので、デプロイのゲートにできる。

**2. CSS を出すはずのコントロールは、全部が実際に CSS を出すのか？**

各コントロールに**それ固有の値**(固有の hex カラー、固有のピクセルサイズ)を
与え、依存チェーンを自動で解決し、その出力を**公開 URL が配信した
スタイルシート**の中でアサートする — サーバーのディスク上のファイルでは
なく：

```
25,259 CSS-driving controls    99.4% covered, 0 failures
33,448 responsive suffixes     each asserted inside ITS media query, with a value
                               distinct from desktop's, so a leak cannot pass
```

Elementor 自身のメタデータが間違っている場合は、レンダリング結果が勝つ。
9 個のコントロールは、実際には出力しないレスポンシブブレークポイントを
謳っており、スキーマは現在それらを `rwd-BROKEN` と記載している。

**3. class を出すコントロールは、全部がラッパーにそのクラスを付けるのか？**

3,308 個のコントロールは CSS を出す代わりにラッパークラスの付与で動作する —
スタイルシートのチェックは、その全部に対して構造的に盲目だ。配信された HTML
から読み出す：99.8% スイープ、失敗 0。`classes_dictionary` によるレガシー
リマップ(`position: "top"` は `elementor-position-block-start` として
レンダリングされる)と、デバイス別プレフィックス(`_tablet` サフィックス
ではなく `elementor-tablet-position-`)も含めてだ。

**4. 宣言したものを、実ブラウザは本当に COMPUTE するのか？**

ルールはファイルの中にあっても負けることがある — 詳細度に、カスケードに、
何にもマッチしないセレクタに。`sweep-browser.py` はすべてのページを Chromium
で開き、Elementor の宣言を `getComputedStyle` と比較する。それも**ルールが
実際にターゲットとするノードの上で**(`data/css-selectors.csv` はそのために
存在する)：

```
48,873 probes across two live sites with different themes
25 of 26 override patterns IDENTICAL on both -> facts about Elementor,
   led by: _element_width's max-width is dead on every widget inside a
   container, killed by Elementor's own frontend.css at specificity (0,4,0)
 1 of 26 site-specific -> a fact about that theme, named by the data
```

**5. コンテンツを与えたとき、各ウィジェットは本当にそれをレンダリングするのか？**

すべてのコンテンツコントロールに固有のマーカーを仕込み(リピータ項目は
抽出済みフィールドから構築)、JS エラーやゼロサイズのレンダリングを正確に
1 つのウィジェットへ帰属できるように**1 ページ 1 ウィジェット**、要素
スクリーンショットを各 1 枚、3 ビューポートで：

```
168/168 placeable widgets across the two sites
  126 rendered — marker echo, real site content, or hidden-by-design
   42 correctly empty without site context (cart/checkout/loop on a bare page)
    0 broken
```

**6. インタラクティブなウィジェットは、本当に操作に反応するのか？**

公開ページ上の実ポインタイベント：

```
nested-tabs        click tab 2  -> content 2 shows, content 1 hides    PASS
nested-accordion   click item 2 -> <details> opens                     PASS
accordion          click item 2 -> body becomes visible                PASS
toggle             click item 1 -> body toggles open                   PASS
image-carousel     click next   -> active slide advances               PASS
```

そして `:hover` ルール — どんな静的読み出しでも検証不能 — は実際のポインタ
操作で検証する：3,882 プローブ、297 件が値で検証済み。113 件のオーバーライドは
すべて同一要素上のシード衝突(2 つの hover コントロールが同じプロパティに
意図的に異なる値を書く — どちらかは必ず負ける)で、行単位で分類済み。
トランジションは事前に無効化し、その介入は開示している。シードした 79 秒の
トランジションの 200 ms 時点で読んだ色は、アニメーション途中のフレームで
あって、判定ではない。

**7. ワークフローはエンドツーエンドで成立するのか？**

以下はそれぞれヘッドレスで構築し、その後ライブサイト上のブラウザで検証した：

- **Global colors**：Kit の `custom_colors` に色を追加し、`__globals__` 経由で
  参照すると、computed でちょうどその色になる
- **Dynamic tags**：`post-title` バインディングが投稿の実際のタイトルを届ける
- **Display conditions**：`logged_in` 条件付きの要素は、未ログイン状態で取得した
  HTML には現れない — CSS で隠されるのではなく、サーバーサイドでドロップされる
- **Theme Builder**：1 ページにスコープしたヘッダーは、そのページでだけ
  レンダリングされ、他のどこにも現れない
- **Popups**：`page_load` トリガーのポップアップが未ログインのブラウザで開く
- **Loop Builder**：loop-item テンプレート + loop-grid が実在する 3 投稿を
  レンダリングする
- **Forms**：未ログインでの入力 → nonce → データベース行 → カスタム成功メッセージ
- **Canvas**：`template: elementor_canvas` がテーマ側のヘッダーやフッター
  といった外枠を取り除く(ページ設定だけでは届かない `_wp_page_template` 経由で)
- **Templates**：Elementor 自身の JSON フォーマットでエクスポート/インポート、
  メディアは Elementor 自身のフックで再ホストされる

**8. 一般公開されるページに、その全部が入っているのか？**

```bash
python tools/verify-live.py page.json https://your-site/your-page/
```

公開 URL と、**そのページがリンクするすべてのスタイルシート**(ページの
スタイルは複数ファイルに分かれている — Kit のグローバルは別ファイルにある)を
エッジキャッシュ越しに取得し、ツリー + CSS 値 + ラッパークラスをアサート
する。改ざんされたツリーに対しては fail する — 一度も赤くなったことのない
ベリファイアは、ベリファイアではない。
[examples/demo-page.json](examples/demo-page.json) はこの方法で組み上げた
完全なページだ。実際に公開されており、エディタでは一度も開かれていないまま、
3 つのビューポートでこのチェックを通過している。

## 罠

これを素朴なやり方でやると、**番号を振って列挙できる 11 通り**の形で間違える — どれもこの
リポジトリで実際に出荷されてから捕まったもので、いまはそれぞれカナリア、
バリデータのルール、あるいはデータフィールドになっている。詳細は
[extraction-traps.md](references/extraction-traps.md)：

1. WP-CLI には削ぎ落とされたコントロールスタックが渡る — 46% のコントロールが黙って消える
2. レスポンシブは 2 つの仕組みでできている。`padding_tablet` にはコントロールオブジェクトが無いのに動く
3. コントロールの tier はウィジェットの tier ではない — Pro は Free ウィジェットに注入する
4. コントロールのゲートは 3 通りある。661 個のコントロールは空の補間値で死ぬ
5. レスポンシブの依存関係はブレークポイントごとに再チェックされる
6. `is_responsive` は過剰に約束する — 本当のことはレンダリングだけが知っている
7. CSS はコントロールにできることの半分にすぎない — 3,308 個は代わりにクラスを出す
8. class の値はリマップされ、そのデバイスプレフィックスは別の文字列になる
9. `_elementor_data` を書くと古いレンダリング済み HTML キャッシュが残る — 正しいツリーが前のページを配信し、17k コントロールのスイープがその上を green で走った
10. ウィジェットサーフェスは Elementor ではなく、インストール環境で決まる性質
11. ルールはスタイルシートの中にあっても負けることがある — それが見えるのはブラウザだけ

加えて、それぞれの現場で文書化されている罠がある。Canvas の `template` 設定は
ページ設定ではなく `_wp_page_template` に保存される。ライブラリテンプレートには
`elementor_library_type` **タクソノミー**と conditions の**キャッシュ**が必要で、
無ければ Theme Builder からは一切認識されない。`theme-*` ウィジェットは挿入時に
エディタから動的バインディングをもらうので、ヘッドレスのツリーでは
`__dynamic__` を自分で書く。WP レガシーブリッジは設定をすべて `settings.wp` の
配下に受け取る。`e_display_conditions` は JSON **文字列**を包む配列であり、
ドキュメントがかつて示していた裸の配列は、問題なく保存された上で黙って
無視される。

## 同梱物

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

## 限界も隠さない

- **Elementor V4 アトミック要素**：クエリのみ。構築は別のデータモデルで、
  このスキルはまだそれを書けない。
- **コンテキスト依存のウィジェット**(カート、チェックアウト、投稿コメント、
  商品パーツ)は、素のページ上では「正しく空」として検証される。完全な挙動には
  ストアや投稿のコンテキストが必要で、スイープはそれを捏造しない。
- **バージョン固定**：ここにある数字はすべて Elementor 4.1.4 / Pro 4.1.2 で
  計測したものだ。新しいバージョンはそのどれでも無効化しうる — だからこそ
  すべてのベリファイアを同梱し、*自分の*環境に対して再実行できる
  ようにしてある。
- `page_load` 以外のポップアップトリガー、`save-to-database` 以外のフォーム
  アクション、サードパーティ製アドオンのウィジェットは、抽出はされているが
  E2E 検証はしていない。

## 自分の環境向けに再生成する

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

## ブロックをページ間・サイト間で再利用する

```bash
wp eval-file tools/export-template.php <post_id> > hero-block.json
wp --user=1 eval-file tools/import-template.php hero-block.json
```

`_elementor_data` のコピーでブロックをサイト間移動してはいけない。メディア系
コントロールが保存しているのは添付ファイルの **id** であり、id は別のサイト
では別の画像を意味する。これらのツールは Elementor 自身のインポート経路を
通るので、`on_import` フックがメディアを再ダウンロードしてくれる。さらに
`[elementor-template id="123"]` は、保存済みテンプレートを任意の WordPress
コンテンツに埋め込める — Free の shortcode ウィジェット経由で、Pro なしに
ブロックをページへネストすることも含めてだ。

## コントリビューション

より新しい Elementor に対して再抽出し、再生成した `data/` で PR を開いて
ほしい — 何が変わったかは `verify-schema.py` が正確に教えてくれる。
[CONTRIBUTING.md](CONTRIBUTING.md) を参照。

## ライセンス

MIT。**moksa** · [moksaweb.com](https://moksaweb.com) が構築・保守。

姉妹スキル：[rankmath-seo-wp](https://github.com/moksa1123/rankmath-seo-wp)
