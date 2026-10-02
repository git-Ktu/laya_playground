# ユーザー systemd サービスの検証（2026-10-02）

- 設定: `~/.config/systemd/user/laya_playground.service`。
- 原本: `deploy/systemd/laya_playground.service`。登録済みファイルとの一致を確認。
- `systemd-analyze --user verify`: 成功。
- 旧 Codex バックグラウンド起動の uv / uvicorn プロセスを停止。
- `systemctl --user enable --now`: 成功。ユーザーサービスの自動起動が有効。
- `systemctl --user stop`: inactive、MainPID=0、8000 番ポートの待受なしを確認。
- `systemctl --user start`: active (running)、systemd の cgroup 配下に単一サーバーを確認。
- `/health`: 200、model_ready=true。Playground HTML、`/info`、tokenize も成功。
- `uv run --no-sync python scripts/verify_http.py`: 成功。Choice / Score / Noul の単発・batch 推論を確認し、CUDA 動作・CPU fallback=0 を確認。
- `Linger=yes` は既存設定。ログアウト後の継続・OS 起動時のユーザー systemd 起動が有効。実際の OS 再起動は行っていない。

HTTP 検証の一時出力: `/tmp/laya-systemd-http-verification.jsonl`。

アプリケーションコード・依存関係の変更はない。起動・停止・ログ参照の手順は README の「ユーザーサービスとして運用する」に記載。
