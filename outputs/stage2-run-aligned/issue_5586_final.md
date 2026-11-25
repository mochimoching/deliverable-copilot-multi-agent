*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

MariaDB 用の Spring Batch 5.2 → 6.0 マイグレーションスクリプト（[migration-mariadb.sql](https://github.com/spring-projects/spring-batch/blob/d1a0f99bd271a18994352a4bc96062f257085a25/spring-batch-core/src/main/resources/org/springframework/batch/core/migration/6.0/migration-mariadb.sql)）が、1文目で SQL 構文エラーになります（[#5586](https://github.com/spring-projects/spring-batch/issues/5586)）。

**背景**: 6.0 では ID 採番用シーケンス `BATCH_JOB_SEQ` を `BATCH_JOB_INSTANCE_SEQ` に改名します。MariaDB のシーケンスは、内部的に1行だけのテーブルとして実装されています。そのため専用の `RENAME SEQUENCE` はなく、テーブルと同じ `RENAME TABLE` で改名します（参照: [Table Operations that Work with Sequences](https://mariadb.com/docs/server/reference/sql-structure/sequences/sequence-overview#table-operations-that-work-with-sequences)）。

**業務への影響**:

- 最初の文で失敗するため、以降の文は実行されません。
- 構文エラーで止まった時点で DB に部分適用が残るかどうかは、入力からは分かりません。
- 回避策として、スクリプトの該当行を自分で `RENAME TABLE` に直せば実行できます。
- 修正版は 6.1.0-RC1 に入っています。6.0.x へバックポート済みかは未確認です。公式スクリプトをそのまま使う場合は、バックポート状況を確認してください。

修正内容は、次の1行の置き換えです。

```sql
-- 修正前
RENAME SEQUENCE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ;
-- 修正後
RENAME TABLE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ;
```

再現手順:

1. 5.2 のスキーマで MariaDB を初期化する。
2. 上記のマイグレーションスクリプトを実行する。
3. 構文エラーで中断することを確認する。

報告者による[再現プロジェクト](https://github.com/ahrytsiuk/spring-batch-issue-5586)もあります。

## 原因

スクリプトが、MariaDB にない `RENAME SEQUENCE` 文を使っていたためです。次のようなエラーが出ます。同じエラーが出たら、この問題です。

- `java.sql.SQLSyntaxErrorException` ... `near 'SEQUENCE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ'`（`ScriptStatementFailedException: Failed to execute SQL script statement [#1](https://github.com/spring-projects/spring-batch/issues/1)` として報告されています）

## 対応方針

issue 本文では、`RENAME TABLE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ;` を使うことが期待動作とされています。修正コミットは [5e446180ef7b](https://github.com/spring-projects/spring-batch/commit/5e446180ef7b80c673c293bb7953c8303bab20e8) です。

- `spring-batch-core/src/main/resources/org/springframework/batch/core/migration/6.0/migration-mariadb.sql`
  - `RENAME SEQUENCE` を `RENAME TABLE` に置き換えました（あわせてファイル末尾の改行を追加）。
- 再発防止として、5.2 スキーマに対してこのスクリプトを実行するテストが追加されました。CI では動かず、手動実行用です。

## バグの発生タイミング

- **バージョン**: Spring Batch 6.0 の 5.2 → 6.0 用マイグレーションスクリプトです。どのパッチ版かは分かりません。
- **混入コミット**: 特定できません。
- **修正**: [5e446180ef7b](https://github.com/spring-projects/spring-batch/commit/5e446180ef7b80c673c293bb7953c8303bab20e8)（マイルストーン 6.1.0-RC1）。`for: backport-to-6.0.x` ラベルが付いていますが、バックポート済みかは分かりません。
