*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# ジョブスコープのBeanがマルチスレッドステップおよび並列フローのワーカースレッドで使用できない問題

**Issue番号**: #5576
**状態**: closed | **作成者**: fmbenhassine | **作成日**: 2026-10-06
**ラベル**: type: bug, in: core, related-to: multi-threading, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5576

## 内容

ジョブスコープのBeanは、`Job`を実行するスレッド以外のスレッドからは使用できません。次の2つのケースで、`ScopeNotActiveException` / `IllegalStateException: No context holder available for job scope` が発生して失敗します。

1. マルチスレッドステップ（`TaskExecutor`で設定されたステップ）のワーカースレッド内。
2. 並列フローを実行するために使用されるスレッド内（`FlowBuilder#split(TaskExecutor)`）。

`StepScope`にはこの制限はありません。たとえば`ChunkOrientedStep`、`StepContextRepeatCallback`、`AsyncItemProcessor`などによって、ステップコンテキストがワーカースレッドに登録されます。一方、ジョブコンテキストをこれらのスレッドに登録するものは何もありません。`JobSynchronizationManager`は`AbstractJob#execute`からのみ、つまりジョブを実行するスレッド上でのみ登録されます（`ThreadLocal`ベース）。

`JobSynchronizationManager`のjavadocには、プールからのワーカースレッドを含め、ジョブ実行に関わるすべてのスレッドで`JobContext`を利用可能にすることは、すべての`Job`実装の責任であると書かれています。上記の2つのケースでは、フレームワークはこれを行っていません。

この問題は最初に [#4782](https://github.com/spring-projects/spring-batch/issues/4782) で報告され、新しい`@FlowScope`の要望と合わせて提起されました。この課題ではジョブスコープの伝播のみを扱います。

**環境**

Spring Batch `main`（eab562ff4e309f307b905ade2453054ca2b6b1bc 時点）、組み込みHSQLのジョブリポジトリ。

**再現手順**

`@JobScope`のBeanを定義し、(a) マルチスレッドのチャンク指向ステップのプロセッサと、(b) 並列フローで実行される2つのステップから使用します。

```java
@Bean
@JobScope
JobScopedBean jobScopedBean() {
      return new JobScopedBean();
}

@Bean
Job multiThreadedStepJob(JobRepository jobRepository, PlatformTransactionManager transactionManager,
              JobScopedBean jobScopedBean) {
      Step step = new ChunkOrientedStepBuilder<Integer, Integer>(jobRepository, 1)
              .reader(new ListItemReader<>(List.of(1, 2, 3, 4)))
              .processor(item -> {
                      jobScopedBean.getId(); // fails on worker threads
                      return item;
              })
              .writer(new ListItemWriter<>())
              .transactionManager(transactionManager)
              .taskExecutor(new SimpleAsyncTaskExecutor())
              .build();
      return new JobBuilder("multiThreadedStepJob", jobRepository).start(step).build();
}
```

完全な再現コードをJUnitテストとして以下に添付します（`JobScopeMultiThreadingTests`）。成功する逐次実行のコントロールジョブと、失敗する上記の2つのケースが含まれています。

**期待される動作**

ジョブスコープのBeanが、ジョブ実行に関わるすべてのスレッドで解決され、すべてのスレッドが同じインスタンスを参照します。ジョブは正常に完了します。

**実際の動作**

ジョブが失敗します。

```
org.springframework.beans.factory.support.ScopeNotActiveException: Error creating bean with name 'scopedTarget.jobScopedBean': Scope 'job' is not active for the current thread; consider defining a scoped proxy for this bean if you intend to refer to it from a singleton
Caused by: java.lang.IllegalStateException: No context holder available for job scope
```

**最小限の完全な再現例**

<details>
<summary>JobScopeMultiThreadingTests.java</summary>

```java
package org.springframework.batch.core.scope;

import java.util.List;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

import javax.sql.DataSource;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.configuration.annotation.JobScope;
import org.springframework.batch.core.configuration.support.JdbcDefaultBatchConfiguration;
import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.JobExecution;
import org.springframework.batch.core.job.builder.FlowBuilder;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.job.flow.Flow;
import org.springframework.batch.core.job.parameters.JobParameters;
import org.springframework.batch.core.launch.JobOperator;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.step.builder.ChunkOrientedStepBuilder;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.infrastructure.item.support.ListItemReader;
import org.springframework.batch.infrastructure.item.support.ListItemWriter;
import org.springframework.batch.infrastructure.repeat.RepeatStatus;
import org.springframework.batch.infrastructure.support.DatabaseType;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.SimpleAsyncTaskExecutor;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

import static org.junit.jupiter.api.Assertions.assertEquals;

/**
 * Tests that a {@link JobScope job-scoped} bean can be used from the threads that take
 * part in a job execution, and that all of them see the same instance.
 */
class JobScopeMultiThreadingTests {

	/**
	 * Identities of the job-scoped bean instances seen by the job's components. Static
	 * because the components are lambdas that capture the job-scoped proxy.
	 */
	private static final Set<String> seenInstances = ConcurrentHashMap.newKeySet();

	@BeforeEach
	void setUp() {
		seenInstances.clear();
	}

	@Test
	void testJobScopedBeanInSequentialSteps() throws Exception {
		JobExecution jobExecution = runJob("sequentialStepsJob");

		assertEquals(ExitStatus.COMPLETED, jobExecution.getExitStatus(), failures(jobExecution));
		assertEquals(1, seenInstances.size());
	}

	@Test
	void testJobScopedBeanInMultiThreadedStep() throws Exception {
		JobExecution jobExecution = runJob("multiThreadedStepJob");

		assertEquals(ExitStatus.COMPLETED, jobExecution.getExitStatus(), failures(jobExecution));
		assertEquals(1, seenInstances.size());
	}

	@Test
	void testJobScopedBeanInParallelFlows() throws Exception {
		JobExecution jobExecution = runJob("parallelFlowsJob");

		assertEquals(ExitStatus.COMPLETED, jobExecution.getExitStatus(), failures(jobExecution));
		assertEquals(1, seenInstances.size());
	}

	private JobExecution runJob(String jobName) throws Exception {
		try (AnnotationConfigApplicationContext context = new AnnotationConfigApplicationContext(
				JobConfiguration.class)) {
			Job job = context.getBean(jobName, Job.class);
			return context.getBean(JobOperator.class).start(job, new JobParameters());
		}
	}

	private static String failures(JobExecution jobExecution) {
		return "Job failed with: " + jobExecution.getAllFailureExceptions();
	}

	public static class JobScopedBean {

		private final String id = Integer.toHexString(System.identityHashCode(this));

		// accessed through a getter as the bean is injected as a scoped proxy
		public String getId() {
			return this.id;
		}

	}

	@Configuration
	static class JobConfiguration extends JdbcDefaultBatchConfiguration {

		@Bean
		@JobScope
		JobScopedBean jobScopedBean() {
			return new JobScopedBean();
		}

		@Bean
		DataSource dataSource() {
			return new EmbeddedDatabaseBuilder().setType(EmbeddedDatabaseType.HSQL)
				.addScript(DatabaseType.HSQL.getProductSchema())
				.generateUniqueName(true)
				.build();
		}

		@Bean
		PlatformTransactionManager transactionManager(DataSource dataSource) {
			return new JdbcTransactionManager(dataSource);
		}

		@Bean
		Job sequentialStepsJob(JobRepository jobRepository, PlatformTransactionManager transactionManager,
				JobScopedBean jobScopedBean) {
			return new JobBuilder("sequentialStepsJob", jobRepository)
				.start(taskletStep("step1", jobRepository, transactionManager, jobScopedBean))
				.next(taskletStep("step2", jobRepository, transactionManager, jobScopedBean))
				.build();
		}

		@Bean
		Job multiThreadedStepJob(JobRepository jobRepository, PlatformTransactionManager transactionManager,
				JobScopedBean jobScopedBean) {
			Step step = new ChunkOrientedStepBuilder<Integer, Integer>(jobRepository, 1)
				.reader(new ListItemReader<>(List.of(1, 2, 3, 4)))
				.processor(item -> {
					seenInstances.add(jobScopedBean.getId());
					return item;
				})
				.writer(new ListItemWriter<>())
				.transactionManager(transactionManager)
				.taskExecutor(new SimpleAsyncTaskExecutor())
				.build();
			return new JobBuilder("multiThreadedStepJob", jobRepository).start(step).build();
		}

		@Bean
		Job parallelFlowsJob(JobRepository jobRepository, PlatformTransactionManager transactionManager,
				JobScopedBean jobScopedBean) {
			Flow flow1 = new FlowBuilder<Flow>("flow1")
				.start(taskletStep("step1", jobRepository, transactionManager, jobScopedBean))
				.build();
			Flow flow2 = new FlowBuilder<Flow>("flow2")
				.start(taskletStep("step2", jobRepository, transactionManager, jobScopedBean))
				.build();
			Flow parallelFlows = new FlowBuilder<Flow>("parallelFlows").split(new SimpleAsyncTaskExecutor())
				.add(flow1, flow2)
				.build();
			return new JobBuilder("parallelFlowsJob", jobRepository).start(parallelFlows).end().build();
		}

		private Step taskletStep(String name, JobRepository jobRepository,
				PlatformTransactionManager transactionManager, JobScopedBean jobScopedBean) {
			return new StepBuilder(name, jobRepository).tasklet((contribution, chunkContext) -> {
				seenInstances.add(jobScopedBean.getId());
				return RepeatStatus.FINISHED;
			}, transactionManager).build();
		}

	}

}
```

</details>
