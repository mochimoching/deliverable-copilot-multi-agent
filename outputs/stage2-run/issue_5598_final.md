# Issue #5598 要約: `RemoteChunkingManagerBuilder` の導入と `RemoteChunkingManagerStepBuilder` / Factory の非推奨化
## 概要
リモートチャンキングの manager ステップを組み立てる新ビルダー `RemoteChunkingManagerBuilder` が 6.1.0-RC1 で追加されました。`StepBuilder` をベースにし、非推奨でない API だけを使います。従来の `RemoteChunkingManagerStepBuilder` と `RemoteChunkingManagerStepBuilderFactory` は 6.1 で非推奨(`@Deprecated(since = "6.1", forRemoval = true)`)となり、7.0 で削除予定です。

## 問題
`RemoteChunkingManagerStepBuilder` は、7.0 で削除予定の非推奨クラス `FaultTolerantStepBuilder` を継承しています。そのため `keyGenerator`、Spring Retry の `RetryListener`、旧チャンクエンジンなど、削除予定の API が利用者に露出していました。`@EnableBatchIntegration` が Bean として公開する `RemoteChunkingManagerStepBuilderFactory` も同様です。

## 修正内容
- 新規 `RemoteChunkingManagerBuilder`(`spring-batch-integration` の `chunk` パッケージ)
  - `StepBuilder` を継承し、`RemoteChunkingWorkerBuilder` と対になる位置付けです。
  - リモートチャンキング固有の設定として `inputChannel`、`outputChannel`、`messagingTemplate`、`maxWaitTimeouts`(既定 40)、`throttleLimit`(既定 6)を持ちます。`maxWaitTimeouts` と `throttleLimit` は 0 より大きい値のみ指定できます(0 以下は `IllegalArgumentException`)。
  - `chunk(int)` をオーバーライドし、`ChunkMessageChannelItemWriter` を設定したうえで通常の `ChunkOrientedStepBuilder` を返します。生成されるステップは `ChunkOrientedStep` です。ライターはビルダー側で設定済みのため、変更してはいけません。
  - `chunk(int)` 呼び出し時の検証は次のとおりです。
    - `inputChannel` は必須(未指定は `IllegalArgumentException`)。
    - `outputChannel` と `messagingTemplate` はどちらか一方のみ指定(両方または両方なしは `IllegalStateException`)。
    - `messagingTemplate` 未指定なら、`outputChannel` をデフォルトチャネルとしたテンプレートが作られます。
- `RemoteChunkingManagerStepBuilder` と `RemoteChunkingManagerStepBuilderFactory` に非推奨アノテーションを付与。
- `EnableBatchIntegration` の Javadoc から Factory を外し、新ビルダーの例に差し替え。新ビルダーは Step ごとに `new` する前提で、autowire 用 Bean ではありません。
- ドキュメント・サンプル・テストも更新されています。

## 利用者への影響・対応
Before / After は次のとおりです(docs の例より)。

```java
// before
@Bean
public TaskletStep managerStep() {
    return this.managerStepBuilderFactory.get("managerStep")
                .chunk(100)
                .reader(itemReader())
                .outputChannel(requests())
                .inputChannel(replies())
                .build();
}

// after
@Bean
public Step managerStep(JobRepository jobRepository, PlatformTransactionManager transactionManager) {
    return new RemoteChunkingManagerBuilder("managerStep", jobRepository)
                .outputChannel(requests())
                .inputChannel(replies())
                .chunk(100)
                .reader(itemReader())
                .transactionManager(transactionManager)
                .build();
}
```

移行時の注意点:
- 既存コードは非推奨警告が出ますが、7.0 までは削除されません。
- チャネル(`outputChannel` / `inputChannel`)は `chunk(int)` より前に設定します。
- トランザクションマネージャの既定は resourceless です。旧 Factory はアプリケーションコンテキストのものを使っていたため、reader がトランザクショナルなリソースを必要とする場合は `transactionManager(...)` で明示します。
- `jobRepository` をコンストラクタで渡します。

## 補足
- `BatchIntegrationConfiguration` の差分は `@SuppressWarnings("removal")` の追加のみで、Factory の Bean 定義が削除されたかは入力から読み取れません(Javadoc 上の記述からは外れています)。
- 旧 `TaskletStep` と `ChunkOrientedStep` の実行時挙動の差(リトライ、スキップ、再起動など)は入力に記載がなく、本要約では扱いません。移行時は自環境での確認をお勧めします。
- 参照: https://github.com/spring-projects/spring-batch/issues/5598
