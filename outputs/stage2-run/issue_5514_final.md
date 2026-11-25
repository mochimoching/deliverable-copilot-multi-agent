# Issue #5514 要約: 遷移が一致しない Flow で `JobFlowExecutor` の `StepExecution` が同一スレッド上の別 Job 実行へ漏れる問題
## 概要
Flow の遷移定義が step の `ExitStatus` を網羅していないと、その Job 実行の `StepExecution` が `JobFlowExecutor` 内の `ThreadLocal` に残ります。同じスレッドで次に動く Job 実行がそれを `ABANDONED` に更新してしまう不具合です(type: bug / in: core、マイルストーン 6.1.0-RC1、ラベル `backport-to-6.0.x`)。報告者は 6.0.3(本番)と 6.0.4(再現用サンプル)で確認しています。メンテナは有効なバグと認め、74975c506 で入ったリグレッションと思われると述べています。修正は commit 9ff78c2b7985 です。

## 問題
- 前提として、`ExitStatus` に対応する遷移がなく `FlowExecutionException: Next state not found ...` で Job が失敗するのは、報告者も認めるとおり仕様どおりの挙動です。問題はその後の副作用です。
- 原因は2点です。
  1. `JobFlowExecutor` の `stepExecutionHolder` が `static` な `ThreadLocal<StepExecution>` で、JVM 全体で共有されていた。
  2. `SimpleFlow.resume` で `nextState(...)` が `try` の外にあり、ここで例外が出ると `executor.close()` が呼ばれず、holder がクリアされなかった。`FlowJob.doExecute` も `finally` なしで再スローするため、他にクリアする箇所がない(issue の分析による)。
- 次の Job 実行が `StepState.handle` から `abandonStepExecution()` を呼ぶと、自分のものではない `StepExecution` を読み書きします。issue が報告する影響は次の3つです。
  1. 同じ Job が以後 step を実行しなくなる。`SimpleStepHandler.shouldStart` が `ABANDONED` で `false` を返し、「Step already complete or not restartable」となる。
  2. 同じスレッドで動く無関係な Job が、先の Job の `StepExecution` を `ABANDONED` にして壊す。
  3. スレッドプールでは各スレッドが古いコピーを保持するため、`OptimisticLockingFailureException` が、その行を所有しない Job で発生する。
- 再現には同一スレッドの共有が必要です。報告者は `ThreadPoolTaskScheduler`(9スレッド)と、デフォルトの `SyncTaskExecutor` を使う `JobOperator` で遭遇しています。

## 修正内容
commit 9ff78c2b7985 による挙動の変化は次の2点です。
- holder が Job 実行(executor)ごとに独立し、JVM 全体で共有されなくなった。
- 遷移が見つからず例外が出た場合でも executor が close され、holder がクリアされる。

あわせて、未一致遷移後の分離・再起動・クローズを検証する回帰テストが `FlowJobFailureTests` に追加されています。

## 利用者への影響・対応
- 影響を受けうるのは、`ExitStatus` の一部しか遷移を定義していない `FlowJob` を、スレッドを共有する形(スレッドプール、`SyncTaskExecutor` など)で繰り返し実行している構成です。
- 兆候として、issue には「Step already complete or not restartable, so no action to execute」のログ、`StepExecution` の `ABANDONED`、別 Job が絡む `OptimisticLockingFailureException` が挙げられています。
- 修正を取り込むには、該当コミットを含むバージョンへの更新が必要です。マイルストーンは 6.1.0-RC1、6.0.x へのバックポート予定ですが、実際の含有リリースは入力から確認できません。
- 遷移が未網羅であること自体は設定ミスで、修正後も該当 Job は失敗する想定です(推測: 差分は遷移の判定を変えていないため)。報告者の例では `.from(step).on("*").fail()` のような catch-all 遷移を置くと再実行できていますが、これは設計上の対策であり、本修正の代替ではありません。

## 補足
- 74975c506 の内容と、リグレッションが入ったバージョンは入力からは分かりません。
- バックポート先の具体的なバージョンとリリース時期は不明です。
- issue のコメントでは jjj-n が修正 PR を準備すると述べていますが、その PR と commit 9ff78c2b7985 の関係は入力からは確認できません。
- 出典: issue #5514、commit 9ff78c2b7985、報告者作成の MCVE(4シナリオ)。
