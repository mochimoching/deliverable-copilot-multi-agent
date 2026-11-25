# リトライなしのスキャンモードで誤解を招くログが出力される

**Issue番号**: #5527
**状態**: closed | **作成者**: se-meiser | **作成日**: 2026-09-07
**ラベル**: type: bug, in: core, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5527

## 内容

**バグの説明**

アプリケーションがアイテムをスキップするための制御フローとして専用の例外を使用する場合、その例外は設定済みの skip policy に受け入れられ、`SkipListener` はちょうど 1 回だけ呼び出されます。ジョブは正常に完了します。

ログ出力は、非推奨の `TaskletStep`/`FaultTolerantChunkProcessor` のパスと、現行の `ChunkOrientedStep` のパスとで異なります:

- 非推奨のパスでは、対応するスキャンの遷移を例外引数なしの `DEBUG` で記録します。これは通常の本番環境のログ設定では事実上見えません。
- `ChunkOrientedStep` は、同じ想定どおりの制御フローの遷移を `INFO` で記録し、`RetryException` を添付します:

  ```java
  if (this.faultTolerant && exception instanceof RetryException retryException
          && this.skipPolicy.shouldSkip(retryException.getCause(), -1)) {
      logger.info("Retry exhausted, entering scan mode for next transaction", retryException);
      // ...
  }
  ```

- ロールバックのパスでも、無条件に `ERROR` を記録します:

  ```java
  catch (Exception e) {
      logger.error("Rolling back chunk transaction", e);
      status.setRollbackOnly();
      // ...
  }
  ```

`.retryable(...)` の例外が設定されていない場合、`Retry exhausted` という文言は誤解を招きます。この場合、デフォルトの retry policy はリトライを 0 回行います。このメッセージが意味するのは、書き込みが失敗し、skip policy がその例外を受け入れた、ということだけです。ロールバックも skip/scan フローの想定された一部であり、アプリケーションの障害ではありません。

**環境**

- Spring Batch: `6.0.5`
- Spring Boot: `4.1.1`
- Java: `17+`（添付プロジェクトは Java `25` で実行）
- ビルドツール: Maven `3+`
- データベース: なし。再現プロジェクトは `ResourcelessJobRepository` と `ResourcelessTransactionManager` を使用
- ロギング: SLF4J と Logback を用いた Spring Boot スターターのロギング
- オペレーティングシステム: macOS（この挙動は OS 固有ではないと想定）

**再現手順**

1. 添付の ZIP をダウンロードして展開します。
2. 展開したプロジェクトのディレクトリに移動します。
3. 次を実行します:

   ```shell
   mvn clean spring-boot:run -Dspring-boot.run.arguments=--spring.main.web-application-type=none
   ```

4. `taskletJob` と `chunkOrientedJob` の両方のログを確認します。

このアプリケーションは、1 つのアイテムに対して `DeliberateSkipException` をスローする writer を設定し、その例外を skippable として設定し、retryable な例外は一切設定しません。`SkipListener` はアプリケーションレベルのスキップメッセージを 1 つ記録し、両方のジョブが `COMPLETED` で終了します。

`chunkOrientedJob` の出力には、次と同等のメッセージが含まれます:

```text
INFO  ... ChunkOrientedStep - Retry exhausted, entering scan mode for next transaction
      org.springframework.core.retry.RetryException: Retry policy for operation 'Retryable write operation' exhausted; aborting execution
ERROR ... ChunkOrientedStep - Rolling back chunk transaction
      org.springframework.core.retry.RetryException: Retry policy for operation 'Retryable write operation' exhausted; aborting execution
INFO  ... ChunkOrientedStep - Rollback complete, scan will execute in next transaction
INFO  ... ChunkOrientedStep - Executing scan in new transaction after rollback
```

`taskletJob` は非推奨の chunk-builder オーバーロードを使用しており、対応するスキャンの遷移を、同じ `INFO` メッセージや例外のスタックトレースなしで出力します。

**期待される動作**

リトライが設定されておらずジョブが正常に完了する場合、想定どおりの skip/scan の遷移で、例外のスタックトレース付きの誤解を招く `INFO` や `ERROR` のメッセージを出力すべきではありません。診断ログは、これが受け入れられたスキップと想定されたロールバックであることを反映すべきであり、リトライの枯渇やアプリケーションの障害であるかのように示すべきではありません。

具体的には:

- retryable な例外が設定されていない場合、スキャンの遷移を `Retry exhausted` と説明すべきではありません。
- skip policy に受け入れられた例外は、チャンクトランザクションが想定どおりの skip/scan アルゴリズムの一部としてロールバックされるというだけの理由で、無条件の `ERROR` ログを出力すべきではありません。
- この診断ログは従来の `FaultTolerantChunkProcessor` のパスとは異なっており、Spring Batch 6 のリファレンスドキュメントやマイグレーションガイドにも記載されていません。
- 想定どおりの skip/scan の遷移は、内部の `RetryException` を伴わずに適切な低いレベルで記録するか、受け入れられたスキップと想定されたトランザクションのロールバックを正確に説明する文言を使用すべきです。

ジョブは、この再現プロジェクトと同様に、`SkipListener` を 1 回呼び出し、正常に完了し続けるべきです。

**最小限の完全な再現例**

添付の ZIP には、完全な Maven の Spring Boot アプリケーションが含まれています。内容は次のとおりです:

- `spring-boot-starter-batch` を含み、Spring Boot の依存関係管理によって解決される Spring Batch `6.0.5` を使用する `pom.xml`。
- 両方の実行パスを含む `src/main/java/com/example/batch/SkipLoggingReproducerApplication.java`。
- `ResourcelessJobRepository` を使用した、インメモリでデータベース不要のセットアップ。
- 1 つのアイテムに対して専用の例外をスローする writer。
- アイテムが正常にスキップされることを示す skip policy と `SkipListener`。

このプロジェクトは次のコマンドで検証されました:

```shell
mvn clean verify
```

両方のジョブはステータス `COMPLETED` で完了します。問題はジョブの失敗ではなく、想定どおりの skip/scan の遷移中に出力される、誤解を招く一貫性のないログです。

[spring-batch-skip-logging-reproducer.zip](https://github.com/user-attachments/files/31918730/spring-batch-skip-logging-reproducer.zip)

## コメント

### コメント 1 by seanxuu (2026-09-09)

この issue に取り組みたいです。

非リトライ対象の例外に対する skip/scan のパスを再現し、期待されるログレベルとメッセージについて焦点を絞ったアサーションを追加し、成功するスキップの挙動と `SkipListener` の呼び出しが 1 回であることは変更しないようにする予定です。その後、誤解を招く診断ログのみを調整し、関連する Spring Batch のテストとプロジェクトのビルドを実行します。

この issue には現在、assignee、コントリビューターの担当表明、リンクされた PR、コミット、ブランチ、タイムライン上の重複のシグナルがありません。進める前に、この方向性がプロジェクトに適しているかどうかお知らせください。

### コメント 2 by seanxuu (2026-09-09)

この issue に対してドラフト PR #5530 を作成しました: https://github.com/spring-projects/spring-batch/pull/5530

想定される skip/scan のロールバックのログを DEBUG に絞り、誤解を招くリトライ枯渇のメッセージを置き換え、出力されるログイベントに対する回帰アサーションを追加しています。

### コメント 3 by fmbenhassine (2026-09-30)

これは妥当な issue です。ご報告ありがとうございます!

確かに v5 とは違いがあります。フレームワークのその部分のログレベルは見直すべきだと思います。

次のリリースで修正を計画します。
