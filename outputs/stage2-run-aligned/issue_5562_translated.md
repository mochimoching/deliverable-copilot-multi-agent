*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# ジョブ起動の失敗により孤立した JobInstance が残る

**Issue番号**: #5562
**状態**: closed | **作成者**: zhujianxintian | **作成日**: 2026-09-28
**ラベル**: type: bug, in: core, status: for-internal-team
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5562

## 内容

**バグの説明**
パラメータとして `java.time.Year` を渡すと、次の例外が発生します: `org.springframework.core.convert.ConverterNotFoundException: No converter found capable of converting from type [java.time.Year] to type [java.lang.String]`

しかし、この `JobInstance` のデータはそれでもデータベースに永続化されています。これは正常なのでしょうか？意図的な設計でしょうか、それともバグでしょうか？

意図的な設計である場合、その理由は何でしょうか？

**`java.time.Year` に対応するコンバーターが見つからないことがバグだと言っているのではない、という点にご注意ください。私が言いたいのは、業務シナリオに合致しない例外（コーディング時に適切に設定されていなかったために発生しただけの例外）が起きた場合でも、データの一部が永続化されてしまうということです。**

**環境**
Spring Boot 4.1.1
Spring Batch 6.0.5
Java 25
H2 database

**再現手順**
提供したデモを起動してください。バッチジョブが自動的に一度実行されます。その後、ログに出力される案内に従って H2 database 内のデータを確認できます。

**期待される動作**
これがバグである場合、トランザクションで解決できないでしょうか？あるいは、いずれかのステップが失敗した後、それ以前に完了した永続化を自動的に削除すべきではないでしょうか？
Job の開始時に予期しない例外が発生した場合、不完全な余分なデータが生成されないことを望みます。

**最小限の完全な再現例**
このデモを開き、H2 database のページにアクセスして、`JobInstance` のデータが存在するかどうかを確認できます。

[spring-batch-demo.zip](https://github.com/user-attachments/files/32757193/spring-batch-demo.zip)

## コメント

### コメント 1 by fmbenhassine (2026-10-02)

この課題を報告していただきありがとうございます！これは意図された動作ではありません。5.x と比較した 6.0 でのリグレッションです。

5.x では、ジョブを起動する際にまず Job パラメータを検証し、その後 `JobInstance`、`JobExecution` とそのパラメータを単一のトランザクションで作成していました。何かが失敗した場合、何も永続化されませんでした。6.0 では、ランチャーが `JobInstance` を独自のトランザクション（すぐにコミットされる）で作成し、その後にようやくパラメータを検証して、2 つ目のトランザクションで `JobExecution` とそのパラメータを作成します。最初のコミットの後に失敗が発生すると、`JobInstance` は実行を伴わないままリポジトリに残ります。

また、これは変換エラーに限った話ではなく、パラメータの検証エラーや永続化エラーでも同じ問題が発生します。残された `JobInstance` は、同じパラメータでの再起動（`IllegalStateException: Cannot find any job execution for job instance`）や、incrementer を持つジョブの `startNextInstance` を妨げます。

次のリリースで修正を計画します。
