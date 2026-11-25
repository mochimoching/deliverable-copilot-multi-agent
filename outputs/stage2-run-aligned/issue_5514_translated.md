*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# ステップの ExitStatus に一致する遷移がない場合、JobFlowExecutor が共有スレッド上でジョブ実行をまたいで StepExecution をリークする

**Issue番号**: #5514
**状態**: closed | **作成者**: MenschNestor | **作成日**: 2026-09-01
**ラベル**: type: bug, in: core, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5514

## 内容

*AI支援によるレポートが歓迎されない場合はここで読むのをやめられるよう、最初に開示しておきます。この分析はAIツールの支援を受けています。以下の主張はすべて、引用したSpring Batchのソースに照らして確認しており、添付のサンプルもビルドして実行し、記載した動作を確認しています。*

**バグの説明**

`JobFlowExecutor`は、現在のステップ実行を**static**フィールドに保持しています。

```java
// JobFlowExecutor.java:45
private static final ThreadLocal<StepExecution> stepExecutionHolder = new ThreadLocal<>();
```

このホルダーは`close()`でのみクリアされます。`SimpleFlow.resume`では、2つの`catch`ブロックの両方とループの後で`executor.close()`が呼び出されますが、`nextState(...)`は保護された`try`の*外側*にあります。

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

`FlowJob.doExecute`は`finally`なしで例外をキャッチして再スローするため、ここでもホルダーはクリアされません。

そのため、ステップがフローで網羅されていない`ExitStatus`で終了すると、`nextState`が`FlowExecutionException: Next state not found ...`をスローし、そのジョブの`StepExecution`はジョブ実行が終了した後もスレッドにバインドされたままになります。ホルダーがstaticであるため、そのスレッド上の以降のすべての`JobFlowExecutor`からこれが見えてしまいます。

そのスレッド上の次のジョブ実行は、自身のステップを実行する*前*に、`StepState.handle`から`abandonStepExecution()`を呼び出します。

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

これは、現在のジョブ実行が所有していない`StepExecution`を読み書きします。添付のサンプルですべて再現できる3つの影響があります。

1. **ジョブが自分自身を無効化する。** 次の実行が、前回の実行が残したステップ実行を放棄(abandon)してしまいます。`SimpleStepHandler.shouldStart`は`ABANDONED`に対して`false`を返すため、そのステップは二度と実行されません。以降の起動では毎回「Step already complete or not restartable, so no action to execute」がログに出力され、フローは`FAILED`を受け取り、実行は失敗します。1つのジョブ、1つのスレッドで、並行処理がなくても発生します。
2. **無関係なジョブが破損する。** 別のジョブがそのスレッド上で次に実行されると、*最初の*ジョブのステップ実行を放棄し、恒久的に無効化します。これは、2番目のジョブ自身のフローが完全に正しく定義されている場合でも起こります。無関係なジョブの欠陥のために、そのジョブが巻き添えになります。
3. **行を所有したことのないジョブで`OptimisticLockingFailureException`が発生する。** `isGreaterThan(STOPPING)`は`ABANDONED`でも満たされるため、その行は繰り返し再更新されます。スレッドプール全体では、各スレッドが自身のコピーを保持し続けます。1つのスレッドの更新でバージョンが上がると、他のスレッドが保持するコピーは古くなります。

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

このトレースのステップ実行idは、失敗として報告されているフローのジョブとは*別の*ジョブのステップに属していることに注意してください。

私たちは本番環境でこれに遭遇しました。フロー定義が不完全な1つのジョブが、サービスを再起動するまで一切処理されなくなり、無関係な3つのジョブのスケジュール実行も巻き添えで停止しました。私たちのフロー定義が不完全だったこと、そのためその*当該*ジョブが失敗すること(網羅されていない`ExitStatus`に対する文書化された動作)は受け入れます。想定していなかったのは、それが他のジョブのバッチメタデータを黙って破損させることです。

**環境**

* 本番インシデントではSpring Batch 6.0.3、添付のサンプルは6.0.4で動作。`JobFlowExecutor`と`SimpleFlow`の該当コードはこれらの間、および2026-09-01時点の`main`で変更されていないため、引用した行番号は3つすべてに当てはまります。
* Spring Boot 4.0.6
* Java 21
* H2、インメモリ、JDBC `JobRepository`
* ジョブは、9スレッドの`ThreadPoolTaskScheduler`上の Spring `@Scheduled` cronタスクから起動され、自動構成された`JobOperator`をデフォルトの`SyncTaskExecutor`で使用しているため、ジョブ実行は共有のスケジューラスレッド上で直接実行されます

共有スレッドという条件が、この問題を顕在化させます。プールされたエグゼキュータからジョブを起動する構成であれば、どれでも発生し得ます。

**再現手順**

添付のサンプルがこれらすべてを行います。要約すると次のとおりです。

1. 1つのexit statusのみを網羅するフローを持つジョブを設定します。例: `new JobBuilder("jobA", jobRepository).start(step).on("COMPLETED").stop().end().build()`。この形式は、`JobInstance`をスケジュールで再起動可能な状態に保ちます。
2. ステップを失敗させ、その`ExitStatus`を`FAILED`にします。
3. ジョブを実行します。`FlowExecutionException: Next state not found in flow=jobA for state=jobA.step0 with exit status=FAILED`で失敗します。
4. **同じスレッド上で**もう一度実行します。そのステップ実行は`ABANDONED`とマークされ、ステップは実行されません。以後も二度と実行されません。
5. 手順4で他の任意のジョブに置き換えると、そのジョブのフローがどのようなものであっても、同じ方法で`jobA`のステップ実行が破損します。
6. 小さなスレッドプール全体で繰り返すと、さらに上記の`OptimisticLockingFailureException`が発生します。

私たちの実際のジョブでは、ステップに`allowStartIfComplete(true)`も設定しています。再起動可能なジョブは、完了済みのステップを再実行するためにこれが必要だからです。ただし、ここでは関係ありません。失敗パスは`shouldStart`の`COMPLETED`分岐には到達せず、添付のサンプルはこれの有無にかかわらず同一に再現します。サンプルを最小限に保つため、サンプルでは省略しています。

**期待される動作**

ジョブ実行は、他のジョブ実行の`StepExecution`を読み書きしてはいけません。具体的には次のとおりです。

* `stepExecutionHolder`は`static`であるべきではありません。これは実行ごとの状態を保持しており、`JobFlowExecutor`は`FlowJob.doExecute`ですでにジョブ実行ごとに作成されているため、この状態をJVM全体で共有させているのは修飾子だけのようです。
* ホルダーは、`nextState`がスローする場合を含め、フローが終了するたびにクリアされるべきです。たとえば、`nextState`を保護されたブロック内に移動するか、`finally`でクリアします。

どちらか一方の変更だけでも連鎖を断ち切れますが、どちらも単独で行う価値があるように思われます。

不完全なフロー定義は私たち側の設定エラーであり、それを持つジョブを失敗させるべきです。それが他のジョブのステップ実行を`ABANDONED`とマークしたり、無関係なジョブを楽観的ロックエラーで失敗させたりできてはいけません。

**Minimal Complete Reproducible example**

添付: `spring-batch-mcve.zip`(テンプレートから作成。`pom.xml`と1つのクラスのみ、`target`ディレクトリなし)。

```shell
unzip spring-batch-mcve.zip && cd spring-batch-mcve
mvn package exec:java -Dexec.mainClass=org.springframework.batch.MyBatchJobConfiguration
```

リークはスレッドに紐づくため、4つのシナリオをそれぞれ専用のスレッドで実行します。

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

シナリオ2は対照実験です。同じジョブに`.from(step).on("*").fail()`を追加すると、両方の起動でステップが実行され、`FAILED`のまま残ります。つまり、遷移の欠落が、回復するジョブと二度と実行されないジョブとの唯一の違いです。シナリオ3では、`innocentJob`は正しく定義されたフローと別の`JobRepository`エントリを持っていますが、2つがスレッドを共有しているため、それでも`leakingJob`のステップ実行を放棄できてしまいます。

報告前にトラッカーを検索しました: `JobFlowExecutor`、`abandonStepExecution`、`stepExecutionHolder`、`FlowExecutor`、`ThreadLocal`、`Next state not found`、`ABANDONED`、および`related-to: optimistic-locking`ラベル。最も近い既存の報告は#1826ですが、それは`AbstractStep.execute`でのコミット失敗パスに関するもので、別のメカニズムです。

[spring-batch-mcve.zip](https://github.com/user-attachments/files/31704251/spring-batch-mcve.zip)

## コメント

### コメント 1 by MenschNestor (2026-09-01)

説明文のものと置き換える形で、更新したサンプルを添付します。4つのシナリオも動作も同じです。変更は2点で、どちらも出力を読みやすくするためのものです。

**シナリオ4が例外を出力するようになりました。** Spring Batchは`AbstractJob`からERRORレベルでログを出力しますが、`exec:java`はMavenのJVM内で実行され、そのSLF4Jバインディングを共有するため、それがコンソールに届くかどうかはMavenの起動方法に依存します。最初のバージョンを実行した同僚は1行の要約しか見ておらず、シナリオが再現しなかったと判断したのも無理はありません。今回はスタックトレース自体を出力します。

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

これは説明文にある本番トレースと同じ形です。`JdbcStepExecutionDao`に到達する更新は`abandonStepExecution`から来ており、それは現在のジョブ実行が自身のステップを実行する前に`StepState.handle`から呼び出されています。

**意図的なステップ失敗がスタックトレースを持たなくなりました。** Spring Batchはそれを`StepExecution`の`exitDescription`に保存し、以降の起動のたびにログへ書き戻すため、以前のバージョンでは、本題ではない例外の25行のトレースが繰り返され、本来の調査結果が埋もれていました。失敗はスタックレスの例外になり、フレームワーク自身の証拠が1行で読めるようになりました。

```
INFO o.s.b.core.job.SimpleStepHandler - Step already complete or not restartable, so no action to
execute: StepExecution: id=1, version=4, name=jobAStep, status=ABANDONED, exitStatus=FAILED, ...
```

それ以外は変更しておらず、観測される動作は同一です。

[spring-batch-mcve.zip](https://github.com/user-attachments/files/31704971/spring-batch-mcve.zip)

### コメント 2 by jjj-n (2026-09-08)

この課題に取り組みたいと考えています。報告された動作を再現し、エグゼキュータのクリーンアップとジョブ実行間の分離を対象とするリグレッションテストを含む修正を用意しました。まもなくPRを開きます。


### コメント 3 by fmbenhassine (2026-10-05)

これは妥当な課題です。報告していただきありがとうございます。74975c506 でのリグレッションのようです。

修正は次のリリースで予定しています。
