# ジョブの起動に失敗すると、孤立した JobInstance が残る

**Issue番号**: #5562
**状態**: closed | **作成者**: zhujianxintian | **作成日**: 2026-09-28
**ラベル**: type: bug, in: core, status: for-internal-team
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5562

## 内容

**バグの説明**
パラメータとして `java.time.Year` を渡すと、次の例外が発生します: `org.springframework.core.convert.ConverterNotFoundException: No converter found capable of converting from type [java.time.Year] to type [java.lang.String]`

しかし、この `JobInstance` のデータはそれでもデータベースに永続化されています。これは正常な動作でしょうか？意図的な設計でしょうか、それともバグでしょうか？

意図的な設計であるなら、なぜそうなっているのでしょうか？

**`java.time.Year` に対応するコンバーターが見つからないこと自体がバグだと言っているのではない、という点にご注意ください。私が言いたいのは、業務シナリオに合致しない例外（コーディング時に設定が適切に行われていなかったためだけに発生する例外）が起きたときに、データの一部が永続化されたままになるということです。**

**環境**
Spring Boot 4.1.1
Spring Batch 6.0.5
Java 25
H2 database

**再現手順**
私が提供したデモを起動してください。バッチジョブが自動的に1回実行されます。その後、ログに出力されるメッセージに従って H2 database のデータを確認できます。

**期待される動作**
バグであるなら、トランザクションで解決できませんか？あるいは、あるステップが失敗した後に、それ以前に完了していた永続化を自動的に削除するべきではないでしょうか？
Job の起動中に予期しない例外が発生した場合、余分な不完全データが生成されないことを望みます。

**最小限の完全な再現例**
このデモを開き、H2 database のページにアクセスして、`JobInstance` のデータが存在するかどうかを確認できます。

[spring-batch-demo.zip](https://github.com/user-attachments/files/32757193/spring-batch-demo.zip)

## コメント

### コメント 1 by fmbenhassine (2026-10-02)

この issue をご報告いただきありがとうございます！これは意図された動作ではありません。5.x と比べた 6.0 でのリグレッションです。

5.x では、ジョブの起動時にまずジョブパラメータを検証し、その後 `JobInstance`、`JobExecution` とそのパラメータを単一のトランザクションで作成していました。何かが失敗した場合、何も永続化されませんでした。6.0 では、ランチャーが `JobInstance` を独自のトランザクションで作成し（これは即座にコミットされます）、その後でパラメータを検証し、`JobExecution` とそのパラメータを2つ目のトランザクションで作成します。最初のコミットの後に失敗が起きると、`JobInstance` は実行を伴わないままリポジトリに残ります。

またこれは変換エラーに限りません。パラメータの検証エラーや永続化エラーでも同じ問題が発生します。残った `JobInstance` は、同じパラメータでの再起動（`IllegalStateException: Cannot find any job execution for job instance`）や、incrementer を持つジョブの `startNextInstance` を妨げます。

次のリリースで修正を計画します。
