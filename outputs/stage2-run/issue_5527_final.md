# Issue #5527 要約: リトライ未設定の scan モードで出る誤解を招くログの修正
## 概要
`ChunkOrientedStep` で、skip 対象の例外により chunk の書き込みが失敗すると、本来は想定どおりの skip/scan 遷移であるにもかかわらず、INFO/ERROR レベルでスタックトレース付きのログが出ていました。この修正(コミット `869421c71f7d`)でこれらを DEBUG に下げ、文言を実態に合わせ、`RetryException` ではなく元の例外を添付するようにしました。差分上はログ出力のみの変更で、テストで skip 成功時の結果(`COMPLETED`、`SkipListener` が1回呼ばれる)を確認しています。

## 問題
- 再現条件(issue より): writer が特定のアイテムで skip 対象の例外(`DeliberateSkipException`)を投げ、`.retryable(...)` は未設定。`SkipListener` は1回だけ呼ばれ、ジョブは `COMPLETED` になります。
- それでも `ChunkOrientedStep` は次のようなログを出していました。
  - INFO: `Retry exhausted, entering scan mode for next transaction`(`RetryException` 付き)
  - ERROR: `Rolling back chunk transaction`(無条件、例外付き)
  - INFO: `Rollback complete, scan will execute in next transaction`
  - INFO: `Executing scan in new transaction after rollback`
- 問題点:
  - リトライ未設定ではデフォルトのリトライポリシーは0回リトライのため、"Retry exhausted" は誤解を招く。実際は「書き込みが失敗し、skip ポリシーが例外を許容した」だけ。
  - skip/scan に伴うロールバックは想定内の動作なのに、ERROR として出力されていた。
- issue 本文によれば、非推奨の `TaskletStep` / `FaultTolerantChunkProcessor` 経路では同等の遷移が例外引数なしの DEBUG で出ており、経路間で差があります。また、v5 との差についてもメンテナ(fmbenhassine)がコメントで認めています。

## 修正内容
変更対象は `spring-batch-core` の `ChunkOrientedStep.java` と、新規テスト `ChunkOrientedStepSkipLoggingTests.java` です。

ログの変更点:
- skip/scan 遷移に関するログ(scan 実行、scan 完了、ロールバック完了、書き込み失敗時の scan 移行)を INFO/ERROR から DEBUG に変更し、文言を実態に合わせました。
- skip に伴う想定内のロールバックでは ERROR が出なくなります。
- skip 可能な書き込み失敗では、`RetryException` ではなく元の例外を添付します。
- ERROR が残るのは、scan 中の失敗や skip 不可の例外など、実際にステップが失敗するケースです。skip 不可の場合の文言は `Chunk write failed with an exception that cannot be skipped` に変わります。

追加テスト(`ChunkOrientedStepSkipLoggingTests`):
- skip 成功時: ステップが `COMPLETED`、`SkipListener` が1回、`writeSkipCount` が1で、INFO 以上のログが出ないこと。DEBUG は出ること。
- skip 不可の例外: ステップが `FAILED` になり、ERROR が出ること。

## 利用者への影響・対応
- 差分上は、変わるのはログ出力のみです。テストでは skip 成功時の `COMPLETED`、`SkipListener` の1回呼び出し、skip 回数を確認しています。
- skip 発生時に INFO/ERROR とスタックトレースが出なくなります。skip の詳細は `ChunkOrientedStep` のロガーを DEBUG にすれば確認できます。
- ログ文言を監視・検索条件にしている場合、旧文言(`Retry exhausted ...` など)は変わるため、見直しが必要になる可能性があります(推測。入力に運用上の言及はありません)。

## 補足
- 修正バージョン: issue のマイルストーンは 6.1.0-RC1、ラベルに `backport-to-6.0.x` があります。実際にバックポートされたかは入力からは分かりません。
- コメントにある seanxuu のドラフト PR #5530 と、このコミットの関係は入力からは不明です。
- リファレンスや移行ガイドの更新は差分に含まれていません。
- 出典: https://github.com/spring-projects/spring-batch/issues/5527 / https://github.com/spring-projects/spring-batch/commit/869421c71f7d80274db40331eaa4284573b33eba
