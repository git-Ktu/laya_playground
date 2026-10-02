# Laya Playground Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 日本語の Choice / Score / Noul を、multilingual モデルと GPU で実行できるローカル Playground と LAN API を提供する。

**Architecture:** `laya.serve.create_app(router=service)` の標準 API と単一推論ワーカーを再利用する。LayaService が Router のロード、入力検証、モデル固定、トークン計数、診断を担当する。HTML / CSS / vanilla JavaScript を同じ FastAPI アプリから配信する。

**Tech Stack:** Python 3.12、uv、Laya serve extra、FastAPI、PyTorch CUDA 12.6 wheel、pytest / httpx。フロントエンドに Anthropic 公式 Frontend Design スキルを適用する。

**Spec:** `docs/superpowers/specs/2026-10-01-laya-playground-design.md`

## Global Constraints

- 使用モデルは `convaiinnovations/laya-multilingual`、Router 呼び出しは `model="multilingual"`。
- 単発・batch の全経路で `max_len=8192`。別モデルや異なる max_len の指定は拒否する。
- モデルは起動時に 1 回ロード。1 プロセス、1 uvicorn worker。標準の CPU フォールバックを妨げない。
- uv / pyproject.toml / uv.lock のみを依存管理に使用。システム Python・CUDA・ドライバーを変更しない。
- Pascal 対応の CUDA 12.6 PyTorch wheel を明示的な uv index から取得し、動作確認したバージョンを固定する。
- API の標準 answer / usage / routing と batch results / total_usage 形式を維持する。
- DB、Docker、認証、SPA framework、フロントエンドのビルド工程を追加しない。
- 日本語主体、控えめなダークテーマ、本文全体をログへ出さない。
- 実際の検証 GPU は GTX 1070 / 8 GB。GTX 1070 Ti で検証したと報告しない。

## Review Focus

- 日本語 JSON、絵文字、引用符を含む入力を正常に扱い、curl コピーでも本文を壊さない。Task 1 / 3。
- 標準 batch が top-level max_len を無視するため、異なる budget 指定を推論前に拒否し、各内部 request に 8192 を渡す。Task 1 / 2。
- 質問の head が state budget を減らす場合、8192 以下の state でも切り捨て警告を表示する。Task 1 / 3。
- モデルロード失敗時にも Playground と info が利用でき、推論と health が説明付き 503 を返す。Task 2。
- CUDA 認識だけで GPU 推論成功と判断せず、推論中の CPU フォールバックも報告する。Task 1 / 4。

## ファイルと共通インターフェース

- `app/models/requests.py`: question、state、固定 model / budget の検証。
- `app/services/laya_service.py`: `LayaService(router_factory=None)`、`load() -> None`、`predict(state, questions, model=None, **kwargs) -> dict`、`predict_batch(requests, **kwargs) -> list[dict]`、`tokenize(state) -> dict`、`info() -> dict`。
- `app/api/policy.py`: 標準ルートをラップし、単発 / batch の model / max_len を確認する。Laya が既に提供する本文サイズ制限を維持する。
- `app/api/diagnostics.py`: `register_diagnostics(app, service) -> None`。GET /health、GET /info、POST /tokenize。
- `app/main.py`: `create_app(service=None) -> FastAPI` と uvicorn 用 `app`。実モデルロードは lifespan 中のみ。
- `app/templates/index.html`、`app/static/playground.css`、`app/static/playground.js`: フロントエンド。
- `tests/test_validation.py`、`tests/test_service.py`、`tests/test_api.py`、`tests/integration/test_model.py`。
- `scripts/verify_gpu.py`、`scripts/verify_http.py`、`README.md`、`docs/verification.md`。

## Task 1: 検証モデルと Laya サービス

**Files:** `pyproject.toml`、`uv.lock`、`.gitignore`、`app/models/requests.py`、`app/services/laya_service.py`、パッケージの `__init__.py`、`tests/test_validation.py`、`tests/test_service.py`。

**Interfaces:** 上記 LayaService を生成する。外部推論の代わりにテスト用 Router factory を注入できる。モデル未ロード、CUDA、OOM、推論失敗を区別するサービス例外を定義する。

- [x] 配布 Laya バージョンとインストールした API を公式ソースと照合する。`pyproject.toml` に Laya serve extra、PyTorch、pytest / httpx を設定し、torch 用 explicit cu126 index を指定する。Python 3.12 で `uv sync` を実行する。システムへの導入は行わない。
- [x] `test_rejects_invalid_inputs` をパラメーター化して先に作成する。空 state / questions、空 name / instructions、不正 type、choice.criteria 欠落、score.criteria 欠落・1 段階、異なる model / max_len を検証する。例: `with pytest.raises(ValueError): validate_request({"state": " ", "questions": valid_questions})`。
- [x] `uv run pytest tests/test_validation.py -q` を実行し、未実装による失敗を確認する。
- [x] `validate_request(body: dict, *, batch: bool = False) -> dict` を実装する。state は非空 str / dict / list、choice は非空 str→str 辞書、score は 2 つ以上の非空 str、noul は instructions。不要な推論ロジックは実装しない。
- [x] サービステストを先に作成する。`test_load_once`、`test_multilingual_and_8192_for_single_and_batch`、`test_rejects_8193_state_tokens_before_predict`、`test_json_japanese_state`、`test_preserves_usage_truncation`、`test_reports_cpu_fallback`、`test_classifies_inference_errors`。Spy Router の境界で呼び出し引数を確認し、返却結果とエラーをアサートする。
- [x] `uv run pytest tests/test_service.py -q` で未実装による失敗を確認する。
- [x] LayaService を実装する。Router は lazy import、`load()` は 1 回のみ実行する。`Router.load("multilingual")` を利用し、Agent.tok と Laya の state 直列化方式に合わせて正確に state を計数する。state tokens >8192 を拒否する。batch の各 request に model / max_len を設定し、`Router.predict_batch(..., batch_size=1)` を利用する。
- [x] 単一ロックでモデル操作と tokenization を保護する。推論後に actual device / model parameter device / fallback count を更新し、診断のスナップショットを info から取得可能にする。標準 usage は保持し、アプリ固有メタデータは追加フィールドに置く。ログはモデル、device、推論時間、分類されたエラーに限定する。
- [x] `uv run pytest tests/test_validation.py tests/test_service.py -q` を実行し、すべて成功することを確認する。

## Task 2: 標準サーバー統合と診断 API

**Files:** `app/main.py`、`app/api/policy.py`、`app/api/diagnostics.py`、`tests/test_api.py`。

**Interfaces:** Task 1 のサービスを `create_app(service=...)` に注入する。外部利用者は設計書記載の /v1/systemone、/v1/systemone/batch、/health、/info、/tokenize を使用する。

- [x] API テストを先に作成する。`test_health_ready` は 200 と model_ready=true、`test_health_unavailable` は 503 と原因、`test_info` は model / max_len / actual device / CUDA / GPU 名 / Laya version を確認する。
- [x] `test_three_question_types_and_japanese`、`test_batch_format_and_fixed_budget`、`test_rejects_explicit_batch_budget_override`、`test_invalid_input_422`、`test_load_failure_keeps_info_available`、`test_classified_service_errors`、`test_inference_timing_headers` を追加する。実モデルのダウンロードを起こさない注入サービスを使用する。
- [x] `uv run pytest tests/test_api.py -q` で未実装による失敗を確認する。
- [x] `laya.serve.create_app(router=service)` を利用する。標準 route の endpoint を包む `PolicyRoute` で body の fixed model / max_len と構造を検証する。上限超過本文を無制限に read せず、標準の capped reader とサイズ制限を維持する。batch で無視される top-level 指定もこの層で確認する。
- [x] lifespan で標準サーバーの終了処理を保持しながら service.load を worker thread で実行する。モデル利用不能でもアプリを起動し、health / 推論は 503。サービス例外を適切な HTTPException に変換し、標準サーバーの generic 500 による原因消失を避ける。
- [x] native /health と競合しない形で診断ルートを登録する。/info はキャッシュ済みスナップショットを返し、推論中にイベントループをブロックしない。/tokenize の blocking 処理は worker thread で行う。
- [x] `uv run pytest -q` を実行し、すべて成功することを確認する。

## Task 3: Frontend Design による Playground

**Files:** `app/templates/index.html`、`app/static/playground.css`、`app/static/playground.js`、`tests/test_api.py`、必要に応じて `tests/test_playground_browser.py`。

**Interfaces:** POST /v1/systemone と /tokenize、GET /info を fetch する。追加のフロントエンド依存やビルドを必要としない。

- [x] 取得した公式 Frontend Design の SKILL.md を全文読む。設計の token system と画面配置を次の方針で確認する。Palette: background `#171c24`、surface `#202834`、border `#465467`、text `#eef2f7`、action `#8edac8`、warning `#f1c177`。日本語本文は OS の日本語 sans-serif、JSON / curl のみ monospace。左揃えの入力と結果を並べ、狭い画面では縦配置にする。装飾より入力・結果の明確な対応を個性にする。
- [x] GET / のテストを先に追加し、200、UTF-8 HTML、静的 assets の配信を確認する。`uv run pytest tests/test_api.py -q` で失敗を確認する。
- [x] HTML / CSS を作成し、GET / と /static を登録する。日本語の初期 state と Choice / Score / Noul のサンプルを表示する。明確な label、focus、色以外のエラー表示、reduced motion と mobile layout を用意する。
- [x] JS に質問と criteria の追加・削除、重複 key の拒否、JSON state の parse エラー、Run / Ctrl+Enter、loading、API エラー、結果と Raw JSON、タイミング・device・token 情報の表示を実装する。確率の辞書 / リスト等はインストールした Laya の実際の形に合わせ、外部文字列は textContent で描画する。
- [x] state 編集時に文字数を即表示し、tokenize は debounce と応答世代番号で更新する。4000 以上を警告、8192 超を拒否する。モデル利用不能では計数不能を明示する。結果の usage.truncated / state_tokens_dropped も警告する。
- [x] JSON / curl コピーを実装する。JSON は UTF-8 のまま、curl は shell の単一引用符を安全に処理する。接続先 origin を編集可能にし、localhost の場合は LAN IP に変更する案内を表示する。
- [x] 利用できるブラウザツールで、日本語入力、3 種質問、criteria 編集、Run / Ctrl+Enter、エラー、Raw JSON、コピー、狭い画面を操作する。スクリーンショットで見直す。ブラウザがなければ追加テスト依存を uv の dev group にのみ導入し、利用可否と検証範囲を記録する。
- [x] `uv run pytest -q` と JavaScript の構文チェックを実行し、失敗を修正する。

## Task 4: 実モデル・GPU・HTTP 検証と README

**Files:** `scripts/verify_gpu.py`、`scripts/verify_http.py`、`tests/integration/test_model.py`、`README.md`、`docs/verification.md`。

**Interfaces:** Task 1 の実サービスと Task 2 の HTTP API を使用する。integration test は `uv run pytest -m integration` の明示実行のみ。通常の pytest では実モデルをロードしない。

- [x] integration test を実推論前に作成する。multilingual のモデルロード、日本語の Choice / Score / Noul の結果型と範囲、batch 結果数、実 device、fallback の有無をアサートする。未知のゼロショット精度を特定ラベルの必須一致として扱わない。
- [x] GPU 確認スクリプトを実装する。torch version / CUDA runtime / is_available / GPU name / capability / arch list、CUDA tensor 演算、Agent と model の device、推論前後の fallback count を記録する。GPU を要求した検証で CPU に fallback した場合は成功として終了しない。
- [x] `uv sync --locked`、`uv run python scripts/verify_gpu.py`、`uv run pytest -m integration -q` を実行する。Hugging Face から初回モデルを取得し、互換性・ロード・CUDA の問題は原因を調べて修正する。
- [x] `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` を起動し、curl で /、/health、/info、単発の日本語 request、batch request を確認する。HTTP スクリプトでも answer の形と diagnostic 値を確認する。
- [x] max_len=8192 の呼び出しをサービスと実推論で確認する。実 token 長が長い場合の切り捨て・VRAM・fallback を記録する。設定値の確認と8192 token 級の実行を混同しない。
- [x] LAN IP を確認し、同一ホストの LAN アドレスからのアクセスを検証する。別端末へのアクセス権がない場合は、別端末からの到達確認は未実施と明記する。不要な firewall 変更はしない。
- [x] 日本語 README に全 endpoint、セットアップ、起動、初回ダウンロード、LAN、JSON と curl、日本語サンプル、long context / head budget、Pascal wheel、OOM / CPU fallback / download failure を記載する。
- [x] `uv run pytest -q` と `uv sync --locked` を最終実行する。実測結果を docs/verification.md に保存する。設計の各要件と差分を確認し、実装手順に沿った最終レビューを行う。

## 計画の確認と実行方法

設計書の各要求は Task 1〜4 に対応済み。Frontend Design は Task 3、実機検証は Task 4 に含める。

実行方法は **Native（このチャットで主担当が順に実装）を推奨**する。単一モデルのサービス、標準サーバー拡張、UI が共通インターフェースに依存するため、担当を分けず進めることで調整を減らせる。ユーザーは計画を確認し、サブエージェントによる実装と独立レビューを選択した。各タスクの実装・レビューと全体レビューを実施済み。

状態: 設計とサブエージェント方式を承認済み。全タスクを実装・検証・レビュー済み。最終通常テスト105件成功。実測と未検証範囲は docs/verification.md、軽微な残件は docs/review-notes.md に記録。
