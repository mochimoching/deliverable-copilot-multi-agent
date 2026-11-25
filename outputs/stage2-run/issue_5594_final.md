# Issue #5594 要約: `ChunkOrientedStep` でチャンクトランザクションが未コミットのとき StepExecution が復元されない問題
## 概要
新チャンクエンジン `ChunkOrientedStep` で、チャンク処理とメタデータ更新が成功した後にトランザクションがコミットされなかった場合（例: `beforeCommit` での例外）、ジョブが `FAILED` ではなく `UNKNOWN` になり再起動できなくなる不具合です。`ChunkOrientedStep.java` を修正し、未コミット時にメモリ上の `StepExecution` を元の状態へ戻すようにしました。修正はコミット be85c66a1b72 で、マイルストーンは 6.1.0-RC1 です。

## 問題
- 報告環境は Spring Batch 6.0.5 / Spring Framework 7.0.9 で、main（6.1.0-SNAPSHOT）でも再現するとのことです。
- 再現手順: チャンクサイズ1で3件処理し、2件目の書き込み中に `beforeCommit` で `IllegalStateException` を投げる `TransactionSynchronization` を登録します。ロールバックは確認でき、1件目のコミットだけが残りますが、ステータスは `UNKNOWN` になります。
- 互換エンジン `chunk(1, transactionManager)` では `FAILED` になり再起動できますが、ネイティブの `chunk(1).transactionManager(transactionManager)` では失敗します。
- 原因: メモリ上の `StepExecution` の version が 3 に進む一方、ロールバックで DB 側は 2 に戻ります。最後のメタデータ保存で `OptimisticLockingFailureException`（wrong version (3), current version is 2）が発生し、`UNKNOWN` になります。
- コメントでは、問題は `beforeCommit` の例外に限らない、より広いものとされ、タイトルが変更されています。

## 修正内容
対象は `ChunkOrientedStep`（`doExecute`、`saveState`）と、新規テスト `ChunkOrientedStepCommitFailureIntegrationTests` です。

- **状態の退避と復元**: 各チャンクのトランザクション処理の冒頭で、`StepExecution` の状態（version、writeCount、filterCount、commitCount、`ExecutionContext` のコピー）を退避します。トランザクション完了時に、コミットされていなければ退避した状態へ復元し、rollbackCount を加算します。read/skip count は復元しません（読み込み済みで、skip は listener に通知済みのため）。
- **結果不明時の扱い**: トランザクション完了時の結果が不明な場合は、`StepExecution` を `BatchStatus.UNKNOWN` にし、`setTerminateOnly()` を呼びます。これにより再起動は拒否され、flow が次のステップへ進むこともありません。
- scan モードで skip 後に行う状態保存も同様に変更されています。
- 同期が無効なトランザクションでは、上記の登録を行いません。
- テストは、`concurrent` の true/false でパラメータ化した6本です。`beforeCommit` 失敗後の再起動、`ItemStream` の update 失敗、scan 中の `beforeCommit` 失敗、commit/rollback の結果不明時の再起動拒否、結果不明時に flow が止まることを検証します。`beforeCommit` 失敗のケースでは、`FAILED`、writeCount=1、commitCount=1、rollbackCount=1 となり、再起動後に 1,2,3 がそろうことを確認しています。

## 利用者への影響・対応
- `ChunkOrientedStep`（新チャンクエンジン）で、`beforeCommit` の失敗や commit 失敗が起こりうる構成が対象です。修正後は、確実にロールバックされた場合に `FAILED` となり、最後にコミットされた地点から再起動できます。
- commit/rollback の結果が不明な場合は `UNKNOWN` になり、再起動は拒否されます。チャンクの書き込みが反映されたか不明なため、手動介入なしに再起動すべきでないとコードコメントに記載されています（diff のコメントに基づく）。
- 利用者側の設定変更が必要かどうかは、入力に記載がありません。

## 補足
- ラベルに `for: backport-to-6.0.x` がありますが、実際のバックポートや対象バージョンは入力から確認できません。
- issue 本文の外部ブランチの修正案と、採用された diff の差異は入力から断定できません。本要約は diff に基づきます。
- 報告者は、全テスト通過などの検証結果を自己申告しています。
- 関連: #5199、#5182 は 6.0.2 で修正済みで、本件はその後の、処理成功後のメタデータ更新またはトランザクション完了時の失敗とされています。
- 出典: https://github.com/spring-projects/spring-batch/issues/5594 、https://github.com/spring-projects/spring-batch/commit/be85c66a1b72e6a8200ca5429e81ae3636333043
