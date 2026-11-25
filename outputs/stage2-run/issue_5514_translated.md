# ステップの ExitStatus に一致する遷移がない場合に、JobFlowExecutor が共有スレッド上のジョブ実行間で StepExecution をリークする

**Issue番号**: #5514
**状態**: closed | **作成者**: MenschNestor | **作成日**: 2026-09-01
**ラベル**: type: bug, in: core, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5514

## 内容

*AI の支援を受けたレポートが歓迎されない場合はここで読むのをやめられるよう、先にお断りしておきます。この分析は AI ツールの支援を受けています。以下のすべての主張は、引用した Spring Batch のソースと照らして確認しており、添付のサンプルもビルドして実行し、記載した挙動を確認しています。*

**バグの説明**

`JobFlowExecutor` は現在のステップ実行を **static** フィールドに保持しています。

```java
// JobFlowExecutor.java:45
private static final ThreadLocal<StepExecution> stepExecutionHolder = new ThreadLocal<>();
```

このホルダーは `close()` でのみクリアされます。`SimpleFlow.resume` では、`executor.close()` は両方の `catch` ブロック内とループの後で呼ばれますが、`nextState(...)` は保護された `try` の*外側*にあります。

```java
// SimpleFlow.java, resume(...)
try {
    status = state.handle(executor);
    stepExecution = executor.getStepExecution();
}
catch (FlowExecutionException e) { executor.close(new FlowExecution(stateName, status)); throw e; }
catch (Exception e)              { executor.close(new FlowExecution(stateName, status)); throw new FlowExecutionException(...); }

state = nextState(stateName, status, stepExecution);   // throws here, no close()
```

`FlowJob.doExecute` は `finally` なしで catch して再スローするだけなので、そこでもホルダーはクリアされません。

そのため、ステップがフローで網羅されていない `ExitStatus` で終了すると、`nextState` が `FlowExecutionException: Next state not found ...` をスローし、そのジョブの `StepExecution` はジョブ実行が終了した後もスレッドにバインドされたままになります。ホルダーが static であるため、そのスレッド上の以降のすべての `JobFlowExecutor` からそれが見えてしまいます。

そのスレッド上の次のジョブ実行は、自身のステップを実行する*前*に、`StepState.handle` から `abandonStepExecution()` を呼びます。

```java
// JobFlowExecutor.java:100
public void abandonStepExecution() {
    StepExecution lastStepExecution = stepExecutionHolder.get();
    if (lastStepExecution != null && lastStepExecution.getStatus().isGreaterThan(BatchStatus.STOPPING)) {
        lastStepExecution.upgradeStatus(BatchStatus.ABANDONED);
        jobRepository.update(lastStepExecution);
    }
}
```

これは、現在のジョブ実行が所有していない `StepExecution` を読み書きします。添付のサンプルで再現された結果は次の 3 つです。

1. **ジョブが自分自身を無効化する。** 次回の自身の実行が、前回の実行が残したステップ実行を abandon します。`SimpleStepHandler.shouldStart` は `ABANDONED` に対して `false` を返すため、そのステップは二度と実行されません。以降の起動のたびに "Step already complete or not restartable, so no action to execute" がログに出力され、フローは `FAILED` を受け取り、実行は失敗します。ジョブ 1 つ、スレッド 1 つで、並行性は不要です。
2. **無関係なジョブが破損する。** 次に別のジョブがそのスレッドで実行されると、*最初の*ジョブのステップ実行を abandon し、恒久的に無効化します。これは、2 番目のジョブ自身のフローが完全に正しく定義されている場合でも起こります。関係のないジョブの欠陥のせいで巻き添えになるのです。
3. **その行を所有したことのないジョブで `OptimisticLockingFailureException` が発生する。** `isGreaterThan(STOPPING)` は `ABANDONED` でも満たされるため、その行は繰り返し再更新されます。スレッドプール全体では、各スレッドが自身のコピーを保持し続けます。あるスレッドの更新でバージョンが上がると、他のスレッドが保持するコピーは古くなります。

```
org.springframework.dao.OptimisticLockingFailureException: Attempt to update step execution id=442
  with wrong version (340), where current version is 341
    at org.springframework.batch.core.repository.dao.jdbc.JdbcStepExecutionDao.updateStepExecution(JdbcStepExecutionDao.java:252)
    at org.springframework.batch.core.repository.support.SimpleJobRepository.update(SimpleJobRepository.java:174)
    ...
    at org.springframework.batch.core.job.flow.JobFlowExecutor.abandonStepExecution(JobFlowExecutor.java:104)
    at org.springframework.batch.core.job.flow.support.state.StepState.handle(StepState.java:67)
    at org.springframework.batch.core.job.flow.support.SimpleFlow.resume(SimpleFlow.java:166)
Wrapped by: org.springframework.batch.core.job.flow.FlowExecutionException: Ended flow=ocrJob at state=ocrJob.step0 with exception
```

このトレース内のステップ実行 id は、失敗したと報告されているフローのジョブとは*別のジョブ*のステップに属していることに注意してください。

私たちは本番環境でこの問題に遭遇しました。フロー定義が不完全な 1 つのジョブが、サービスを再起動するまで完全に処理を停止し、無関係な 3 つのジョブのスケジュール実行も巻き込んで停止させました。私たちのフロー定義が不完全だったこと、そしてそれによって*そのジョブ*が失敗すること(網羅されていない `ExitStatus` に対するドキュメント化された挙動)は受け入れます。想定していなかったのは、それが他のジョブのバッチメタデータを黙って破損させることです。

**環境**

* 本番インシデントでは Spring Batch 6.0.3。添付のサンプルは 6.0.4 で実行。`JobFlowExecutor` と `SimpleFlow` の該当コードは、これらの間でも、2026-09-01 時点の `main` でも変更されていないため、引用した行番号は 3 つすべてに当てはまります。
* Spring Boot 4.0.6
* Java 21
* H2、インメモリ、JDBC `JobRepository`
* ジョブは、9 スレッドの `ThreadPoolTaskScheduler` 上の Spring `@Scheduled` cron タスクから起動。自動構成された `JobOperator` をデフォルトの `SyncTaskExecutor` で使用しているため、ジョブ実行は共有のスケジューラスレッド上で直接行われます。

共有スレッドという条件が、この問題を顕在化させます。プールされた executor からジョブを起動する構成であれば、どれでもこの問題に遭遇する可能性があります。

**再現手順**

添付のサンプルがこれらすべてを行います。要点は次のとおりです。

1. 1 つの終了ステータスのみを網羅するフローを持つジョブを構成します。例: `new JobBuilder("jobA", jobRepository).start(step).on("COMPLETED").stop().end().build()`。この形は、`JobInstance` をスケジュールで再起動可能に保つものです。
2. ステップを失敗させ、その `ExitStatus` を `FAILED` にします。
3. ジョブを実行します。`FlowExecutionException: Next state not found in flow=jobA for state=jobA.step0 with exit status=FAILED` で失敗します。
4. **同じスレッド上で**もう一度実行します。そのステップ実行は `ABANDONED` とマークされ、ステップは実行されません。以後、二度と実行されません。
5. 手順 4 で他の任意のジョブに置き換えても、そのジョブのフローがどのようなものであっても、同じ形で `jobA` のステップ実行が破損します。
6. 小さなスレッドプール全体で繰り返すと、上記の `OptimisticLockingFailureException` も発生します。

実際のジョブでは、ステップに `allowStartIfComplete(true)` も設定しています。再起動可能なジョブでは、完了済みのステップを再実行するためにこれが必要だからです。ただし、ここでは関係しません。失敗パスは `shouldStart` の `COMPLETED` 分岐には到達せず、添付のサンプルはこれがあってもなくても同一に再現します。サンプルを最小限にするため、そこでは省略しています。

**期待される動作**

ジョブ実行が、他のジョブ実行の `StepExecution` を読み書きしてはなりません。具体的には次のとおりです。

* `stepExecutionHolder` は `static` であるべきではありません。これは実行ごとの状態を保持しており、`JobFlowExecutor` は `FlowJob.doExecute` でジョブ実行ごとにすでに作成されているため、この状態を JVM 全体のものにしているのは `static` 修飾子だけのようです。
* ホルダーは、フローが終了するときは常に、`nextState` がスローする場合も含めてクリアされるべきです。たとえば、`nextState` を保護されたブロックの内側に移すか、`finally` でクリアします。

どちらか一方の変更だけでも連鎖は断ち切れます。両方とも、それぞれ単独で行う価値があると考えます。

不完全なフロー定義は私たち側の構成エラーであり、それを持つジョブを失敗させるのは当然です。しかし、それによって他のジョブのステップ実行が `ABANDONED` とマークされたり、無関係なジョブが楽観的ロックエラーで失敗したりすることがあってはなりません。

**最小限の再現可能な完全な例**

添付: `spring-batch-mcve.zip`(テンプレートから作成。`pom.xml` とクラス 1 つ、`target` ディレクトリなし)。

```shell
unzip spring-batch-mcve.zip && cd spring-batch-mcve
mvn package exec:java -Dexec.mainClass=org.springframework.batch.MyBatchJobConfiguration
```

4 つのシナリオ。リークはスレッドにバインドされているため、それぞれ専用のスレッドで実行します。

```
SCENARIO 1 - a job with an uncovered ExitStatus never runs its step again
  times the step actually ran : 1   (expected 2)
  step execution status       : ABANDONED

SCENARIO 2 - control: the same job, with a catch-all transition
  times the step actually ran : 2   (expected 2)
  step execution status       : FAILED

SCENARIO 3 - an unrelated job corrupts the first job's StepExecution
  leakingJob step status, before innocentJob runs : FAILED
  leakingJob step status, after  innocentJob runs : ABANDONED
  leakingJob step runs before / after relaunch    : 1 / 1

SCENARIO 4 - retained stale copies collide with OptimisticLockingFailureException
  worker-2 causes :
      JobExecutionException: Flow execution ended unexpectedly
      FlowExecutionException: Ended flow=jobC at state=jobC.step0 with exception
      OptimisticLockingFailureException: Attempt to update step execution id=1 with wrong version (4), where current version is 5

ALL SCENARIOS BEHAVED AS DESCRIBED
```

シナリオ 2 は対照実験です。同じジョブに `.from(step).on("*").fail()` を追加すると、両方の起動でステップが実行され、`FAILED` のまま残ります。したがって、遷移の欠落が、回復するジョブと二度と実行されないジョブとの唯一の違いです。シナリオ 3 では、`innocentJob` は正しく定義されたフローと別の `JobRepository` エントリを持っていますが、両者がスレッドを共有しているため、`leakingJob` のステップ実行を abandon できてしまいます。

起票前にトラッカーを検索しました: `JobFlowExecutor`、`abandonStepExecution`、`stepExecutionHolder`、`FlowExecutor`、`ThreadLocal`、`Next state not found`、`ABANDONED`、および `related-to: optimistic-locking` ラベル。最も近い既存のレポートは #1826 ですが、それは `AbstractStep.execute` でのコミット失敗パスであり、別のメカニズムです。

[spring-batch-mcve.zip](https://github.com/user-attachments/files/31704251/spring-batch-mcve.zip)

## コメント

### コメント 1 by MenschNestor (2026-09-01)

説明文のものに置き換わる、更新版のサンプルを添付します。4 つのシナリオと挙動は同じです。変更は 2 点で、どちらも出力を読みやすくするためのものです。

**シナリオ 4 が例外を出力するようになりました。** Spring Batch は `AbstractJob` から ERROR レベルでログ出力していますが、`exec:java` は Maven の JVM 内で実行され、その SLF4J バインディングを共有するため、それがコンソールに届くかどうかは Maven の起動方法に依存します。最初のバージョンを実行した同僚は 1 行のサマリーしか見えず、シナリオが再現しなかったと判断してしまいました(無理もありません)。今回はスタックトレース自体を出力します。

```
org.springframework.dao.OptimisticLockingFailureException: Attempt to update step execution id=1 with wrong version (4), where current version is 5
	at org.springframework.batch.core.repository.dao.jdbc.JdbcStepExecutionDao.updateStepExecution(JdbcStepExecutionDao.java:256)
	at org.springframework.batch.core.repository.support.SimpleJobRepository.update(SimpleJobRepository.java:171)
	...
	at jdk.proxy3/jdk.proxy3.$Proxy27.update(Unknown Source)
	at org.springframework.batch.core.job.flow.JobFlowExecutor.abandonStepExecution(JobFlowExecutor.java:104)
	at org.springframework.batch.core.job.flow.support.state.StepState.handle(StepState.java:67)
	at org.springframework.batch.core.job.flow.support.SimpleFlow.resume(SimpleFlow.java:166)
	at org.springframework.batch.core.job.flow.support.SimpleFlow.start(SimpleFlow.java:141)
	at org.springframework.batch.core.job.flow.FlowJob.doExecute(FlowJob.java:135)
```

これは説明文にある本番のトレースと同じ形です。`JdbcStepExecutionDao` に到達する更新は `abandonStepExecution` からのもので、現在のジョブ実行が自身のステップを実行する前に `StepState.handle` から呼ばれています。

**意図的なステップ失敗がスタックトレースを持たなくなりました。** Spring Batch はそれを StepExecution の `exitDescription` に保存し、以降の起動のたびにそれをログ出力するため、以前のバージョンでは、本題ではない例外の 25 行のトレースが繰り返されて、フレームワーク自身の証拠が埋もれていました。失敗はスタックレスの例外になったため、フレームワーク自身の証拠が 1 行で読めるようになっています。

```
INFO o.s.b.core.job.SimpleStepHandler - Step already complete or not restartable, so no action to
execute: StepExecution: id=1, version=4, name=jobAStep, status=ABANDONED, exitStatus=FAILED, ...
```

それ以外は何も変わっておらず、観測される挙動は同一です。

[spring-batch-mcve.zip](https://github.com/user-attachments/files/31704971/spring-batch-mcve.zip)

### コメント 2 by jjj-n (2026-09-08)

この issue に取り組みたいと思います。報告された挙動を再現し、executor のクリーンアップとジョブ実行間の分離をカバーする回帰テストを含む修正を用意しました。まもなく PR を開きます。


### コメント 3 by fmbenhassine (2026-10-05)

これは有効な issue です。報告してくれてありがとうございます。74975c506 でのリグレッションのようです。

次のリリースで修正する予定です。
