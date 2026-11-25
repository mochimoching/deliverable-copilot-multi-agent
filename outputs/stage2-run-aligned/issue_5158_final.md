*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

リモートパーティショニングのジョブで、コントローラー停止中にワーカーのパーティションがすべて完了することがあります。その後コントローラーを再起動すると、アグリゲーターに空の `StepExecution` リストが渡されます。

報告者によれば Spring Batch 5 でも発生します。ラベルは `type: bug` / `in: integration`、マイルストーンは 6.1.0-RC1、状態は closed で、報告時の環境は Spring Boot 4.0.0 / Spring Batch 6.0.0 / JDK21 です。

**用語補足**
- 以降、マネージャー（コントローラー）と書く場合は同じものを指します。
- 再起動時、COMPLETED 済みのパーティションは再実行されず、`SimpleStepExecutionSplitter` の `split()` は再実行が必要な実行だけを返す仕様です。

**業務への影響**
- 全パーティションが正常完了しているのに、再起動したジョブが失敗扱いになります（メンテナーの見解）。
- 一部だけ再実行された場合も、マネージャーステップの `writeCount` などの集約メトリクスが過小になります。例えば、1つ完了・1つ失敗で各3件書き込みの場合、1回目は FAILED で `writeCount` は6、修正前の再起動では COMPLETED で3になっていました。

関連: [#4831](https://github.com/spring-projects/spring-batch/issues/4831) と関連があるとコメントされています。再現サンプルは [SpringBatch6 の shutdownAggregator ブランチ](https://github.com/brian-mcnamara/SpringBatch6/tree/shutdownAggregator)（[該当の235行目](https://github.com/brian-mcnamara/SpringBatch6/blob/shutdownAggregator/src/main/java/com/example/batchpartitionbug/BatchPartitionBugApplication.java#L235)）です。

## 原因

`SimpleStepExecutionSplitter` は仕様どおり、完了済みを除いた再実行分だけを返しており、こちらは問題ではありません。`split()` が完了済みも返すと、`split()` を直接呼ぶ任意の `PartitionHandler` が完了済みの作業をワーカーに再ディスパッチしてしまうため、契約は変えられませんでした。

実際の原因は `PartitionStep` です。`PartitionStep` は、`PartitionHandler` の戻り値を集約の入力としても使っていました。再起動時の戻り値は再実行分だけなので、完了済みのパーティションが集約から漏れました。

さらに `RemoteStepExecutionAggregator` が、現在の `JobExecution` に属さない実行をすべて除外していました。そのため、過去の `JobExecution` で完了したパーティションを渡しても集約されませんでした。

## 対応方針

マイルストーン 6.1.0-RC1 の修正コミット [57558bd35d8e](https://github.com/spring-projects/spring-batch/commit/57558bd35d8ebef7ba48bf5b8201bd838771c28d) で対応されました。`split()` の契約は変えず、`PartitionStep` 側で集約対象を補います。

再起動時、同じ `JobInstance` の過去の実行で完了済みのパーティションも集約に加えます。今回ハンドラーが処理した分とは二重に数えません。`RemoteStepExecutionAggregator` は、過去の `JobExecution` に属する実行も除外せずそのまま集約します。テストと `scalability.adoc`（完了済みパーティションは再実行されないが集約結果には含まれる旨）も更新されています。

**アップグレード時の確認事項**
- 6.1.0 へ上げると、再起動後のマネージャーステップの `writeCount` や終了ステータスが変わります。再起動後の件数やステータスを見て判定している監視や後続処理があれば、期待値を確認してください。
- カスタム `StepExecutionAggregator` や `PartitionHandler` がある場合は、再起動時に過去の `JobExecution` で完了済みの実行が渡ってくる点を確認してください。

**採用されなかった案**
- オプトイン式の集約モード追加と、`split()` が完了済みを返す案は採用されていません。
- 別アプローチとして [#5318](https://github.com/spring-projects/spring-batch/issues/5318) があります。

## バグの発生タイミング

- 発生バージョンと混入コミットは入力から特定できません（Spring Batch 6.0.0 で確認、報告者によれば 5 系でも発生）。
- **修正コミット**: [57558bd35d8e](https://github.com/spring-projects/spring-batch/commit/57558bd35d8ebef7ba48bf5b8201bd838771c28d)（マイルストーン 6.1.0-RC1）
