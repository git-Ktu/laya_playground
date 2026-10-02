# 日本語ガイドと入力保持の検証（2026-10-02）

## 公開内容

- 日本語ガイド: `http://192.168.1.10:8000/guide`。
- Playground: `http://192.168.1.10:8000/`。
- 既存 `/docs` は OpenAPI の操作画面として維持。
- 状態・質問・Choice / Score / Noul・結果・例題・制限・API の 10 章を掲載。
- 参照情報は公式リポジトリとモデルの公式ページのみ。
- 同じタブ・同じ origin の sessionStorage で編集状態を保持。Plain text、JSON の raw 文字列、不完全な質問、構文エラー、順序、型、表示モードを復元する。結果や実行中状態は保存しない。

## 自動検証

統合後の `/home/server/work_space/laya_playground` で実行:

- `uv run --no-sync pytest -q`: **142 passed, 1 deselected, 1 warning（58.53 秒）**。
- Chrome のテストは実行され、skip はなし。実モデル専用 integration テストは通常設定どおり除外。
- guide.js / draft-storage.js / playground.js の `node --check`: 成功。
- `git diff --check`: 成功。
- 公開例は実際の validator で確認。例題が常に期待した分類になるという保証はしない。
- 通常の往復・reload・Back / Forward、保存禁止・容量不足・壊れた保存値、遅延した token / inference 応答、コピーのフォールバック、閉じる・Escape・フォーカス復帰を確認。

既存の Starlette / httpx 非推奨警告が 1 件残る。依存関係変更は本機能の範囲に含めていない。

## 独立レビュー

- ガイド実装 `7ca8f9d`: 仕様・品質とも承認。
- 入力保持 `213beaf`: 仕様・品質とも承認。
- 全変更レビュー: Critical / Important の指摘なし。
- コピー表示と手動コピー画面の閉じる操作を `c0619cf` で修正。限定再レビューで両件解消・新たな問題なしを確認。
- 新規ガイド HTML / CSS のコンパクトなソース整形は軽微な保守性改善として残る。動作に関する未解決指摘はない。

実モデルの GPU 推論取消、タブ間同期、永続履歴、高度な Noul 設定の Plain text 変換、固定の正解・本番閾値は承認済み設計の対象外。

## 実サービス・LAN ブラウザー

検証済みブランチをローカルへ fast-forward で統合し、`systemctl --user restart laya_playground.service` を実行した。

- サービス: active / running。Web と API は同じユーザーサービスで提供。
- `/health`: 200、model_ready=true。
- `/info`: `convaiinnovations/laya-multilingual`、max_len=8192、CUDA、CPU fallback=0。
- 既存 `/docs`: 200。
- 実 Chrome で LAN origin のガイドと Playground の往復を確認。
- Plain text の状態を往復後に確認。JSON の両欄に構文エラーを含む書きかけを入れ、往復・再読み込み後の文字列一致を確認。
- JSON を修正して直接 Run。Choice / Score / Noul が返り、CUDA / CPU fallback=0 を確認。
- Plain text に戻すと状態と 3 つの質問が反映される。
- PC 1440px、モバイル 390px のガイド表示を確認。ページ全体の横溢れなし。

実測スクリプトと成果物（このホストの一時ファイル）:
`/tmp/laya-documentation-live-check.py`、`/tmp/laya-documentation-live-result.json`、`/tmp/laya-documentation-live.png`、`/tmp/laya-guide-live-desktop.png`、`/tmp/laya-guide-live-mobile.png`。

## 検証の範囲

Chrome の通常の履歴移動は動作確認できたが、この自動化環境は自然な bfcache 復帰を使用しなかった。persisted pagehide / pageshow をブラウザー内で直接発火し、遅延応答に対する復帰処理を確認した。自然な bfcache が全ブラウザーで選ばれることを実測済みとは扱わない。

LAN 接続は同一ホストからサーバーの LAN IP へアクセスした結果。別端末からの到達と OS の再起動は行っていない。

## 実装中の判断

Noul の `confidence` の解説を、インストール済み Laya 0.3.22 の実装に合わせて訂正した。Choice / Score は分布の集中度、Noul は max(P(true), P(false))。根拠は laya/agent.py:1041–1084。設計書の対応する 1 項目も修正した。もしこの根拠に誤りがあれば解説と設計書の再修正が必要になる。

## ページ切替リンクの位置統一（2026-10-02）

共通 navigation.css を追加し、両ページのリンクに固定幅の操作領域を確保した。PC は右上、モバイルはタイトル下の同じ行に配置し、両ヘッダーを sticky にした。現在地の太字でもリンク位置がずれない。

- 実装: `ce25397`。独立レビューで問題なし。
- 全テスト: 146 passed、1 deselected、既存警告 1 件（66.93 秒）。
- 稼働中 LAN ページを Chrome で確認。1440 / 1920 / 390 / 320px の両ページでリンクの x / y / 幅 / 高さが一致した。
- PC のリンク y=26px、モバイルのリンク y=70px、幅=100px、高さ=24px。
- スクロール・復元後の座標と入力保持を自動テストで確認。実サービスでの往復も入力を保持した。
- HTML / CSS の変更のためサービス再起動は不要。サービスは active。Playground の副題とモデル状態はリンクとは別の行に保持する。
