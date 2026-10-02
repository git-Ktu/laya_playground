# 状態・質問 JSON 編集機能の確認（2026-10-02）

ユーザー承認の設計に従い、Frontend Design スキルを使って既存ページの JSON モードへ状態と質問の2欄、共通の適用、未適用の編集を破棄する操作を追加した。Plain text のフォームと結果表示を維持し、API・モデル設定は変更していない。

実装サブエージェントの RED / GREEN と、別担当の仕様・品質・変更全体の独立レビューを実施。Critical / Important 指摘なし。通常テストは116件成功、うちChromeテスト17件。実モデル test は通常実行から除外している。既存のStarlette/httpx警告が1件ある。

主担当が `http://192.168.1.10:8000/` に Chrome で接続し、件名・本文を持つ日本語メールのJSON stateとChoice / Score / Noulの質問辞書を貼り付けて適用。その後Runで実推論を確認した。回答3件、routing.repo=`convaiinnovations/laya-multilingual`、actual_device=`cuda`、CPU fallback count=0。Plain textへ戻すとstateは元のオブジェクトと一致し、質問3件をフォームで確認できた。

JSON欄の状態にはstateの値、質問には質問名をキーにした辞書を入力する。全文requestをコピーした場合はそのstate / questionsをそれぞれ取り出して貼り付ける。未適用の編集はモード切り替えでも残り、適用または明示的な破棄までRun / Ctrl+Enterを止める。

## 軽微な残件

- 不正なJSONを適用した後で「未適用の編集を破棄」を押すと、エラー文は消えるがaria-invalidと警告枠が残る場合がある。データ復元と実行は正常。
- JSON文字列stateのCRLFは、フォームのtextareaへ反映するとLFへ正規化される。文字列の型と通常の文章内容は保持するが、改行コードの完全一致が必要な用途には制約がある。

通常の段落・構造化メールを使う今回の機能に対し、独立レビューは両方とも非ブロッキングと判定した。既存アプリの残件は [review-notes.md](review-notes.md) を参照。
