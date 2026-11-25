# BatchObservabilityBeanPostProcessorが手動で設定された`observationRegistry`を尊重しない

**Issue番号**: #5566
**状態**: closed | **作成者**: ahrytsiuk | **作成日**: 2026-09-29
**ラベル**: type: bug, in: core, related-to: observability
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5566

## 内容

**バグの説明**
Spring Batchの設定を定義する際、特定の`Job`や`Step`に対してカスタムの`ObservationRegistry`を定義できます。
```java
@Bean
public Job simpleLogJob1(JobRepository jobRepository, Step step1) {
    return new JobBuilder("simpleLogJob1", jobRepository)
            .incrementer(new RunIdIncrementer())
            .observationRegistry(new JobObservationRegistry())   // <---- customization
            .start(step1)
            .build();
}

@Bean
public Step step1(JobRepository jobRepository) {
    return new StepBuilder("step1", jobRepository)
            .tasklet(new EchoTasklet())
            .observationRegistry(new StepObservationRegistry())  // <---- customization
            .build();
}
```

しかし、Spring Contextに`ObservationRegistry`型のBeanが存在する場合、このカスタマイズは`BatchObservabilityBeanPostProcessor`によって上書きされてしまいます。
- Jobの上書き: https://github.com/spring-projects/spring-batch/blob/c15bfcea73563f46fa030e1e978c50666b422019/spring-batch-core/src/main/java/org/springframework/batch/core/configuration/annotation/BatchObservabilityBeanPostProcessor.java#L66-L68
- Stepの上書き: https://github.com/spring-projects/spring-batch/blob/c15bfcea73563f46fa030e1e978c50666b422019/spring-batch-core/src/main/java/org/springframework/batch/core/configuration/annotation/BatchObservabilityBeanPostProcessor.java#L69-L71


**環境**
- Spring Batchバージョン: 5.0+

**再現手順**

1. `ObservationRegistry`型のBeanを設定する
2. バッチ`Job`に対して、（1とは異なる）カスタムの`ObservationRegistry`を設定する
3. アプリケーションを実行し、`Job`（2で定義したもの）に何が設定されているかを確認する

**期待される動作**

- `Job`や`Step`に対してカスタム定義された`ObservationRegistry`が使用され、`BatchObservabilityBeanPostProcessor`によって上書きされないこと。

**最小限の完全な再現例**
- [gist](https://gist.github.com/ahrytsiuk/d7951ba37a50b3ebd4cb3ada34bf18f2)
- この問題を再現する[最小限の完全で検証可能な例](https://github.com/ahrytsiuk/spring-batch-issue)




## コメント

### コメント 1 by fmbenhassine (2026-10-05)

これは妥当な課題です。ご報告いただき、また例も提供していただきありがとうございます。
