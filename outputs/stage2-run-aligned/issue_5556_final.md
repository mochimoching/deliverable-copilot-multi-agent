*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

リファレンスドキュメントの[付録](https://docs.spring.io/spring-batch/reference/appendix.html)にある `JpaItemWriter` の説明が、実際の動作と合っていないという課題です（[#5556](https://github.com/spring-projects/spring-batch/issues/5556)）。付録は「別のライターに委譲する」と説明していましたが、実際は委譲せず `EntityManager#persist` / `merge` を直接呼びます。ドキュメントのみの問題で、コードの挙動は変わりません。

業務上の影響は次の2点です。

- 付録を信じて、委譲先のライターを探したり、カスタマイズ点として期待したりする必要はありません。
- 既定では `merge` が呼ばれ、チャンクごとにフラッシュされます。大量データ処理でのメモリ消費や SQL 発行のタイミングを考える際は、この動作を前提にしてください。ただし `clear` の既定値は入力に記載がなく、未確認です。

**補足**:

- 永続コンテキスト: `EntityManager` が管理するエンティティの集合です。
- `persist`: 新規エンティティ専用で、永続コンテキストに登録します。新規データのみを書き込む場合は `usePersist` の利用が候補になります。
- `merge`: 渡したエンティティの状態を、管理下のコピーに反映します。既存行の場合は事前に SELECT が走ることがあります（実装での挙動は入力から確認できていません）。

## 原因

付録の説明文が `JpaItemWriter` の実際の動作と一致していなかったためです。いつ・なぜ乖離したかについては、入力に記載がありません。

## 対応方針

### issue での議論

Akhil-1527 が、委譲の記述を削除して実際の動作に書き換える案を出しました。marschall は、各チャンクの後に `EntityManager` の `clear` をオプションで呼ぶ旨の追記も提案しています。

### 修正内容（[commit 0565ed4e64ed](https://github.com/spring-projects/spring-batch/commit/0565ed4e64eda24cb0c21778c1ddec008f0c32fe)）

変更は `spring-batch-docs/modules/ROOT/pages/appendix.adoc` の `JpaItemWriter` の行の差し替えのみです。

- 修正前: JPA `EntityManager` を意識し、「トランザクション関連の作業」を行い、別のライターに委譲して実際の書き込みを行う
- 修正後:
  1. トランザクションが有効な `EntityManager` を取得する。
  2. 永続コンテキストにまだ含まれていないアイテムに `merge` を呼ぶ（`usePersist` が設定されていれば `persist`）。
  3. 各チャンクの終了時にフラッシュし、`clearPersistenceContext` が `false` でない限り `clear` する。

### issue と diff の齟齬

- `persist` または `merge`: issue では二択としか述べていませんが、diff では `merge` を基本とし、`usePersist` 設定時に `persist` を呼ぶと具体化されています。矛盾ではなく詳細化です。
- `clear`: diff の文面は「`false` でない限り `clear`」なので、`clearPersistenceContext` が `false` に設定されない限り `clear` が行われます。コメントの「オプション」とは異なります。既定値は入力に記載がなく未確認です。
- フラッシュ、委譲記述の削除: issue と diff で一致しています。

## バグの発生タイミング

- バージョン・コミットとも入力からは特定できません。
- 修正は [commit 0565ed4e64ed](https://github.com/spring-projects/spring-batch/commit/0565ed4e64eda24cb0c21778c1ddec008f0c32fe) で行われ、6.1.0-RC1 で反映されます。`for: backport-to-6.0.x` ラベルがあり、6.0.x へもバックポートされる予定です。
