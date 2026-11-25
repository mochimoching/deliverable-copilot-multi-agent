# ドキュメントの付録にある JpaItemWriter の説明が誤っている

**Issue番号**: #5556
**状態**: closed | **作成者**: marschall | **作成日**: 2026-09-25
**ラベル**: in: documentation, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5556

## 内容

リファレンスドキュメントの[付録](https://docs.spring.io/spring-batch/reference/appendix.html)には、`JpaItemWriter` について次のように書かれています。

> This item writer is JPA `EntityManager`-aware and handles some transaction-related work that a non-“JPA-aware” `ItemWriter` would not need to know about and then delegates to another writer to do the actual writing.

（訳: この item writer は JPA の `EntityManager` を認識しており、「JPA 非対応」の `ItemWriter` であれば知る必要のないトランザクション関連の処理を行い、その後、実際の書き込みを別の writer に委譲します。）

これには次の問題があると考えています。
- 実際にトランザクションに関係することは、トランザクショナルな `EntityManager` を取得することくらいです
- 実際には別の writer に委譲しておらず、`EntityManager#persist` または `EntityManager#merge` を呼び出しています


## コメント

### コメント 1 by Akhil-1527 (2026-09-26)

こんにちは。喜んで修正します。付録の `JpaItemWriter` の行を、この writer が実際に行うことに合わせて書き直そうと思います。具体的には、トランザクショナルな `EntityManager` を取得し、`EntityManager` がまだ管理していない各 item に対して `persist` または `merge` を呼び出し、各チャンクの最後に flush する、という内容です。別の writer に委譲するという部分は削除します。これでよければ、PR を作成します。


### コメント 2 by marschall (2026-09-26)

おおむね良さそうです。各チャンクの後に `EntityManager` の `clear` をオプションで呼び出すことも追記してよいと思います。
