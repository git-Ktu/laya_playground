# 日本語ドキュメントとタブ内入力保持 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 日本語ガイドを読みながら Playground の入力を失わずに作業できるようにする。

**Architecture:** FastAPI の既存 HTML 配信に `/guide` を追加する。ガイドの章・コード例は静的 HTML、目次とコピーは専用 JavaScript で提供する。Playground の編集状態はバージョン付き sessionStorage に保存し、入力を検証・変換せずに復元する。

**Tech Stack:** FastAPI、既存 vanilla JavaScript / CSS、sessionStorage、pytest、Playwright / Chrome。追加依存関係なし。

**Spec:** `docs/superpowers/specs/2026-10-02-laya-documentation-design.md`（承認済み、第三者の記事の参照は削除済み）。

## Global Constraints

- プロジェクト: `/home/server/work_space/laya_playground`。実行開始時に using-git-worktrees で隔離方針を確認する。
- Laya 0.3.22、`convaiinnovations/laya-multilingual`、multilingual 固定、max_len=8192 を維持。
- 既存 `/docs` と `/openapi.json` を維持。日本語ガイドは `/guide`。
- Frontend Design: `/tmp/laya-frontend-design-SKILL.md` を読み、設計書の配色・文字組み・ワイヤーフレームに従う。
- 同じ origin・同じタブの往復と再読み込みに対応。タブ終了後の永続保存は行わない。
- 現在の Plain text / JSON 直接 Run、Ctrl+Enter、原子的なモード切替、token 検証を維持。
- 保存対象は入力。結果、token キャッシュ、busy、エラー、モデル情報は保存しない。
- 参照情報は Laya の公式リポジトリとモデルの公式ページのみ。
- 外部 CDN、フレームワーク、モデル・API 契約・systemd の変更は行わない。
- 開発中は稼働サービスを差し替えない。統合後、サービスを再起動して `/guide` と既存機能を実測する。
- 実装・レビューはユーザー指定のサブエージェント方式。各タスク後に独立レビュー、最後に全変更のレビュー。

## Review Focus

1. 不正な JSON / 空欄 / 重複した質問名を request() で保存しないこと。Task 2 の raw 往復テストで確認する。
2. sessionStorage が禁止・満杯の場合、Run は使え、移動前には保持不能を案内すること。Task 2 の例外注入テストで確認する。
3. bfcache / Back / Forward / 推論待ち中の移動で、古い応答や busy が復帰画面を壊さないこと。Task 2 の遅延応答テストで確認する。
4. JSON の高度な upstream 設定を、現在のフォームで必ず維持できると案内しないこと。Task 1 の内容レビューと例題 validator で確認する。
5. モバイルの長いコード・表と HTTP LAN のコピー失敗が作業を妨げないこと。Task 1 のレイアウト・コピーの実ブラウザーテストで確認する。

## File Structure

| ファイル | 責務 |
|---|---|
| `app/main.py` | `/guide` の FileResponse 追加 |
| `app/templates/index.html` | 共通ナビと章ヘルプ、保持案内・失敗時の移動 UI |
| `app/templates/guide.html`（新規） | 日本語本文、章アンカー、目次、コード例 |
| `app/static/guide.css`（新規） | ガイドのレイアウト・文字組み・レスポンシブ |
| `app/static/guide.js`（新規） | 目次、現在地、コピー、ガイドのスクロール |
| `app/static/draft-storage.js`（新規） | 保存・読み込み・schema チェックと例外処理 |
| `app/static/playground.js` | 編集状態の収集・適用・保存イベントと復帰処理 |
| `app/static/playground.css` | 共通ナビと必要な保持案内の最小追加 |
| `tests/test_guide.py`（新規） | ルート、説明の必須項目、公開 JSON 例の検証 |
| `tests/test_playground_browser.py` | 実 Chrome で往復・保存失敗・モバイル・コピーを検証 |
| `README.md` | ガイド URL、保持範囲、公式情報の説明 |
| `docs/documentation-verification.md`（新規） | 最終実測結果 |

既存ファイル全体の整形・リファクタリングは行わない。ガイド用 CSS は `.guide-page` 等で scope を限定し、既存の広い main / header セレクターの影響を明示的に調整する。

## Task 1: 日本語ガイドと相互ナビゲーション

**Files:** 上表の `main.py`、両テンプレート、`guide.css`、`guide.js`、`playground.css`、`test_guide.py`、ブラウザーテスト、README。

**Interfaces:**

- Consumes: `create_app(service=None)`、既存ブラウザー fixture `browser_page`、`app.models.requests.validate_request(body)`。
- Produces: `/guide`（include_in_schema=False）、`#guide-nav`、`#guide-content`、章 ID `getting-started`, `state`, `questions`, `choice`, `score`, `noul`, `results`, `examples`, `limits`, `api`。
- 両ページの同じタブのリンク: `[data-internal-nav]`。ガイドリンクは `/guide`、Playground は `/`。章ヘルプは `/guide#state` と `/guide#questions`。
- コード例は `pre[data-example="例題名"][data-kind="state|questions"]`。コピー用ボタンの `data-copy-target` は対応する pre の ID。HTML エスケープした有効な JSON を表示し、DOM textContent からコピーする。
- `guide.js` の `copyExample(targetId: string): Promise<void>` は Clipboard API → execCommand → 選択済み手動コピーの順で試す。コピー通知は role=status。
- ガイドの位置保存キー `laya-guide:scroll:v1`。章アンカーのある直接アクセスではアンカーを優先する。

- [x] **Step 1: ルートと例題の失敗テストを書く。**

`tests/test_guide.py` に以下を追加する。既存 FakeService を使い、実モデルをロードしない。

```python
def test_guide_routes_and_api_docs(client):
    r = client.get('/guide')
    assert r.status_code == 200
    assert 'text/html' in r.headers['content-type']
    assert 'lang="ja"' in r.text
    assert 'href="/"' in r.text
    assert client.get('/docs').status_code == 200
    assert client.get('/openapi.json').status_code == 200
```

`test_guide_public_examples_validate` は標準 HTMLParser で data-example / data-kind の pre text を抽出し、製品レビューとメール 3 状態の全組を `json.loads` と `validate_request` に通す。全組に Choice / Score / Noul があり、メール 3 状態の質問は同じであることを確認する。

`test_guide_sections_and_official_references` は上記 10 章、`instructions`、`criteria`、`answer_confidence`、切り捨ての説明を確認する。GMO 記事へのリンクがないことを確認する。

- [x] **Step 2: RED を確認する。**

Run: `uv run pytest tests/test_guide.py -q`。新しい `/guide` が 404 等で FAIL することを記録する。

- [x] **Step 3: ページと内容を実装する。**

`main.py` にガイド配信を追加。承認済み設計の全章を実際の日本語本文として書く。Choice / Score / Noul は用途、フォームの設定方法、JSON、結果を順に説明する。例示結果は説明用と明記する。Score の小数を割合として表示せず、confidence と answer_confidence の違いを説明する。

ガイドの冒頭は短い利用手順、本文は設定表と短いコード例を中心にする。PC の章目次と右小目次、モバイルの目次開閉、sticky のアンカー位置、キーボードフォーカス、aria-current、reduced-motion を実装する。guide.js はドキュメントを読むだけで推論 API を呼ばない。

- [x] **Step 4: ガイド操作の失敗テストを書き、RED を確認する。**

ブラウザーテスト追加:

- `test_guide_navigation_examples_and_copy`: 両方向のリンク、章ヘルプ、アンカー位置、コピーした JSON が pre と一致し parse 可能、推論 calls は 0。
- `test_guide_mobile_keyboard_and_copy_fallback`: 390px で目次開閉、Escape、フォーカス、ページ横溢れなし。Clipboard API と execCommand の失敗を注入し、手動コピー用 textarea に正しい JSON が選択される。
- `test_guide_scroll_and_anchor`: ガイド復帰の位置と、直接章リンクでのアンカー優先を確認する。

- [x] **Step 5: 操作・表示を完成し、GREEN と画面レビューを確認する。**

Run: `uv run pytest tests/test_guide.py tests/test_playground_browser.py -q`。PC / モバイルの screenshot は pytest tmp_path に保存し、Frontend Design に照らして自分で見る。見出し・目次・コードが詰まりすぎないことを確認する。`node --check app/static/guide.js` も成功させる。

- [x] **Step 6: コミットし独立レビューを受ける。**

対象ファイルだけを stage し、`Add Japanese guide and navigation` としてコミット。レビュー対象は内容の正確性、公開例、配色と文字組み、API 文書との区別、既存 Playground への影響。

## Task 2: タブ内の編集状態保存と往復の完成

**Files:** `draft-storage.js`、`playground.js`、`index.html`、必要な最小 CSS、ブラウザーテスト、README。

**Interfaces:**

- Consumes: Task 1 の `[data-internal-nav]`、既存 `questions` / `structuredState` / `activeMode` / renderQuestions / stateChanged。
- Produces: classic script の `window.LayaDraft`。playground.js より先に読み込む。
- `LayaDraft.read(): {status: 'empty'|'ok'|'invalid'|'unavailable', draft?: DraftSnapshot}`。
- `LayaDraft.write(snapshot: DraftSnapshot): boolean`。キーは `laya-playground:draft:v1`。例外を UI へ投げない。
- DraftSnapshot: `schemaVersion: 1`, `mode: 'text'|'json'`, `stateRaw: string`, `structuredState: boolean`, `questions: Array<{name:string,type:'choice'|'score'|'noul',instructions:string,criteria:Array<[string,string]>}>`, `stateJsonRaw: string`, `questionsJsonRaw: string`, `origin: string`, `requestOpen: boolean`, `scrollY: number`。
- `captureDraft(): DraftSnapshot` と `restoreDraft(snapshot: DraftSnapshot): void` は Playground 側。restore は switchMode / populateForms / request を呼ばず、raw の値を直接設定する。
- `persistDraft(): boolean` は保存不能の案内を更新し、内部リンククリック時にも使う。成功時はナビゲーションを妨げない。
- 保存不能の移動 UI: 「このまま移動」「戻る」。拒否時は入力を失わず、その場で作業を続ける。

- [x] **Step 1: 入力保持の失敗テストを書く。**

`test_plain_draft_survives_guide_and_reload` は状態、質問名、種類、instructions、criteria の key / 説明 / 順序、origin、API details を変更して往復・再読み込みする。重複名・空行・未完成の指示も保存できることを確認する。

`test_json_raw_draft_survives_guide_and_reload` は JSON モードの両欄へ不正な書きかけ JSON を入れ、往復後の input_value が一致することを確認する。非表示のフォームと structuredState も保存データに残る。復元後に修正し Run すると、その最新値だけが service.calls に入る。

Run: `uv run pytest tests/test_playground_browser.py -q -k 'draft'`。FAIL を記録する。

- [x] **Step 2: 保存層と Playground 統合を実装する。**

draft-storage.js は sessionStorage の getItem / setItem と保存オブジェクトの schema チェックを担当。UI のデータ構造の型をチェックするが、文章の完成度や JSON 構文はチェックしない。保存データから任意の HTML を生成せず、フォーム値 / textContent を使う。

capture は questions のフォーム配列をそのまま複製し、JSON 欄は raw 文字列として保持する。すべての編集・追加・削除・モード変更成功・origin / details 変更で同期保存する。既定値を描画する前に read / restore し、復元した JSON を syncJsonDrafts で上書きしない。

モデル情報と token は取り直し、既存の generation と captured request の保護を維持する。復元による API 呼び出しは `/info` と必要な tokenize のみ。Run を自動再送しない。

- [x] **Step 3: 保存障害と履歴の失敗テストを書く。**

- `test_draft_storage_unavailable_navigation`: Storage.setItem に QuotaExceededError / SecurityError を注入。案内表示、移動キャンセルによる入力保持、「このまま移動」、保存不能でも Run の成立を確認。
- `test_draft_invalid_saved_schema`: 壊れた保存 JSON、未知 version、不正な fields を入れて reload。安全な既定値と復元失敗案内、Run が使えることを確認。
- `test_draft_history_and_pending_run`: Back / Forward を使い、入力を保持。tokenize / inference を遅延させて移動し、戻った際に busy が固まらず古い応答で編集状態を戻さない。余分な inference calls が発生しない。Chrome が bfcache を使用したかを記録し、pageshow.persisted 経路もブラウザー内で exercise する。
- `test_structured_state_draft_types`: オブジェクトと配列をフォームに反映して往復後も request の型が同じ。保存前後の構文エラーは変換されない。

Run: 対象の各テストを実行し FAIL を記録する。

- [x] **Step 4: 保存失敗・pagehide / pageshow を実装する。**

保存が使えない場合も入力と実行を続けられるようにする。内部ナビゲーション直前に保存を試み、失敗した場合だけ移動 UI を開く。未知・壊れた保存は案内して既定値に戻す。

pagehide は最後の snapshot と位置を保存し、実行中の表示状態・旧非同期応答を復帰画面に持ち越さない。必要な run 世代識別と AbortController を追加し、離れたページの応答が現在の画面を更新しないようにする。クライアントの取消で GPU 推論自体が確実に中断すると約束しない。

pageshow は既定値の再適用や自動再送を行わず、保存 DOM を維持する。復帰時には busy を健全な状態にし、token / モデル情報を更新する。スクロールはレイアウト構築後に戻す。イベントの二重登録を防ぐ。

- [x] **Step 5: GREEN、既存回帰、README を確認する。**

Run: `uv run pytest tests/test_playground_browser.py tests/test_guide.py -q`。

Run: `node --check app/static/draft-storage.js` と `node --check app/static/playground.js`。

README にガイド URL、保持範囲、入力だけの保存、不正 JSON の継続編集、origin / tab の範囲を記載する。タブ終了で秘密情報が必ず消えるとは案内しない。

- [x] **Step 6: コミットし独立レビューを受ける。**

対象だけ stage して `Preserve Playground drafts across guide navigation` としてコミット。レビュー重点は raw 保存、復元の順序、失敗時の導線、bfcache、非同期 race、現在の直接 Run の保持。

## 最終統合・公開の検証（コントローラー）

- [x] 全変更の独立レビュー。重大な指摘は元実装担当へ返し、修正と再検証を行う。
- [x] `uv run pytest -q`: 全テスト成功。Chrome が skip された場合は完了扱いせず、実行可能な既存環境で確認する。
- [x] 全 JavaScript の `node --check` と `git diff --check` を成功させる。
- [x] 検証済み変更を稼働プロジェクトへ統合。`systemctl --user restart laya_playground.service`、`/health` が 200 / model_ready=true を確認する。
- [x] LAN URL `http://192.168.1.10:8000/` と `/guide` を Chrome で開き、同じタブの往復、JSON の修正・直接 Run、ガイドのコピーと mobile を確認。実モデルの 3 形式の回答と CUDA / CPU fallback=0 を確認する。
- [x] `docs/documentation-verification.md` にテスト結果、レビュー、起動状態、実測範囲、残る制約を記録し、保存する。

## 計画の自己レビュー

設計の全章・公式参照・色/文字/PC/モバイル/アクセシビリティは Task 1。保持対象・原子的な復元・失敗・bfcache・非同期処理は Task 2。既存 UI/API 回帰とサービス反映は最終統合で検証する。保存 interface と利用側のフィールド名は一致している。初版対象外の検索・結果保存・例の自動適用は追加しない。

実装方法はすでにユーザーが選択したサブエージェント方式を継続する。実装計画のレビュー後に着手する。
