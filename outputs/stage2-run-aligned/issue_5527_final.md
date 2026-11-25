*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

[#5527](https://github.com/spring-projects/spring-batch/issues/5527) は、フォールトトレラントな `ChunkOrientedStep` で、スキップが正常に成功しているにもかかわらず、誤解を招くログが `INFO` / `ERROR` で出力される問題です。

報告された状況:
- ライターが、報告者が用意したスキップ用の例外(`DeliberateSkipException`)をスローし、その例外をスキップ対象として設定している
- `.retryable(...)` は未設定のため、デフォルトのリトライポリシーはリトライを0回しか行わない
- `SkipListener` は1回だけ呼ばれ、ジョブは `COMPLETED` で正常終了する

それでも `ChunkOrientedStep` は次のログを出力します。

- `INFO`: `Retry exhausted, entering scan mode for next transaction`(`RetryException` 付き)
  - リトライを設定していないのに「リトライ枯渇」と表現しており、誤解を招く
  - `RetryException` は、リトライ処理が元の例外をラップして投げる例外です
- `ERROR`: `Rolling back chunk transaction`(例外のスタックトレース付き)
  - スキップ/スキャンの流れで想定内のロールバックでも、無条件に `ERROR` で出力される

非推奨の `TaskletStep` / `FaultTolerantChunkProcessor` では、同じ遷移は `DEBUG`・例外引数なしで出力されていました。

## 原因

`ChunkOrientedStep` のスキャンモードは、チャンクの書き込みがスキップ可能な例外で失敗したときに、そのチャンクをロールバックする仕組みです。その後、アイテムを1件ずつ別トランザクションで再処理して、問題のアイテムを特定・スキップします。

この「スキップに伴う想定内のロールバックと再実行」を、障害や異常と区別せずにログ出力していたことが原因です(`writeChunk`、`processChunkConcurrently` / `processChunkSequentially`)。リトライが0回でも「リトライ枯渇」の文言が使われ、スキャンの開始・完了も `INFO` でした。

issue のコメントでは、メンテナーの fmbenhassine 氏が「確かにv5とは違いがある。ログレベルは見直すべき」と述べています。

## 対応方針

修正コミット [869421c71f7d](https://github.com/spring-projects/spring-batch/commit/869421c71f7d80274db40331eaa4284573b33eba)(2026-09-30)で、`ChunkOrientedStep` のログが次のように変更されています。スキップ件数や `SkipListener` の呼び出しといった動作自体は変わりません。

- スキャン関連のログ(開始・完了・ロールバック・スキップ可能な書き込み失敗)は `DEBUG` に下げました。主な変更は次の2件です。
  - `INFO` `Retry exhausted, entering scan mode for next transaction` は、`DEBUG` `Chunk write failed with a skippable exception, entering scan mode for next transaction` になり、`RetryException` ではなく原因例外を添付します。
  - `ERROR` `Rolling back chunk transaction` は、`DEBUG` `Chunk transaction rolled back, scan will execute in next transaction` になります。
- スキップ不可の書き込み失敗は `ERROR` のままで、文言だけ `Chunk write failed with an exception that cannot be skipped` に変わります。

スキャンに移行する想定内のロールバックでは `ERROR` を出さず、スキャン自体の失敗などステップが実際に失敗する場合だけ `ERROR` を出します。並列(`processChunkConcurrently`)と逐次(`processChunkSequentially`)の両方が対象です。スキップ時に `INFO` 以上のログが出ないこと、スキップ不可時に `ERROR` が出ることは、新規テスト `ChunkOrientedStepSkipLoggingTests` で確認しています。

### 業務への影響

- `INFO` / `ERROR` を監視・アラート対象にしている場合、正常にスキップされたジョブが障害に見える誤検知が減ります。
- スキップの発生を `INFO` 以上のログで追っていた場合、修正後は `DEBUG` にしないと見えなくなります。
- 非推奨パスから `ChunkOrientedStep` へ移行するとログの見え方が変わりますが、この差はリファレンスドキュメントや移行ガイドに記載されておらず、修正でも追加されていません。
- 6.0.x で修正がいつ入るかは不明です。ドラフト PR [#5530](https://github.com/spring-projects/spring-batch/pull/5530)(想定内のロールバックを `DEBUG` に絞る内容)と修正コミットの関係も不明です。

## バグの発生タイミング

- 発生バージョンは不明です(報告は Spring Batch `6.0.5`、Spring Boot `4.1.1`)。
- 発生コミットは特定できていません。コメントでは v5(`FaultTolerantChunkProcessor` 系)との違いが挙がっていますが、`ChunkOrientedStep` の導入時期は分かりません。
- 修正コミットは [869421c71f7d](https://github.com/spring-projects/spring-batch/commit/869421c71f7d80274db40331eaa4284573b33eba) です(発生コミットではありません)。
- マイルストーンは 6.1.0-RC1 です。`for: backport-to-6.0.x` ラベルがありますが、バックポート済みかは不明です。
