# レビュー記録

2026-10-02（Asia/Tokyo）。ユーザー承認のサブエージェント方式で、サービス、API、Playground、実機検証を各段階で独立レビューし、最後に全体レビューを実施した。

## 修正と確認

- tokenizer 例外の分類漏れを修正し、単発・batch・tokenize の回帰テストを確認。
- 本文編集中の Run トークン上限判定を、実行する本文のスナップショットに固定。Chrome の回帰テストを確認。
- Router の既定 bundled repo を使わず、要求の `convaiinnovations/laya-multilingual` を明示。実 GPU 推論の routing.repo を確認。
- LAN HTTP の Clipboard API 非対応時に、従来コピーと選択可能な手動コピーを用意。実 LAN origin と回帰テストを確認。
- ブラウザテストの保存先を pytest tmp_path に変更し、作業記録ディレクトリのない別配置先でも Chrome テストを確認。
- 通常の uvicorn 起動でアプリ INFO ログを有効化し、本文・生の例外文を出さず起動、モデル、CUDA/GPU、推論時間、分類済みエラーを記録。

最終修正の再レビューでは、必須の2件が解決済みで、新しい Critical / Important 指摘はなかった。

## 判断

全体レビューは既定 INFO ログの不足を Minor としたが、起動・モデル・device・推論ログはユーザーの明示要件なので必須修正として扱った。誤った判断の場合の影響は、運用ログの量が増えること。リクエスト本文はログに含まない。

## 軽微な改善点（未修正）

1. 推論後の診断更新で GPU device の取得自体が例外を出した場合、元の結果やエラーを置き換える可能性がある。検証では発生していない。直前の診断と主処理結果を保存する保護を追加できる。
2. 非常に深くネストした JSON state（レビューで約510階層を再現）は deepcopy の RecursionError により500になる。ネスト制限かコピー方法を改善するとクライアントエラーとして扱える。
3. health のHTTP status、info の期待値、検証スクリプトの質問 type 一致について、assertion を補強できる。保存された実結果は正しい値と型を示す。
4. JS/CSS の一部が長い行にまとめられている。保守性のための整形が残る。
5. Starlette/httpx TestClient の deprecation warning が1件ある。現行 lock でテストは成功するが、互換依存の更新が残る。

## 最終確認

主担当による最終確認: `uv sync --locked` 成功、`uv run --no-sync pytest -q` は **105 passed, 1 deselected, 1 warning in 16.54s**、JavaScript 構文確認成功。LAN アドレスの `/`、`/health`、`/info`、tokenize、日本語の単発3種とbatch2件も成功。standalone checkpoint、CUDA、CPU fallback 0 を応答で確認。

実モデル integration test は実装担当の検証で1件成功。GPU、ブラウザ、長文の詳細と未検証範囲は [verification.md](verification.md) を参照。

ローカル専用の新規 Git リポジトリなので、成果物を `codex/laya-playground` ブランチに保持している。共有リポジトリへの push や merge は行っていない。
