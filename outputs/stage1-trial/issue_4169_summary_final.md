# Issue #4169 要約: ジョブ実行時に JobExecution の全履歴を取得してしまう問題

## 概要

用語: 以降、「JobExecution」はジョブ実行、「JobInstance」はジョブインスタンスを指す。「再起動」は既存の JobInstance に対する新規 JobExecution の作成を指す。

- Issue: #4169（closed、起票者 glaz666、2022-07-29）
- ラベル: `in: core` / `type: enhancement` / `related-to: performance` / `for: backport-to-6.0.x`
- マイルストーン: 6.1.0-RC1
- 修正コミット: c702081236ee（2026-10-02）
- 関連 issue: #5495（コメント4で言及。最小再現例と比較基準が添付されているとされる）
- バックポート（6.0.x）が実施されたかどうかは、資料からは不明。

再起動のたびに、過去の JobExecution を全件取得していた。これを「最後の JobExecution 1件」だけで判定する形に変更した修正である。

## 問題

- 起票時の症状: `SimpleJobLauncher#run` で新しい JobExecution を作る際、そのジョブの過去の JobExecution を DB からすべて取得していた。実行時間とメモリ使用量が過去の実行回数に比例する。起票者は、実行回数に依存しない作りにすべきで、「最後の JobExecution だけで足りるのでは」と提案した。
- メンテナーの見解（コメント2）: 全件取得は複数の条件検証に必要なので、退行なしに改善できる方法があれば歓迎する。コメント3では、まず最小再現例の提供が求められた。
- コード位置の変化: 起票時のリンク先は `SimpleJobRepository` だが、コメント4（2026-08）によると現在の取得箇所は `TaskExecutorJobLauncher.createJobExecution` の再起動チェック（`jobRepository.getJobExecutions(jobInstance)`）である。今回の修正対象も後者である。
- #5495 について: 本文は資料になく、コメント4の記述による伝聞である。コメント4の報告によれば、実行回数が増えるとステートメント数も増えることが再現・比較されており、5.2.2 と 6.0.4 では増加の傾きが約8倍違う。本修正がこの事象を解消したかどうかは未確認である。

## 修正内容

対象: `spring-batch-core` の `TaskExecutorJobLauncher#createJobExecution` の再起動分岐。

- `jobRepository.getJobExecutions(jobInstance)` による全履歴の取得と全件走査での判定をやめ、`jobRepository.getLastJobExecution(jobInstance)` で取得した最後の1件だけを判定する形に変更した。
- 最後の1件に対する判定（実行中、UNKNOWN、完了済み、再起動不可など）で投げる例外の種類は、従来の同種の判定と同じである。最後の JobExecution が `null` の場合は `IllegalStateException`。
- 到達しないはずの重複した `getLastJobExecution` 呼び出しと分岐は削除された。

この変更は、diff 内のコメントにある前提に基づく。「新規 JobExecution は前の JobExecution がチェックを通過した場合にだけ作られるので、実行中または完了済みになりうるのは最後のものだけ」という前提である。これは実装者の想定であり、検証の記録は資料にない。

`getLastJobExecution` 側の SQL がどの範囲を読むかは、今回の diff からは確認できない。

## 利用者への影響

- 再起動チェックでの履歴全件取得をやめた。これが実行時間・メモリ使用量・DB アクセスに与える影響（実行回数への依存の有無や改善幅）は、計測結果が資料になく未検証である。
- 最後の1件に対する判定では、例外の種類・メッセージは従来と同じである。ただし、古い JobExecution のみが異常状態（RUNNING や UNKNOWN など）の場合は、従来は例外になりえたものが例外にならなくなる可能性があり、挙動が変わりうる。
- 公開 API については、diff 上は `TaskExecutorJobLauncher` 内部の再起動分岐の変更のみで、シグネチャの変更は確認できない。

## 補足・注意

- 追加したテスト（`TaskExecutorJobOperatorTests`）が確認する観点
  - 最後の JobExecution が実行中の場合（`JobExecutionAlreadyRunningException`）
  - 最後の JobExecution が完了済みの場合（`JobInstanceAlreadyCompleteException`）
  - 3回失敗した後の4回目で成功し、履歴が4件になる場合
- 未確認点（断定しない）
  - `getLastJobExecution` の「最後」が ID 順か作成日時順かは、diff からは判別できない。
  - 履歴の途中に RUNNING や UNKNOWN の古い JobExecution が残っている場合、判定対象が最後の1件になるため挙動が変わりうる。異常な状態のレコードが混在する環境では注意して確認したい。
