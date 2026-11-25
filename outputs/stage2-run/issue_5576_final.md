# Issue #5576 要約: マルチスレッドステップ／並列フローのワーカースレッドで `@JobScope` Bean が使えない問題
## 概要
`@JobScope` を付けた Bean は、`Job` を実行するスレッド以外から参照すると失敗します。この Issue は、`TaskExecutor` を指定したマルチスレッドステップと、`FlowBuilder#split(TaskExecutor)` による並列フローで、この問題が起きるバグを扱っています。修正は `spring-batch-core` で、ワーカースレッド側にジョブコンテキストを登録・解放する形で行われました。マイルストーンは 6.1.0-RC1 で、ラベルに `backport-to-6.0.x` が付いています。

## 問題
次の2つのケースで、`ScopeNotActiveException` / `IllegalStateException: No context holder available for job scope` が発生します。

1. `TaskExecutor` を指定したマルチスレッドステップのワーカースレッド
2. `FlowBuilder#split(TaskExecutor)` で並列フローを実行するスレッド

原因は、`JobSynchronizationManager` への登録が `AbstractJob#execute` からしか行われず、`ThreadLocal` ベースのため、ジョブを実行するスレッドにしか効かないことです。一方 `StepScope` は、`ChunkOrientedStep`、`StepContextRepeatCallback`、`AsyncItemProcessor` がワーカースレッドにステップコンテキストを登録しているため、この制限がありません。`JobSynchronizationManager` の javadoc には、ワーカースレッドを含む関与スレッドすべてでコンテキストを使えるようにするのは各 `Job` 実装の責務とありますが、上記2ケースでは満たされていませんでした。

期待される動作は、すべてのスレッドで同一の `@JobScope` Bean が解決され、ジョブが正常終了することです。報告環境は `main`（eab562ff…）、組み込み HSQL の JobRepository です。なお本件は #4782 で `@FlowScope` の要望と一緒に報告されたもので、本 Issue はジョブスコープの伝播だけを扱います。

## 修正内容
マルチスレッドステップ、並列フロー、非同期処理、パーティショニングの各スレッドで、ジョブコンテキストを登録（`JobSynchronizationManager.register(...)`）し、終了時に解放（`JobSynchronizationManager.close()`）するようにしました。クラスごとの詳細は参照先の差分を確認してください。なお `AbstractStep` の変更はパーティショニング時だけでなく、すべてのステップ実行に適用されます。

テストとして `JobScopeMultiThreadingTests` が追加されています。対象は、逐次ステップ（対照）、マルチスレッドステップ、並列フロー、`AsyncItemProcessor`、`ChunkTaskExecutorItemWriter`、パーティションステップで、ジョブが `COMPLETED` になることと、見えた `@JobScope` Bean のインスタンスが1つであることを検証します。

## 利用者への影響・対応
- マルチスレッドステップや `split` での並列フローで `@JobScope` Bean を使っていて上記例外が出ていた場合、修正版で動作する見込みです。
- 修正版は 6.1.0-RC1 です。`backport-to-6.0.x` ラベルはありますが、6.0.x のどの版に入るか、実際にバックポートされたかは入力からは不明です。
- 修正前の回避策、性能への影響、移行時の注意は入力に記載がありません。

## 補足
- 差分は Issue 本文の2ケースに加え、`AsyncItemProcessor`、`ChunkTaskExecutorItemWriter`、パーティショニングも対象にしています。Issue 本文はパーティショニングに触れていません。
- `JobSynchronizationManager.register` / `close` の内部実装（多重登録時の扱いなど）は差分に含まれず、不明です。
- 参照: https://github.com/spring-projects/spring-batch/issues/5576 、コミット 2f9e839dea2f、関連 #4782
