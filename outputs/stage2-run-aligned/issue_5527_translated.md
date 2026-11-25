*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# リトライなしのスキャンモードにおける誤解を招くログ

**Issue番号**: #5527
**状態**: closed | **作成者**: se-meiser | **作成日**: 2026-09-07
**ラベル**: type: bug, in: core, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5527

## 内容

**バグの説明**

アプリケーションがアイテムをスキップするための制御フローとして専用の例外を使用する場合、その例外は設定済みのスキップポリシーに受け入れられ、`SkipListener`はちょうど1回呼び出されます。ジョブは正常に完了します。

ログ出力は、非推奨の`TaskletStep`/`FaultTolerantChunkProcessor`のパスと、現在の`ChunkOrientedStep`のパスとで異なります。

- 非推奨のパスでは、対応するスキャンの遷移を例外引数なしで`DEBUG`レベルで出力します。これは通常の本番環境のログ設定ではほぼ見えません。
- `ChunkOrientedStep`では、同じ想定内の制御フローの遷移を`INFO`レベルで出力し、`RetryException`を添付します。

  ```java
  if (this.faultTolerant && exception instanceof RetryException retryException
          && this.skipPolicy.shouldSkip(retryException.getCause(), -1)) {
      logger.info("Retry exhausted, entering scan mode for next transaction", retryException);
      // ...
  }
  ```

- ロールバックのパスでも、無条件に`ERROR`を出力します。

  ```java
  catch (Exception e) {
      logger.error("Rolling back chunk transaction", e);
      status.setRollbackOnly();
      // ...
  }
  ```

`.retryable(...)`の例外が設定されていない場合、`Retry exhausted`という文言は誤解を招きます。この場合、デフォルトのリトライポリシーはリトライを0回しか行いません。このメッセージが意味するのは、書き込みが失敗し、スキップポリシーがその例外を受け入れたということだけです。また、ロールバックもスキップ/スキャンのフローにおける想定内の一部であり、アプリケーションの障害ではありません。

**環境**

- Spring Batch: `6.0.5`
- Spring Boot: `4.1.1`
- Java: `17+`（添付のプロジェクトはJava `25`で実行しました）
- ビルドツール: Maven `3+`
- データベース: なし。再現プロジェクトでは`ResourcelessJobRepository`と`ResourcelessTransactionManager`を使用しています
- ロギング: SLF4JとLogbackを用いたSpring Bootスターターのロギング
- オペレーティングシステム: macOS（この動作はOS固有ではないと考えられます）

**再現手順**

1. 添付のZIPをダウンロードして展開します。
2. 展開したプロジェクトのディレクトリに移動します。
3. 次を実行します。

   ```shell
   mvn clean spring-boot:run -Dspring-boot.run.arguments=--spring.main.web-application-type=none
   ```

4. `taskletJob`と`chunkOrientedJob`の両方のログを確認します。

このアプリケーションでは、1つのアイテムに対して`DeliberateSkipException`をスローするライターを設定し、その例外をスキップ可能として設定しており、リトライ可能な例外は一切設定していません。`SkipListener`はアプリケーションレベルのスキップメッセージを1件出力し、両方のジョブが`COMPLETED`で終了します。

`chunkOrientedJob`の出力には、次と同等のメッセージが含まれます。

```text
INFO  ... ChunkOrientedStep - Retry exhausted, entering scan mode for next transaction
      org.springframework.core.retry.RetryException: Retry policy for operation 'Retryable write operation' exhausted; aborting execution
ERROR ... ChunkOrientedStep - Rolling back chunk transaction
      org.springframework.core.retry.RetryException: Retry policy for operation 'Retryable write operation' exhausted; aborting execution
INFO  ... ChunkOrientedStep - Rollback complete, scan will execute in next transaction
INFO  ... ChunkOrientedStep - Executing scan in new transaction after rollback
```

`taskletJob`は非推奨のチャンクビルダーのオーバーロードを使用しており、同じ`INFO`メッセージや例外のスタックトレースを出力せずに、対応するスキャンの遷移を行います。

**期待される動作**

リトライが設定されておらず、ジョブが正常に完了する場合、想定内のスキップ/スキャンの遷移で、例外のスタックトレースを伴う誤解を招く`INFO`や`ERROR`のメッセージを出力すべきではありません。診断ログは、これが使い果たされたリトライやアプリケーションの障害ではなく、受け入れられたスキップと想定内のロールバックであることを反映するべきです。

具体的には次のとおりです。

- リトライ可能な例外が設定されていない場合、スキャンの遷移を`Retry exhausted`と表現すべきではありません。
- スキップポリシーに受け入れられた例外に対して、想定内のスキップ/スキャンのアルゴリズムの一部としてチャンクトランザクションがロールバックされるというだけの理由で、無条件の`ERROR`ログを出力すべきではありません。
- この診断ログは従来の`FaultTolerantChunkProcessor`のパスとは異なっており、Spring Batch 6のリファレンスドキュメントや移行ガイドにも記載されていません。
- 想定内のスキップ/スキャンの遷移は、内部の`RetryException`を含めずに適切に低いレベルでログ出力するか、受け入れられたスキップと想定内のトランザクションロールバックを正確に説明する文言を使用するべきです。

このリプロデューサーで確認できるように、ジョブは引き続き`SkipListener`を1回呼び出し、正常に完了する必要があります。

**最小限の完全な再現例**

添付のZIPには、完全なMaven Spring Bootアプリケーションが含まれています。内容は次のとおりです。

- `spring-boot-starter-batch`を含み、Spring Bootの依存関係管理によってSpring Batch `6.0.5`が解決される`pom.xml`
- 両方の実行パスを含む`src/main/java/com/example/batch/SkipLoggingReproducerApplication.java`
- `ResourcelessJobRepository`を使用した、インメモリでデータベース不要のセットアップ
- 1つのアイテムに対して専用の例外をスローするライター
- アイテムが正常にスキップされることを示すスキップポリシーと`SkipListener`

プロジェクトは次のコマンドで検証しました。

```shell
mvn clean verify
```

両方のジョブはステータス`COMPLETED`で完了します。問題はジョブの失敗ではなく、想定内のスキップ/スキャンの遷移中のログが誤解を招き、かつ一貫していないことです。

[spring-batch-skip-logging-reproducer.zip](https://github.com/user-attachments/files/31918730/spring-batch-skip-logging-reproducer.zip)

## コメント

### コメント 1 by seanxuu (2026-09-09)

この課題に取り組みたいと思います。

非リトライ対象の例外におけるスキップ/スキャンのパスを再現し、想定されるログレベルとメッセージに対する焦点を絞ったアサーションを追加し、スキップが正常に行われる動作と`SkipListener`が1回だけ呼び出される動作は変更しないようにする予定です。その後、誤解を招く診断ログのみを調整し、関連するSpring Batchのテストとプロジェクトのビルドを実行します。

この課題には現在、担当者、コントリビューターの申告、リンクされたPR、コミット、ブランチ、タイムライン上の重複の兆候はありません。進める前に、この方向性がプロジェクトに適しているかお知らせください。

### コメント 2 by seanxuu (2026-09-09)

この課題に対してドラフトPR [#5530](https://github.com/spring-projects/spring-batch/issues/5530) を作成しました: https://github.com/spring-projects/spring-batch/pull/5530

想定内のスキップ/スキャンのロールバックのログを`DEBUG`に絞り込み、誤解を招くリトライ枯渇のメッセージを置き換え、出力されるログイベントに対する回帰アサーションを追加しています。

### コメント 3 by fmbenhassine (2026-09-30)

これは妥当な課題です。ご報告ありがとうございます！

確かにv5とは違いがあります。フレームワークのその部分のログレベルは見直すべきだと思います。

次のリリースで修正を計画します。
