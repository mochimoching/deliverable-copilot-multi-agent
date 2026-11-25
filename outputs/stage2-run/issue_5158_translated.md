# コントローラー再起動時に、リモートパーティションの aggregator にすべてのワーカーステップが渡されない

**Issue番号**: #5158
**状態**: closed | **作成者**: brian-mcnamara | **作成日**: 2025-12-10
**ラベル**: type: bug, in: integration, has: minimal-example
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5158

## 内容

バグの説明
コントローラーとワーカーで構成されるリモートパーティショニングのジョブにおいて、コントローラージョブが停止され(たとえば Pod が kill されてジョブが graceful にシャットダウンされた場合)、リモートワーカーのステップが完了し、その後コントローラージョブが再起動されたとします。ジョブの進行として結果を aggregator に渡す段階になると、リモートステップは正常に完了しているにもかかわらず、aggregator には空の step execution のリストが渡されます。

これは、SimpleStepExecutionSplitter が、完了済みであることを理由に execution をフィルタリングして除外してしまうためです。

環境
Spring boot 4.0.0, batch 6.0.0, batch-integration 6.0.0, JDK21
ただし、batch 5 でも同じ問題が発生します

再現手順

サンプルリポジトリは https://github.com/brian-mcnamara/SpringBatch6/tree/shutdownAggregator を参照してください

(`./gradlew run` で実行できます) 特に [235行目](https://github.com/brian-mcnamara/SpringBatch6/blob/shutdownAggregator/src/main/java/com/example/batchpartitionbug/BatchPartitionBugApplication.java#L235) に注目してください。ここでは aggregator に2つの step execution のリストが渡されることを期待しています。

期待される動作

aggregator が呼び出されるとき、ワーカーが完了したステップが含まれているべきです。

## コメント

### コメント 1 by banseok1216 (2026-01-24)

> **Bug description**
> In a remote partitioned job, with a controller and workers, if the controller job is stopped (for example when the pod is killed and the job is gracefully shutdown), if the remote workers steps complete, and the controller job is restarted, if the job progression is to pass the result to a aggregator, the aggregator is passed an empty list of step executions, even tho the remote steps completed successfully.
>
> This is due to SimpleStepExecutionSplitter filtering out the executions since they were completed.
>
> **Expected behavior**
> When the aggregator is called, it should contain the steps the worker completed.

現在のリスタートの意図に基づくと、これは意図された動作であるように見えます。

splitter は「今回の試行で再実行が必要なパーティション」だけを返すため、コントローラーが停止している間にすべてのワーカーがパーティションを完了した場合、Spring Batch は再実行すべきものはもうないと判断し、その結果、handler/aggregator には空の execution のリストが渡されます。

JobInstance 全体にわたる最終的な集約(すでに完了済みのパーティションを含む)が必要な場合、それは現在の動作とは異なる集約の意図になります。
 考えられる選択肢は次のとおりです:
• 集約の入力を「今回の試行で再実行されたパーティションのリスト」ではなく、JobInstance に保存されているパーティション化された StepExecution(すでに COMPLETED のものを含む)に変更するよう、集約方法を変更する。
• パーティショニングにオプトインの集約モード(例: 既存の動作と、完了済みパーティションを含める動作)を追加する。

### コメント 2 by brian-mcnamara (2026-01-24)

@banseok1216 さん、確認してくださってありがとうございます。これが期待される動作でバグではないのであれば、この issue はクローズします。選択肢を示してくださってありがとうございます!

### コメント 3 by fmbenhassine (2026-02-04)

@brian-mcnamara さん、報告ありがとうございます!また @banseok1216 さん、フォローアップありがとうございます。

私はこれはバグだと考えています。すべてのパーティションが正常に完了しているにもかかわらず、コントローラージョブが失敗としてマークされるためです。リスタート時に aggregator が何を受け取るかにかかわらず、失敗したジョブをリスタートした場合、その間にすべてのパーティションが正常に完了していたなら、ジョブは完了としてマークされるべきです。

より深い調査と修正のため、この issue を再オープンします。

### コメント 4 by fmbenhassine (2026-02-04)

#4831 とやや関連しています

### コメント 5 by answndud (2026-03-05)

Hi team, I'd like to work on this issue.\n\nI will start by reproducing the restart scenario from the minimal example and then propose a focused fix so that a restarted manager job can complete when partitions were already completed while the manager was down.\n\nI will share a PR once I have a reproducible failing test and patch.

### コメント 6 by answndud (2026-03-05)

I opened PR #5318 with a proposed fix and tests for this restart aggregation behavior.\n\nSummary:\n- include completed partition executions on restart for aggregation\n- avoid re-executing already completed partitions\n- add splitter/handler/partition-step coverage

### コメント 7 by XhstormR (2026-09-23)

ping

### コメント 8 by fmbenhassine (2026-09-30)

57558bd35 で修正されました。これが意図された動作かどうかについて上で議論があったため、アプローチについて簡単に補足します。@banseok1216 さんの指摘どおり、`SimpleStepExecutionSplitter` はドキュメントに記載された動作をしています。`split()` は再起動が必要な execution のみを返すと規定されており、私はそれを変更したくありませんでした。splitter が完了済みの execution を返すようにすると、`split()` を直接呼び出す `PartitionHandler` が、完了済みの作業をワーカーに再ディスパッチしてしまうことになります。

実際のバグは1つ上のレベル、`PartitionStep` にあります。`PartitionHandler` の結果を「今実行したパーティション」と「集約対象のパーティション」の両方として使っています。これらは正当に異なる2つの集合であり、リスタート時には後者が黙って前者に潰れてしまいます。そこで今回の修正では、handler の結果と、同じ job instance の以前の実行ですでに完了しているパーティションとの和集合に対して集約を行い、パーティション名をキーにして重複して数えないようにしました。`RemoteStepExecutionAggregator` にも小さな変更が必要でした。現在の `JobExecution` に属さないものをすべて除外してしまっていたためです。

調査中に、ここで報告されたケースに限らない関連の問題も見つかりました。パーティション化されたジョブのリスタート後は、すべてのパーティションが完了していた場合だけでなく、manager ステップの集約メトリクスが常に誤っています。1つのパーティションが完了し、1つが失敗した状態で、それぞれが3件のアイテムを書き込む場合:

```
run 1: managerStep -> FAILED    writeCount=6   (correct)
run 2: managerStep -> COMPLETED writeCount=3   (should be 6)
```

再起動された manager ステップは、実際には6行を書き込んだ作業に対して書き込み数3を永続化していました。再実行されたパーティションのみが集約されていたためです。同じ修正でこれもカバーされます。

再現コードを提供してくださった @brian-mcnamara さん、PR を作成してくださった @answndud さん、ありがとうございます(別の方法を取った理由は #5318 で説明しました)。
