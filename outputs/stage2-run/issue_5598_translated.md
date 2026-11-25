# RemoteChunkingManagerBuilder を導入し、RemoteChunkingManagerStepBuilder とそのファクトリを非推奨にする

**Issue番号**: #5598
**状態**: closed | **作成者**: fmbenhassine | **作成日**: 2026-10-14
**ラベル**: in: integration, type: enhancement
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5598

## 内容

`RemoteChunkingManagerStepBuilder` は非推奨の `FaultTolerantStepBuilder` を継承しているため、7.0 で削除予定の非推奨 API（`keyGenerator`、Spring Retry の `RetryListener`、レガシーなチャンクエンジンなど）を公開してしまっています。`@EnableBatchIntegration` によって Bean として公開される `RemoteChunkingManagerStepBuilderFactory` についても同様です。

この issue では、`StepBuilder` をベースとし、非推奨でない API のみに依存し、`RemoteChunkingWorkerBuilder` と一貫性のある新しい `RemoteChunkingManagerBuilder` を導入します。これは `ChunkMessageChannelItemWriter` をセットアップし、通常の `ChunkOrientedStepBuilder` を返します:

```java
Step managerStep = new RemoteChunkingManagerBuilder("managerStep", jobRepository)
        .outputChannel(requests)
        .inputChannel(replies)
        .chunk(100)
        .reader(itemReader)
        .transactionManager(transactionManager)
        .build();
```

`RemoteChunkingManagerStepBuilder` と `RemoteChunkingManagerStepBuilderFactory` は、これに置き換える形で 6.1 で非推奨とし、7.0 で削除するべきです。
