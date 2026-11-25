# Issue #5520 要約: `FlatFileItemReaderBuilder` で `comments(...)` の後に `addComment()` を呼ぶと例外になる問題

## 概要
`FlatFileItemReaderBuilder` で `comments(String...)` を呼んだあとに `addComment(String)` を呼ぶと `UnsupportedOperationException` が発生するバグです。コミット `523eeda0e0af` で、`comments(...)` が保持するリストを可変にする1行の修正が行われました。Issue のステータスは closed、マイルストーンは 6.1.0-RC1、ラベルは `in: infrastructure` / `type: bug` / `for: backport-to-6.0.x` ですが、リリースへの反映やバックポートの状況は入力からは未確認です。

## 問題
`comments(String...)` は `Arrays.asList(comments)` の戻り値をそのままフィールドに保存していました。`Arrays.asList` が返すのは固定長リストで、要素の追加ができません。そのため、次のような呼び出しでは `addComment("+")` 内部の `List.add` が `AbstractList.add` で `UnsupportedOperationException` を投げます。

```java
new FlatFileItemReaderBuilder<Foo>().name("fooReader")
    .resource(resource)
    .comments("@")
    .addComment("+")
```

両メソッドは「コメント行を示す文字列のリストに追加する」と説明されており、組み合わせて使える想定ですが、実際には呼び出し順によって例外になっていました。Issue には、`main`(6.0.x、`cb69762`)で確認され、5.x にも存在すると書かれています。

## 修正内容
対象は `spring-batch-infrastructure` の `FlatFileItemReaderBuilder` の `comments(String...)` です。

```java
this.comments = new ArrayList<>(Arrays.asList(comments));
```

`ArrayList` で包んで可変リストを保持するようにし、後続の `addComment(String)` が追加できるようになりました(コミット `523eeda0e0af`)。メソッドシグネチャの変更はありません。

テストは `FlatFileItemReaderBuilderTests` に `testAddCommentAfterComments` を追加しており、`@` と `+` の両方で始まるコメント行がスキップされることを検証します。

## 利用者への影響・対応
`.comments(...)` の後に `.addComment(...)` を連結しているコードは、この修正で例外が出なくなります。API の変更はないため、既存コードの書き換えは不要です。5.x にも同じ問題が存在すると Issue に書かれていますが、5.x に修正が提供されるかどうかは不明です。5.x 利用者は、自分のバージョンに修正が入っているかを別途確認してください。バージョンアップ時は、該当の呼び出し順を使っている箇所がないか確認すると安心です。

## 補足
- 入力からは、`comments(...)` を `addComment(...)` の後に呼んだ場合の挙動、および `comments(...)` に渡した配列を後で変更した場合の挙動は不明です。
- 5.x へのバックポートの有無は入力に記載がありません(ラベルは `for: backport-to-6.0.x` のみ)。
- 6.1.0-RC1 などのリリースに修正が含まれたかどうかは入力に記載がありません。
- 以前の呼び出し順に対する回避策の有無は入力に記載がありません。
- 実際の PR 番号は入力に記載がありません。
