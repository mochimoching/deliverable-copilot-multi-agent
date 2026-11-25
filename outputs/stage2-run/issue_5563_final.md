# Issue #5563 要約: `@JobParameter` によるジョブパラメータ注入と late binding 関連クラスのリネーム

## 概要
Issue #5563（マイルストーン 6.1.0-RC1、closed）は、`JobParameters` の値をより簡単に注入できる `@JobParameter` アノテーションの機能要望です。機能自体は PR #5564 で対応されました（実装の詳細は入力にないため不明）。今回添付されている commit 24d5fd176553 は `@JobParameter` 本体ではなく、関連クラス（`BeanFactoryPostProcessor` は public）のリネームです。

## 問題
現状は、ジョブパラメータを注入するのに SpEL を使った `@Value` を書く必要があります。

```java
@Value("#{jobParameters['year']}")
private Year year;
```

起票者はこれを硬直的で使いにくいとし、次のような書き方を求めました。

```java
@JobParameter
private Year year;
```

- 起票者の期待は、`value` を省略した場合は変数名を既定のパラメータ名にし、必要なら `value` で名前を指定する、というものです。これは issue の期待動作であり、diff に現れた実装結果ではありません。最終実装でこの仕様になったかは入力にありません。
- 付随案として、コンバータの個別指定にも触れていますが、実装の有無は不明です。

コメントでは、`@JobParameter` に続いて `jobExecutionContext` / `stepExecutionContext` 用の同様のアノテーションを足す案も出ました。ただし命名とスコープの妥当性を別 issue で議論するとされ、6.2 以降の見込みです。実装済みではありません。

## 修正内容
commit 24d5fd176553 は、次のリネームと参照箇所の修正のみです（`spring-batch-core` モジュール）。

| 旧名 | 新名 | 可視性 |
|---|---|---|
| `JobParameterBeanFactoryPostProcessor` | `LateBindingBeanFactoryPostProcessor` | public |
| `JobParameterAutowireCandidateResolver` | `LateBindingAutowireCandidateResolver` | package-private |

- `LateBindingBeanFactoryPostProcessor`: `DefaultListableBeanFactory` の autowire candidate resolver を `LateBindingAutowireCandidateResolver` で包んで設定します。
- `LateBindingAutowireCandidateResolver`: `@JobParameter` の付いたフィールドやパラメータを処理し、それ以外は委譲先の resolver に任せます。
- `EnableBatchProcessing.java` と `DefaultBatchConfiguration.java` の `@Import` を新クラスに変更しました。
- `JobParameterInjectionTests.java` の参照を新名に変更しました。

リネームの理由（コメント 8・9 より）:
- 将来 `@JobExecutionContextValue` などを追加しても名前を変えずに済むよう、アノテーションの一覧ではなく仕組みを表す名前にするため。
- `JobParameterBeanFactoryPostProcessor` は public なので、6.1 リリース前に変えて後からの公開 API 変更を避けるため。
- 参照ドキュメント「Late Binding of Job and Step Attributes」の用語に合わせるため。
- 当初案の `BatchAnnotation*` は、late binding と無関係なアノテーションも含まれて範囲が広すぎるため却下されました。

## 利用者への影響・対応
- `@EnableBatchProcessing` または `DefaultBatchConfiguration` を使っていれば、`LateBindingBeanFactoryPostProcessor` が `@Import` されます。これらを使わない構成での挙動は入力にありません。
- 旧 `JobParameterBeanFactoryPostProcessor` を直接参照するコードは、新名への書き換えが必要です。
- `@JobParameter` の適用対象は、Javadoc で job / step スコープの bean 向けと説明されています。それ以外の挙動は入力にないため、公式ドキュメントでの確認を推奨します。

## 補足
- commit 24d5fd176553 は、コメント 9 の「リネームの commit を追加する」というフォローアップ commit と整合します。
- `@JobParameters`（`Map` と `JobParameters` のどちらを注入するか）は別途設計議論が必要とされ、結論は入力にありません。
- ExecutionContext 向けアノテーション（`@JobExecutionContextValue` / `@StepExecutionContextValue`）は、`@JobScope` の bean で step 用を使うと実行時に失敗する点が懸念されており、未決定です。
