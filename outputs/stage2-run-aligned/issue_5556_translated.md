*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# ドキュメントの付録にある JpaItemWriter の説明が誤っている

**Issue番号**: #5556
**状態**: closed | **作成者**: marschall | **作成日**: 2026-09-25
**ラベル**: in: documentation, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5556

## 内容

リファレンスドキュメントの[付録](https://docs.spring.io/spring-batch/reference/appendix.html)には、`JpaItemWriter`について次のように記載されています。

> This item writer is JPA `EntityManager`-aware and handles some transaction-related work that a non-“JPA-aware” `ItemWriter` would not need to know about and then delegates to another writer to do the actual writing.

これについて、次の問題があります。
- トランザクションに関連することで実際に行っているのは、トランザクショナルな`EntityManager`を取得することだけです
- 実際には別のライターに委譲しておらず、`EntityManager#persist`または`EntityManager#merge`のいずれかを呼び出しています


## コメント

### コメント 1 by Akhil-1527 (2026-09-26)

こんにちは。喜んで修正します。付録の`JpaItemWriter`の行を、このライターの実際の動作に合わせて書き直したいと考えています。具体的には、トランザクショナルな`EntityManager`を取得し、`EntityManager`がまだ管理していない各アイテムに対して`persist`または`merge`を呼び出し、各チャンクの終了時にフラッシュする、という内容です。別のライターに委譲するという部分は削除します。問題なければ、PRを作成します。


### コメント 2 by marschall (2026-09-26)

良さそうです。各チャンクの後に`EntityManager`の`clear`をオプションで呼び出すことも追記できると思います。
