*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

`JobParameters` の値を Bean に注入する際、現状は `@Value("#{jobParameters['year']}")` のように SpEL 式を文字列で書く必要があり冗長です。そこで専用の `@JobParameter` アノテーションの提供が提案されました（[#5563](https://github.com/spring-projects/spring-batch/issues/5563)、`type: feature` / `in: core`、6.1.0-RC1、closed）。

```java
// 現状
@Value("#{jobParameters['year']}") private Year year;

// 要望（value 省略時は変数名を使用。value で名前の明示も可）
@JobParameter private Year year;
```

議論の経緯:
- PR [#5564](https://github.com/spring-projects/spring-batch/pull/5564) で実装が進められました。
- `#{jobExecutionContext['…']}` / `#{stepExecutionContext['…']}` 向けの類似アノテーション（`@JobExecutionContextValue` / `@StepExecutionContextValue` が名前の候補）も議論されました。`@JobScope` の Bean にステップ用アノテーションを付けると実行時に失敗するため、名前とあわせて別 Issue で検討することになりました。
- 全パラメータをまとめて注入する別アノテーション `@JobParameters` の案も出ました（`Map` 型にするか `JobParameters` 型にするかは未決定）。
- 6.1 リリース前に、public な `JobParameterBeanFactoryPostProcessor` の名前を、将来のアノテーション追加にも合う汎用的な名前へ変更する方針になりました。

## 原因

機能要望のため、該当なしです。

## 対応方針

`@JobParameter` 本体は PR [#5564](https://github.com/spring-projects/spring-batch/pull/5564) で実装され、コミット [24d5fd176553](https://github.com/spring-projects/spring-batch/commit/24d5fd176553c30b43912cf7e0581e61e5c007d2)（2026-10-13）はその後のリネームのみです。このコミットにアノテーション本体は含まれません。

| 旧名 | 新名 | 可視性 |
|---|---|---|
| `JobParameterBeanFactoryPostProcessor` | `LateBindingBeanFactoryPostProcessor` | public |
| `JobParameterAutowireCandidateResolver` | `LateBindingAutowireCandidateResolver` | package-private |

`LateBindingBeanFactoryPostProcessor` は、`@JobParameter` を `@Value` と同じ式として解決する Spring の拡張点（`AutowireCandidateResolver`、注入候補や `@Value` 式を決める Spring 本体のインターフェース）を登録するクラスです。

**命名の理由**: 名前を、参照ドキュメントの「Late Binding of Job and Step Attributes」の節と合わせました。個別のアノテーション名ではなく仕組みの名前にしたので、`@JobExecutionContextValue` などが追加されても名前を変えずに済みます。

**業務への影響**:
- `@EnableBatchProcessing` または `DefaultBatchConfiguration` を使っている場合、これらの `@Import` が新名に差し替えられているため、利用側の変更は不要です。
- 独自の設定クラスやテスト設定で旧 public クラス `JobParameterBeanFactoryPostProcessor` を `@Import` や `new` で参照している場合は、`LateBindingBeanFactoryPostProcessor` への置換が必要です。置換しないとコンパイルエラーになります。
