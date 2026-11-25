# `JobParameters` 内の変数により便利にアクセスするための `@JobParameter` アノテーションを提供する。

**Issue番号**: #5563
**状態**: closed | **作成者**: zhujianxintian | **作成日**: 2026-09-28
**ラベル**: type: feature, in: core
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5563

## 内容

**期待する動作**

`JobParameters` 内のパラメータにアクセスするために、次のようなコードを使いたいです。

`@JobParameter` は空のままにでき、その場合はデフォルトでこのローカル変数の名前が使われます。あるいは、`value` に名前を手動で指定して、対応する変数を探すこともできます。

注: これにより、コンバーターを個別に指定するといった追加機能も、より簡単に加えられるようになるかもしれません。

```java
@JobParameter
private Year year;
```

**現在の動作**

現在は次のようになっており、かなり融通が利かず、あまり使いやすくないと感じます。

```java
@Value("#{jobParameters['year']}")
private Year year;
```

## コメント

### コメント 1 by quaff (2026-09-30)

@zhujianxintian https://github.com/spring-projects/spring-batch/pull/5564 を検証していただけますか？

### コメント 2 by zhujianxintian (2026-09-30)

@quaff ご協力とコントリビューションに心から感謝します！

### コメント 3 by fmbenhassine (2026-10-01)

素晴らしいアイデアです！機能リクエストをありがとうございます。

#5564 をレビューして、6.1 に含められるか確認します。

同じ仕組みで、同様のアノテーションにより `#{jobExecutionContext['…']}` や `#{stepExecutionContext['…']}` もカバーできるでしょう。また、`@JobParameters` については、注入される型（`Map` か `JobParameters` か）や、`private @JobParameters JobParameters` のようなスニペットでの名前の衝突について、別途設計の議論が必要です。

ただ、まずは `@JobParameter` を評価しましょう。

### コメント 4 by quaff (2026-10-08)

`@JobExecutionContext` と `@StepExecutionContext` を導入する価値はありますか？ 私がコントリビュートしたいです。

### コメント 5 by fmbenhassine (2026-10-12)

@quaff はい、https://github.com/spring-projects/spring-batch/issues/5563#issuecomment-5939697016 で述べたとおり、そう思います。混乱を避けるため、命名を考える必要があります。実際、`@JobExecutionContext ExecutionContext ctx` はコンテキスト全体を注入するように読めますが、（私が意図した）このアノテーションは `@JobParameter` と同様に 1 つの値を注入するものです。おそらく `@JobExecutionContextValue` と `@StepExecutionContextValue` なら、「そのコンテキストからの 1 つの値」と読めるでしょう。また「Value」という語は、それらが置き換える `@Value("#{JobExecutionContext['...']}")` の `@Value` とも対応します。

ただし、命名は難しいものの、混乱を招かないよい名前はまだ見つけられるでしょうが、それよりもこれらのアノテーションのスコープの妥当性のほうが気がかりです。`@JobScope` の Bean からは `jobExecutionContext` しか見えませんが、`@StepScope` の Bean からは両方が見えます。Job スコープの Bean に step 用のバリアントを使うと、実行時に失敗します。デスクリプタが要求元 Bean のスコープを公開していない可能性があるため、リゾルバーがこれを早期に検出できるかどうかは分かりません。

いずれにせよ、これは別の issue で議論すべきで、おそらく 6.2 以降になるでしょう。

### コメント 6 by quaff (2026-10-13)

> 10\. [@quaff](https://github.com/quaff) yes, I think so, as mentioned in [#5563 (comment)](https://github.com/spring-projects/spring-batch/issues/5563#issuecomment-5939697016). We need to think about the naming to avoid any confusion. In fact, `@JobExecutionContext ExecutionContext ctx` would suggest injecting the whole context, but the annotation (as I intended it) would inject one value in a similar fashion to `@JobParameter`.  Probably `@JobExecutionContextValue` and `@StepExecutionContextValue` reads as "one value from that context". The term "Value" also pairs with the `@Value` they replace in `@Value("#{JobExecutionContext['...']}")`.
>      However, while naming is hard and we can still manage to find a good non-confusing name, I am more concerned about the scope validity of those annotations:  `@JobScope` beans only see `jobExecutionContext`, while `@StepScope` beans see both. Using the step variant on a job-scoped bean fails at runtime. I don't know whether the resolver can detect that early, because the descriptor may not expose the requesting bean's scope.
>      In any case, this should be discussed in a separate issue, likely for 6.2 or later.

`JobParameterAutowireCandidateResolver` と `JobParameterBeanFactoryPostProcessor` は `@JobParameter` を `@Value` に変換するだけではなくなるので、もっと一般的な名前にリネームすべきだと思います。`BatchAnnotation*` はどうでしょうか？ @fmbenhassine

### コメント 7 by fmbenhassine (2026-10-13)

@quaff はい、（命名とスコープが別の issue で整理されたうえで）それらのアノテーションを導入することになれば、BFPP をより汎用的な名前にリネームできます。

### コメント 8 by quaff (2026-10-13)

> if we decide to introduce those annotations (once the naming and scope are clarified in a separate issue), we can rename the BFPP to a more generic name.

 `JobParameterAutowireCandidateResolver` は package-private ですが、`JobParameterBeanFactoryPostProcessor` は public なので、6.1 のリリース前にリネームしたほうがよいです。


### コメント 9 by fmbenhassine (2026-10-13)

はい、後から public API が変わるのを避けるため、その対応を進めています。

> what about `BatchAnnotation*`, WDYT?

それは広すぎる名前です。late binding とは無関係な他の batch アノテーションもあるためです。私なら `LateBindingBeanFactoryPostProcessor` と `LateBindingAutowireCandidateResolver` にします。ドキュメントの内容と合致するからです。リファレンスのページは "Late Binding of Job and Step Attributes" です。`@JobParameter`、`@JobExecutionContextValue`、`@StepExecutionContextValue` はいずれも、そこに記載されている SpEL による late binding 式の省略形です。

また、この名前はアノテーションの一覧ではなく仕組みを表しているので、後で再度リネームする必要もありません。ここでの public な BPP は、`BatchObservabilityBeanPostProcessor` や `AutomaticJobRegistrarBeanPostProcessor` のように、その機能にちなんで名付けられています。Spring 自身のリゾルバーも、たとえば `QualifierAnnotationAutowireCandidateResolver` のように同じ読み方になります。

リネームのコミットを追って行います。
