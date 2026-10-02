# Laya ローカル Playground

日本語の文章・JSON から Choice（選択）、Score（段階評価）、Noul（true の確率）を試す FastAPI + HTML/JavaScript アプリです。モデルは **convaiinnovations/laya-multilingual**、Router 名は `multilingual`、全推論の `max_len` は **8192** 固定です。別モデルや異なる上限の指定は 422 で拒否します。

操作・設定の日本語ガイドは `/guide` で読めます。状態・質問の設定、Choice / Score / Noul、結果の読み方、コピーできる例題を掲載しています。既存の `/docs` は API リファレンス（OpenAPI）、`/openapi.json` は API スキーマです。Playground のヘッダーと章ヘルプから同じタブで移動できます。

入力は同じ origin・同じタブの `sessionStorage` に保持します。ガイドへの往復、Back / Forward、再読み込み後も、入力形式、状態・質問・criteria の順序、非表示のフォームと JSON 欄、接続先 origin、API リクエストの開閉、作業位置を復元します。JSON の構文エラー、重複名、空欄もそのまま保持され、戻って続きを編集できます。

保存するのは入力だけです。結果、token 数、モデル情報、実行中状態は保存せず、復帰後にモデル情報と token 数を確認します。推論を自動再送しません。実行中に移動するとブラウザーで応答の受け取りを取り消しますが、サーバーの GPU 推論自体の中断は保証しません。

localhost / LAN IP / ポートが異なると保存領域も異なります。別タブや端末へ同期せず、サーバーへ下書きを保存しません。保存が使えない場合も編集と Run を続けられます。内部リンクで移動する際には「このまま移動」「戻る」を選べる案内を表示します。壊れた保存データは使用せず、案内と既定の入力を表示します。タブ終了後の永続保存は行いませんが、ブラウザーのセッション復元により入力が復活する場合があるため、タブ終了で秘密情報が確実に消えるとは保証しません。

## 配置

`/home/server/work_space` は各プロジェクトの親ディレクトリです。このプロジェクトのコード、Git 管理、仮想環境、テスト、ドキュメントは `laya_playground/` 内にまとめています。以下のコマンドはプロジェクトのディレクトリで実行してください。

## セットアップと起動

Ubuntu、Python 3.12、uv、NVIDIA GPU と対応ドライバーを用意してください。

```sh
cd /home/server/work_space/laya_playground
uv sync --locked
uv run python scripts/verify_gpu.py
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

初回起動は Hugging Face からモデルをダウンロードするため時間がかかります。通常の Hugging Face キャッシュを使います。ネットワーク・空き容量・Hub の制限を確認してください。必要なら環境変数 `HF_TOKEN` を設定します。ダウンロードまたはロード失敗時はサーバーを起動して `/health` と推論を 503 にします。原因を解決してアプリを再起動してください。リクエストごとの再ロードはしません。

モデルは起動時に一度ロードします。**1 プロセス、1 worker** で起動してください。ブラウザは [localhost:8000](http://localhost:8000/) を開き、状態と質問を編集して Run / Ctrl+Enter を押します。Raw JSON、確率、token 数、推論時間、実 device を確認できます。

入力形式で JSON を選ぶと、「状態 JSON」「質問 JSON」の2欄が表示されます。状態には state の値（文章は `"配送が遅れています。"` のように引用符付きの JSON 文字列、データは空でないオブジェクト・配列）、質問には質問名をキーにした辞書を貼り付けます。Run / Ctrl+Enter はその時点の両欄を検証して直接実行します。不正な入力は欄ごとに原因を表示し、推論を開始しません。

Plain text に切り替えると両欄を検証して状態・質問フォームへまとめて反映します。片方でも不正なら JSON モードを維持し、入力を保持します。オブジェクト・配列の状態はフォームでも整形 JSON として編集し、送信時の型を保持します。JSON に切り替えると最新のフォームを2欄へ反映します。リクエスト表示、JSON コピー、curl コピーは現在の入力を使用します。再取り込みにはコピーしたリクエストの `state` と `questions` をそれぞれの欄に分けてください。

LLM には、次のように **状態 JSON** と **質問 JSON** の2つのコードブロックを生成するよう依頼できます。

状態 JSON:
```json
{"body": "配送が遅れています。早く届けてほしいです。"}
```

質問 JSON:
```json
{
  "感情": {"type": "choice", "instructions": "感情を分類してください。", "criteria": {"positive": "肯定的", "negative": "否定的"}},
  "緊急度": {"type": "score", "instructions": "緊急度を評価してください。", "criteria": ["低い", "高い"]},
  "改善要望": {"type": "noul", "instructions": "改善を求めていますか。"}
}
```


## ユーザーサービスとして運用する

`deploy/systemd/laya_playground.service` をユーザーの systemd に登録して運用できます。仮想環境は先に `uv sync --locked` で用意してください。サービスはその環境から直接起動し、起動時の依存関係の更新は行いません。Web アプリと API は同じ 1 プロセスで提供します。手動起動のサーバーは停止してから登録してください。

```sh
mkdir -p ~/.config/systemd/user
cp deploy/systemd/laya_playground.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now laya_playground.service
```

ユーザー権限で操作できます。以下のコマンドに `sudo` は不要です。

```sh
systemctl --user start laya_playground.service
systemctl --user stop laya_playground.service
systemctl --user restart laya_playground.service
systemctl --user status laya_playground.service
journalctl --user -u laya_playground.service -f
```

`enable` によりユーザーの systemd 起動時に自動起動します。このサーバーの `Linger` は有効なので、ログアウト後も継続し、OS 起動時にもユーザーの systemd が立ち上がります。別環境では `loginctl show-user "$USER" -p Linger` で確認してください。自動起動を解除する場合は `systemctl --user disable --now laya_playground.service` を使います。

異常終了時は 5 秒後に再起動し、短時間の繰り返し失敗では再起動を止めます。原因を直した後は `systemctl --user reset-failed laya_playground.service` と `start` で復旧できます。モデルロードが完了するまでは HTTP を待つため、`active` に加えて `curl --fail http://127.0.0.1:8000/health` で利用可能か確認してください。ロード失敗時は `/health` が 503 を返すため、ログを確認してサービスを再起動します。

必要な場合のみ `~/.config/laya_playground/server.env` を作成し、`HF_TOKEN=...` などの環境変数を記述できます。このファイルはサービスから任意で読み込みます。秘密情報を含む場合は `chmod 600` で保護してください。通常は既存の Hugging Face キャッシュを使用します。

## LAN で使う

`hostname -I` でサーバーの LAN IP を確認し、同じ LAN の端末から `http://SERVER_IP:8000/` を開きます。今回の同一ホスト検証先は [192.168.1.10:8000](http://192.168.1.10:8000/) です。別端末からの到達は未検証です。接続先 origin は開いたブラウザの origin を初期値にします。localhost でコピーした curl は別端末で使う前に IP を変更してください。

通常の HTTP LAN 接続で Clipboard API が使えない場合は従来のコピー処理を試し、失敗時には選択済みテキストを表示します。Ctrl+C / ⌘C で手動コピーできます。認証はありません。アクセスできるネットワークの端末から API を利用できます。

## Endpoint

| Method | Path | 用途 |
|---|---|---|
| GET | `/` | Playground |
| GET | `/guide` | 日本語の操作・設定ガイド |
| GET | `/health` | モデル利用可能なら 200、ロード失敗なら 503 |
| GET | `/info` | model_id、8192 上限、要求/実 device、パラメータ device、GPU、バージョン、fallback 回数 |
| POST | `/tokenize` | `{ "state": "日本語" }` の正確な state token 数 |
| POST | `/v1/systemone` | `{state, questions, model?, max_len?}` の単発推論 |
| POST | `/v1/systemone/batch` | `{states, questions, model?, max_len?}` の batch 推論 |
| GET | `/docs` | OpenAPI 対話式ドキュメント |
| GET | `/openapi.json` | API schema |

state は非空の文字列・JSON オブジェクト・配列です。questions は名前から質問への辞書で、type と非空 instructions を必須とします。Choice の criteria は key → 説明、Score は最低 2 段階の説明リスト、Noul は criteria 不要です。空入力、不正な質問、8192 超の state token 数は 422。標準サーバーの本文・質問数・選択肢数制限も適用します。

## 日本語 curl 例

```sh
curl http://localhost:8000/v1/systemone \
  -H 'Content-Type: application/json' \
  --data-raw '{
    "state":"注文した商品が届かず、困っています。配送状況を確認してください。",
    "questions":{
      "分類":{"type":"choice","instructions":"問い合わせを分類してください。","criteria":{"配送":"配送の問い合わせ","その他":"その他"}},
      "緊急度":{"type":"score","instructions":"緊急度を評価してください。","criteria":["低い","普通","高い"]},
      "要対応":{"type":"noul","instructions":"担当者の対応が必要ですか。"}
    },
    "model":"multilingual","max_len":8192
  }'
```

単発の結果は標準の `model / answers / usage / routing` と追加の `diagnostics` です。Choice は `choice` に選択 key、Score は `score` に 0〜段階数−1 の実数、Noul は `noul` に 0〜1 の true 確率を返します。confidence、probabilities、legend も表示します。`model` は標準の `laya-rl-agent` になる場合があり、実 checkpoint は `routing.repo` と `diagnostics.model_id` で確認してください。

```sh
curl http://localhost:8000/v1/systemone/batch \
  -H 'Content-Type: application/json' \
  --data-raw '{"states":["配送が遅れています。",{"問い合わせ":"商品が届きました。"}],"questions":{"要対応":{"type":"noul","instructions":"担当者の対応が必要ですか。"}},"max_len":8192}'
curl http://localhost:8000/tokenize -H 'Content-Type: application/json' --data-raw '{"state":"日本語の文章"}'
curl http://localhost:8000/health
curl http://localhost:8000/info
```

batch は `results / total_usage` を維持し、各入力を `batch_size=1` で順次処理します。

## 長文と GPU の注意

8192 は設定上限であり、8 GB GPU で最大長が必ず収まる保証ではありません。4000 state tokens 以上では UI に精度低下の警告を出し、8192 超は実行を止めます。質問 instructions と criteria にも token を使います。モデルの **head budget**（標準設定）内に収まらない質問や、質問を含めた系列では state が8192 以下でも切り捨てが起き得ます。`usage.truncated / state_tokens_dropped / truncated_questions` を必ず確認し、質問と文章を短くしてください。8192 token 級の実行と設定値の確認は別です。実測は [検証記録](docs/verification.md) にあります。

GTX 1070 / Pascal（compute capability 6.1）で検証しました。GTX 1070 Ti ではありません。`torch==2.7.1+cu126` を CUDA 12.6 の明示 uv index で固定しています。ドライバーの nvidia-smi に表示される CUDA 13.0 はドライバーの最大対応で、PyTorch runtime は 12.6 です。システム Python、CUDA toolkit、ドライバーを変更しません。別の新しい torch wheel に変更すると Pascal 対応がなくなる可能性があるため、CUDA tensor 演算と実モデル推論で確認してください。

CUDA エラー・OOM 時は Laya 標準の CPU fallback を許可します。`/info` と結果の diagnostics に実 device、model_parameter_device、cpu_fallback_count を出します。GPU 検証スクリプトは CPU fallback を成功扱いせず非ゼロ終了します。OOM 時は文章・質問を短くして他の GPU 使用プロセスを確認し、必要ならアプリを再起動します。モデル利用不能・CUDA/OOM は分類付き 503、その他の推論エラーは 500 で返します。通常の起動コマンドで、起動・モデルロード・CUDA/GPU/device・推論時間・分類済みエラーをログに出します。リクエスト本文と例外全文をログには出しません。

## 検証

```sh
uv run pytest -q                    # mock/API/Chrome。モデルをロードしません
uv run pytest -m integration -q     # 明示したときだけ実モデル・GPU
uv run python scripts/verify_gpu.py
uv run python scripts/verify_http.py --url http://127.0.0.1:8000
```

Chrome の画面テストは `google-chrome` があると実行し、なければ skip します。今回の GPU、HTTP、LAN origin の実ブラウザ・スクリーンショットを含む記録は [docs/verification.md](docs/verification.md) です。
