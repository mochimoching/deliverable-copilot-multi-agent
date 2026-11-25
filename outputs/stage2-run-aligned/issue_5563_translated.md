*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# JobParameters内の変数により便利にアクセスするための @JobParameter アノテーションを提供してほしい

**Issue番号**: #5563
**状態**: closed | **作成者**: zhujianxintian | **作成日**: 2026-09-28
**ラベル**: type: feature, in: core
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5563

## 内容

**期待される動作**

`JobParameters`内のパラメータにアクセスするために、次のようなコードを使いたいです。

`@JobParameter`は空のままにすることができ、その場合はデフォルトでこのローカル変数の名前が使用されます。または、`value`に名前を手動で指定して、対応する変数を検索することもできます。

注：これにより、コンバーターを個別に指定するなど、追加機能を加えることも容易になるかもしれません。

```java
@JobParameter
private Year year;
```

**現在の動作**

現在は次のようになっており、かなり融通が利かず、あまり使いやすくないと感じています。

```java
@Value("#{jobParameters['year']}")
private Year year;
```

## コメント

### コメント 1 by quaff (2026-09-30)

@zhujianxintian https://github.com/spring-projects/spring-batch/pull/5564 を検証していただけますか？

### コメント 2 by zhujianxintian (2026-09-30)

@quaff ご協力とコントリビュートに心から感謝します！

### コメント 3 by fmbenhassine (2026-10-01)

素晴らしいアイデアです！機能リクエストをありがとうございます。

[#5564](https://github.com/spring-projects/spring-batch/issues/5564) をレビューし、6.1 に含められるか検討します。

同じ仕組みで、同様のアノテーションを使って`#{jobExecutionContext['…']}`や`#{stepExecutionContext['…']}`にも対応できるはずです。また、`@JobParameters`については、注入される型（`Map`か`JobParameters`か）や、`private @JobParameters JobParameters`のようなスニペットにおける名前の衝突について、別途設計の議論が必要です。

ただし、まずは`@JobParameter`を評価しましょう。

### コメント 4 by quaff (2026-10-08)

`@JobExecutionContext`と`@StepExecutionContext`を導入する価値はあるでしょうか？ぜひコントリビュートしたいです。

### コメント 5 by fmbenhassine (2026-10-12)

@quaff はい、https://github.com/spring-projects/spring-batch/issues/5563#issuecomment-5939697016 で述べたとおり、そう思います。混乱を避けるために、命名を検討する必要があります。実際、`@JobExecutionContext ExecutionContext ctx`ではコンテキスト全体を注入するように見えますが、（私が意図していた）このアノテーションは、`@JobParameter`と同様の方法で1つの値を注入するものです。おそらく`@JobExecutionContextValue`と`@StepExecutionContextValue`であれば、「そのコンテキストからの1つの値」と読めるでしょう。「Value」という語は、置き換え対象である`@Value("#{JobExecutionContext['...']}")`の`@Value`とも対応します。

ただ、命名は難しいものの、混乱を招かない良い名前はまだ見つけられると思います。それよりも、これらのアノテーションのスコープの妥当性のほうが気がかりです。`@JobScope`のBeanからは`jobExecutionContext`しか見えませんが、`@StepScope`のBeanからは両方が見えます。ジョブスコープのBeanでステップ用のバリアントを使うと、実行時に失敗します。ディスクリプターが要求元Beanのスコープを公開していない可能性があるため、リゾルバーがこれを早期に検出できるかどうかはわかりません。

いずれにせよ、これは別の課題で議論すべきで、おそらく6.2以降になるでしょう。

### コメント 6 by quaff (2026-10-13)

> 10\. [@quaff](https://github.com/quaff) yes, I think so, as mentioned in [#5563 (comment)](https://github.com/spring-projects/spring-batch/issues/5563#issuecomment-5939697016). We need to think about the naming to avoid any confusion. In fact, `@JobExecutionContext ExecutionContext ctx` would suggest injecting the whole context, but the annotation (as I intended it) would inject one value in a similar fashion to `@JobParameter`.  Probably `@JobExecutionContextValue` and `@StepExecutionContextValue` reads as "one value from that context". The term "Value" also pairs with the `@Value` they replace in `@Value("#{JobExecutionContext['...']}")`.
>      However, while naming is hard and we can still manage to find a good non-confusing name, I am more concerned about the scope validity of those annotations:  `@JobScope` beans only see `jobExecutionContext`, while `@StepScope` beans see both. Using the step variant on a job-scoped bean fails at runtime. I don't know whether the resolver can detect that early, because the descriptor may not expose the requesting bean's scope.
>      In any case, this should be discussed in a separate issue, likely for 6.2 or later.

`JobParameterAutowireCandidateResolver`と`JobParameterBeanFactoryPostProcessor`は、`@JobParameter`を`@Value`に変換するだけではなくなるので、より汎用的な名前に変更すべきだと思います。`BatchAnnotation*`はどうでしょうか？ @fmbenhassine のご意見を伺いたいです。

### コメント 7 by fmbenhassine (2026-10-13)

@quaff はい、それらのアノテーションを導入することになった場合（命名とスコープが別の課題で明確になった後に）、BFPPをより汎用的な名前に変更できます。

### コメント 8 by quaff (2026-10-13)

> if we decide to introduce those annotations (once the naming and scope are clarified in a separate issue), we can rename the BFPP to a more generic name.

`JobParameterAutowireCandidateResolver`はpackage-privateですが、`JobParameterBeanFactoryPostProcessor`はpublicなので、6.1のリリース前に名前を変更するほうが望ましいです。


### コメント 9 by fmbenhassine (2026-10-13)

はい、後でパブリックAPIが変更されることを避けるために、その作業を進めています。

> what about `BatchAnnotation*`, WDYT?

それは範囲の広い名前で、レイトバインディングに関係_しない_他のバッチ用アノテーションもあります。ドキュメントと一致するため、`LateBindingBeanFactoryPostProcessor`と`LateBindingAutowireCandidateResolver`にしたいと思います。リファレンスのページは「Late Binding of Job and Step Attributes」です。`@JobParameter`、`@JobExecutionContextValue`、`@StepExecutionContextValue`は、そこに記載されているSpELによるレイトバインディング式の省略記法です。

また、この名前はアノテーションの一覧ではなく仕組みを表しているため、再度の名前変更は不要です。ここでのパブリックなBPPは、`BatchObservabilityBeanPostProcessor`や`AutomaticJobRegistrarBeanPostProcessor`のように、その機能にちなんで名付けられています。Spring自体のリゾルバーも同様の読み方になります。たとえば`QualifierAnnotationAutowireCandidateResolver`です。

名前変更のコミットを続けて行います。
