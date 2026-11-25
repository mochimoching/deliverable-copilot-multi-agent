# ChunkOrientedStep は、チャンクのトランザクションがコミットされなかった場合に step execution を復元しない

**Issue番号**: #5594
**状態**: closed | **作成者**: AndreaBosmanWork | **作成日**: 2026-10-13
**ラベル**: type: bug, in: core, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5594

## 内容

**バグの説明**

`ChunkOrientedStep` では、チャンク処理とメタデータ更新が成功した後に、トランザクション同期が `beforeCommit` から例外をスローすると、ロールバックが確認されているにもかかわらず、ジョブが `UNKNOWN` のままとなり再起動できなくなります。互換性のあるチャンクエンジンでは、同じ構成で `FAILED` が記録され、再起動にも成功します。

**環境**

- Spring Batch 6.0.5、Spring Framework 7.0.9、Java 17
- PostgreSQL 17.11、PostgreSQL JDBC 42.7.13、Testcontainers 2.0.5
- JDBC JobRepository とビジネス書き込みは、DataSource と DataSourceTransactionManager を共有
- デフォルトの Batch execution-context シリアライザ。アプリケーションコードやカスタムシリアライザはなし

追加のフレームワーク回帰テストでも、upstream の main（`de91ffcaccf887c32f86b683d9430ff2329e4818`、6.1.0-SNAPSHOT）で同じ失敗が再現します。

**再現手順**

1. チャンクサイズ 1 で、3 件のデータベースレコードを処理する。
2. レコード 1 を通常どおりコミットする。
3. 2 回目の書き込みで、`beforeCommit` が `IllegalStateException` をスローする `TransactionSynchronization` を登録する。
4. `afterCompletion` で `STATUS_ROLLED_BACK` を確認し、レコード 1 のビジネス更新のみがコミットされたままであることを確認する。
5. `FAILED` ステータスを確認し、同じ job instance を再起動してレコード 2 と 3 を処理する。

パラメータ化テストでは、`chunk(1, transactionManager)` と `chunk(1).transactionManager(transactionManager)` を比較します。互換性のある方は成功し、ネイティブの方は `expected FAILED but was UNKNOWN` で失敗します。

**期待される動作**

ロールバックが確認され、メタデータストレージが利用可能な場合、ジョブは `FAILED` となり、最後にコミットされたチェックポイントから再起動できるべきです。この失敗は物理的なコミットの前に発生し、確定的なロールバック結果が観測されます。

**実際の動作**

StepExecution のバージョンがメモリ上で 3 に進みます。ロールバックによりデータベース上のバージョンは 2 に戻りますが、メモリ上は 3 のままです。最後のメタデータ保存が失敗します:

```text
org.springframework.dao.OptimisticLockingFailureException:
Attempt to update step execution id=1 with wrong version (3), where current version is 2
```

ジョブは `UNKNOWN` となり、通常の再起動がブロックされます。

**最小限の再現可能な例**

[スタンドアロンの Maven/PostgreSQL 再現プロジェクト](https://github.com/AndreaBosmanWork/spring-batch/tree/reproduce/chunk-rollback/spring-batch-rollback-reproducer)。

Java 17 以上と Docker がある環境で、次を実行します:

```sh
git clone --depth 1 --branch reproduce/chunk-rollback https://github.com/AndreaBosmanWork/spring-batch.git
cd spring-batch
./mvnw -B -f spring-batch-rollback-reproducer/pom.xml test
```

2 回の実行が想定されます。互換性のある方は成功し、ネイティブの方はステータスのアサーションで失敗します。このブランチは、パッチ未適用のリリース版 6.0.5 の依存関係を使用しています。

**修正案**

別の [fix ブランチ](https://github.com/AndreaBosmanWork/spring-batch/tree/fix/chunk-rollback-metadata)に、TaskletStep のトランザクション完了時のリカバリに倣った修正候補があります。ロールバックが確認され、メタデータ更新が開始されていた場合にメタデータのスナップショットを復元し、read/skip のカウントは保持し、トランザクション結果が不明な場合は再起動を明示的にブロックします。

新しいテストでは、逐次/並行処理、保存された reader と writer のコンテキスト、beforeCommit とストリーム更新の失敗、コミット済みカウンタ、再起動、コミット結果が不確実な場合をカバーしています。upstream の 8 モジュールの Maven verification 全体が、実行された 3,045 テストで失敗/エラー 0、既存スイートが報告する 130 件のスキップで通過します。分離された PostgreSQL/H2 での検証、および 6.0.5 と main の両方に対する重点的なチェックも、この修正候補で通過します。

**関連する経緯**

[#5199](https://github.com/spring-projects/spring-batch/issues/5199) と [#5182](https://github.com/spring-projects/spring-batch/issues/5182) は 6.0.2 で解決済みで、それらの修正は 6.0.5 に含まれています。この再現は、処理成功後のメタデータ更新中またはトランザクション完了時に発生する、それより後の失敗を扱っています。


## コメント

### コメント 1 by fmbenhassine (2026-10-16)

これは妥当な issue です。ご報告と例の提供ありがとうございます！

問題は "beforeCommit" での例外だけにとどまらず、より広範であるため、それに合わせてタイトルを編集しました。
