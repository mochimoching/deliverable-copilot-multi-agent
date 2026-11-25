# Issue #5586 要約: MariaDB 向け 6.0 移行スクリプトが `BATCH_JOB_SEQ` のリネームで失敗する問題
## 概要
Spring Batch 5.2 から 6.0 へ移行するための MariaDB 用スクリプト `migration-mariadb.sql` が、MariaDB で構文エラーになる不具合です。原因は MariaDB が受け付けない `RENAME SEQUENCE` 文を使っていたことで、該当の 1 文を `RENAME TABLE` に置き換えて修正されました。あわせて、移行スクリプトを検証する統合テストと 5.2 スキーマが追加されています。

## 問題
`spring-batch-core/src/main/resources/org/springframework/batch/core/migration/6.0/migration-mariadb.sql` は次の 1 文だけで構成されていました。

```sql
RENAME SEQUENCE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ;
```

issue の報告によると、5.2 スキーマを作成した MariaDB でこのスクリプトを実行すると、statement #1 で `ScriptStatementFailedException`（原因は `SQLSyntaxErrorException`）が発生し、`BATCH_JOB_SEQ` のリネームに到達する前に失敗します（issue に記載されたスタックトレースに基づく）。issue は、MariaDB ではシーケンスのリネームに `RENAME TABLE` が必要だと述べています。この根拠は issue が引用する MariaDB ドキュメントの記述のみです。なお、修正後の動作は CI で自動検証されていません（下記のテストは `@Disabled`）。

## 修正内容
コミット 5e446180ef7b による変更です。

- `migration-mariadb.sql`: 該当文を次のように変更しました（ファイル末尾に改行も追加）。
  ```sql
  RENAME TABLE BATCH_JOB_SEQ TO BATCH_JOB_INSTANCE_SEQ;
  ```
- MariaDB 11.8.2 で移行スクリプトを検証するオンデマンドの統合テストと、その前提となる 5.2 スキーマを追加しました。

このテストは `@Disabled`（「CI ビルドの対象外で、移行スクリプトの検証が必要なときにオンデマンドで使う」旨）になっており、CI では実行されません。

## 利用者への影響・対応
- MariaDB で 5.2 から 6.0 へ移行する利用者が対象です。旧スクリプトでは移行が最初の文で失敗するため、修正後のスクリプトを使う必要があります。
- 旧スクリプトで一度失敗した環境の状態（部分適用の有無）は入力からは分かりません。ただしスクリプトは 1 文のみで、失敗はその文で起きています。
- 修正が含まれるパッチバージョンは入力からは分かりません。

## 補足
- ラベル: `type: bug`、`in: core`、`related-to: ddl-scripts`、`for: backport-to-6.0.x`。マイルストーンは 6.1.0-RC1、状態は closed です。バックポートが実際に行われたかは入力に記載がありません。
- 他のデータベース用スクリプトへの影響は入力からは分かりません。
- 環境について: issue の報告内容（上記スタックトレース）と、追加テストの設定（`mariadb:11.8.2` のコンテナを使用）は別の情報源です。他バージョンでの挙動は不明です。
- 実行後に `BATCH_JOB_INSTANCE_SEQ` が存在し `BATCH_JOB_SEQ` が無くなっていることを確認する、という案は推測に基づくもので、issue や diff に記載された手順ではありません。
