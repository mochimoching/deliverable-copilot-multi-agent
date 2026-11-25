*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# チャンクトランザクションがコミットされない場合に ChunkOrientedStep がステップ実行を復元しない

**Issue番号**: #5594
**状態**: closed | **作成者**: AndreaBosmanWork | **作成日**: 2026-10-13
**ラベル**: type: bug, in: core, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5594

## 内容

**バグの説明**

`ChunkOrientedStep` では、チャンク処理とメタデータ更新が成功した後に、トランザクション同期が `beforeCommit` から例外をスローすると、ロールバックが確認されているにもかかわらず、ジョブが `UNKNOWN` のままとなり、再起動できなくなります。互換性チャンクエンジンでは、同じ設定で `FAILED` が記録され、正常に再起動できます。

**環境**

- Spring Batch 6.0.5、Spring Framework 7.0.9、Java 17
- PostgreSQL 17.11、PostgreSQL JDBC 42.7.13、Testcontainers 2.0.5
- JDBC `JobRepository` とビジネス上の書き込みは、`DataSource` と `DataSourceTransactionManager` を共有しています
- デフォルトの Batch 実行コンテキストシリアライザーを使用しており、アプリケーションコードやカスタムシリアライザーはありません

追加のフレームワーク回帰テストでも、upstream の main (`de91ffcaccf887c32f86b683d9430ff2329e4818`、6.1.0-SNAPSHOT) で同じ失敗が再現します。

**再現手順**

1. チャンクサイズ 1 で、3 件のデータベースレコードを処理します。
2. レコード 1 を通常どおりコミットします。
3. 2 回目の書き込みで、`beforeCommit` が `IllegalStateException` をスローする `TransactionSynchronization` を登録します。
4. `afterCompletion` で `STATUS_ROLLED_BACK` であること、およびレコード 1 のビジネス更新のみがコミットされたままであることを確認します。
5. `FAILED` ステータスを確認し、同じジョブインスタンスを再起動してレコード 2 と 3 を処理します。

パラメータ化テストでは、`chunk(1, transactionManager)` と `chunk(1).transactionManager(transactionManager)` を比較しています。互換性側は成功しますが、ネイティブ側は `expected FAILED but was UNKNOWN` で失敗します。

**期待される動作**

ロールバックが確認され、メタデータストレージが利用可能な場合、ジョブは `FAILED` となり、最後にコミットされたチェックポイントから再起動できるはずです。この失敗は物理的なコミットの前に発生し、確定したロールバック結果が観測されます。

**実際の動作**

StepExecution のバージョンがメモリ上で 3 に進みます。ロールバックによりデータベース上のバージョンは 2 に戻りますが、メモリ上は 3 のままです。最終的なメタデータの保存が失敗します:

```text
org.springframework.dao.OptimisticLockingFailureException:
Attempt to update step execution id=1 with wrong version (3), where current version is 2
```

ジョブは `UNKNOWN` となり、通常の再起動がブロックされます。

**最小限の完全な再現例**

[スタンドアロンの Maven/PostgreSQL 再現プロジェクト](https://github.com/AndreaBosmanWork/spring-batch/tree/reproduce/chunk-rollback/spring-batch-rollback-reproducer)。

Java 17 以上と Docker がある環境で、以下を実行してください:

```sh
git clone --depth 1 --branch reproduce/chunk-rollback https://github.com/AndreaBosmanWork/spring-batch.git
cd spring-batch
./mvnw -B -f spring-batch-rollback-reproducer/pom.xml test
```

2 回の実行が行われ、互換性側は成功し、ネイティブ側はステータスのアサーションで失敗することが期待されます。このブランチでは、パッチ未適用のリリース版 6.0.5 の依存関係を使用しています。

**修正案**

別の[修正ブランチ](https://github.com/AndreaBosmanWork/spring-batch/tree/fix/chunk-rollback-metadata)に候補の修正があります。これは TaskletStep のトランザクション完了時のリカバリに倣っています。メタデータの更新が開始されていた場合、ロールバックが確認された後にメタデータのスナップショットを復元し、読み取り数とスキップ数は保持し、トランザクション結果が不明な場合は再起動を明示的にブロックします。

新しいテストでは、逐次/並行処理、保存された reader と writer のコンテキスト、beforeCommit およびストリーム更新の失敗、コミット済みカウンター、再起動、コミット結果が不確定な場合をカバーしています。upstream の 8 モジュール全体の Maven 検証は、実行テスト 3,045 件、失敗/エラー 0 件、既存スイートが報告するスキップ 130 件で成功しています。PostgreSQL/H2 を分離した検証、および 6.0.5 と main の両方に対する重点的なチェックも、この候補で成功しています。

**関連する履歴**

[#5199](https://github.com/spring-projects/spring-batch/issues/5199) と [#5182](https://github.com/spring-projects/spring-batch/issues/5182) は 6.0.2 向けに解決され、その修正は 6.0.5 に含まれています。この再現は、処理が成功した後の、メタデータ更新またはトランザクション完了中に発生する、より後段の失敗を扱っています。


## コメント

### コメント 1 by fmbenhassine (2026-10-16)

これは有効な課題です。ご報告と例の提供をありがとうございます!

問題は "beforeCommit" での例外だけにとどまらず、より広範であるため、それに合わせてタイトルを編集しました。
