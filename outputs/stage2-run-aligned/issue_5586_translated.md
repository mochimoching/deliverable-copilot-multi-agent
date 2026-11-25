*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# MariaDB 6.0 マイグレーションで BATCH_JOB_SEQ のリネームに失敗する

**Issue番号**: #5586
**状態**: closed | **作成者**: ahrytsiuk | **作成日**: 2026-10-12
**ラベル**: type: bug, in: core, related-to: ddl-scripts, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5586

## 内容

**バグの説明**
Spring Batch 5.2 から 6.0 へアップグレードするための MariaDB の[マイグレーションスクリプト](https://github.com/spring-projects/spring-batch/blob/d1a0f99bd271a18994352a4bc96062f257085a25/spring-batch-core/src/main/resources/org/springframework/batch/core/migration/6.0/migration-mariadb.sql)では、サポートされていない `RENAME SEQUENCE` 文が使用されています。
```sql
RENAME SEQUENCE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ;
```
MariaDB ではシーケンスをリネームするために `RENAME TABLE` が必要です。その結果、`BATCH_JOB_SEQ` をリネームする前に、マイグレーションが SQL 構文エラーで失敗します。

**環境**
- Spring Batch: 6.0 マイグレーションスクリプト
- 移行元スキーマ: Spring Batch 5.2
- データベース: MariaDB 11.8.2
- MariaDB JDBC ドライバー

**再現手順**
1. MariaDB インスタンスを起動します。
2. Spring Batch 5.2 のスキーマでデータベースを初期化します。
3. [org/springframework/batch/core/migration/6.0/migration-mariadb.sql](https://github.com/spring-projects/spring-batch/blob/9a2ad579e74f9782caecb838525a88b6032d7198/spring-batch-core/src/main/resources/org/springframework/batch/core/migration/6.0/migration-mariadb.sql) を実行します。
4. マイグレーションが失敗することを確認します。

```console
org.opentest4j.AssertionFailedError: Unexpected exception thrown: org.springframework.jdbc.datasource.init.ScriptStatementFailedException: Failed to execute SQL script statement #1 of file [.../org/springframework/batch/core/migration/6.0/migration-mariadb.sql]: RENAME SEQUENCE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ

	at org.junit.jupiter.api.Assertions.assertDoesNotThrow(Assertions.java:3306)
	at org.springframework.batch.core.repository.migration.MariaDbMigrationScriptIntegrationTests.migrationScriptShouldBeValid(MariaDbMigrationScriptIntegrationTests.java:51)
Caused by: org.springframework.jdbc.datasource.init.ScriptStatementFailedException: Failed to execute SQL script statement #1 of file [.../org/springframework/batch/core/migration/6.0/migration-mariadb.sql]: RENAME SEQUENCE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ
	at org.springframework.jdbc.datasource.init.ScriptUtils.executeSqlScript(ScriptUtils.java:293)
	at org.springframework.jdbc.datasource.init.ResourceDatabasePopulator.populate(ResourceDatabasePopulator.java:254)
	at org.springframework.jdbc.datasource.init.DatabasePopulatorUtils.execute(DatabasePopulatorUtils.java:54)
	at org.springframework.jdbc.datasource.init.ResourceDatabasePopulator.execute(ResourceDatabasePopulator.java:269)
	at org.springframework.batch.core.repository.migration.MariaDbMigrationScriptIntegrationTests.lambda$migrationScriptShouldBeValid$0(MariaDbMigrationScriptIntegrationTests.java:51)
	at org.junit.jupiter.api.AssertDoesNotThrow.assertDoesNotThrow(AssertDoesNotThrow.java:52)
	at org.junit.jupiter.api.AssertDoesNotThrow.assertDoesNotThrow(AssertDoesNotThrow.java:39)
	... 2 more
Caused by: java.sql.SQLSyntaxErrorException: (conn=4) You have an error in your SQL syntax; check the manual that corresponds to your MariaDB server version for the right syntax to use near 'SEQUENCE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ' at line 1
	at org.mariadb.jdbc.export.ExceptionFactory.createException(ExceptionFactory.java:308)
	at org.mariadb.jdbc.export.ExceptionFactory.create(ExceptionFactory.java:402)
	at org.mariadb.jdbc.message.ClientMessage.readPacket(ClientMessage.java:196)
	at org.mariadb.jdbc.client.impl.StandardClient.readPacket(StandardClient.java:1524)
	at org.mariadb.jdbc.client.impl.StandardClient.readResults(StandardClient.java:1463)
	at org.mariadb.jdbc.client.impl.StandardClient.readResponse(StandardClient.java:1382)
	at org.mariadb.jdbc.client.impl.StandardClient.execute(StandardClient.java:1306)
	at org.mariadb.jdbc.Statement.executeInternal(Statement.java:1003)
	at org.mariadb.jdbc.Statement.execute(Statement.java:1132)
	at org.mariadb.jdbc.Statement.execute(Statement.java:471)
	at org.springframework.jdbc.datasource.init.ScriptUtils.executeSqlScript(ScriptUtils.java:261)
	... 8 more
```

**期待される動作**
マイグレーションスクリプトが正常に完了し、`BATCH_JOB_SEQ` が `BATCH_JOB_INSTANCE_SEQ` にリネームされるべきです。
MariaDB では、シーケンスは次のようにリネームする必要があります。
```sql
RENAME TABLE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ;
```
参照: [Table Operations that Work with Sequences](https://mariadb.com/docs/server/reference/sql-structure/sequences/sequence-overview#table-operations-that-work-with-sequences)

**最小限の完全な再現例**
[minimal complete verifiable example](https://github.com/ahrytsiuk/spring-batch-issue-5586)
