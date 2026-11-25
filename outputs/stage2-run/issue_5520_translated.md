# `FlatFileItemReaderBuilder.addComment()` が `comments(...)` の後に `UnsupportedOperationException` をスローする

**Issue番号**: #5520
**状態**: closed | **作成者**: hunseonglee | **作成日**: 2026-09-03
**ラベル**: in: infrastructure, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5520

## 内容

**バグの説明**
`FlatFileItemReaderBuilder.comments(String...)` は、`Arrays.asList` が返す固定サイズのリストを保持します。

```java
public FlatFileItemReaderBuilder<T> comments(String... comments) {
    this.comments = Arrays.asList(comments);
    return this;
}
```

その後に `addComment(String)` を呼び出すと、そのリストに対して `List.add` が呼ばれ、`UnsupportedOperationException` がスローされます。しかし、両メソッドは組み合わせて使えるとドキュメントに記載されています（"Add a string to the list of Strings that indicate commented lines"）。

**環境**
Spring Batch `main` の `cb69762`（6.0.x）。5.x にも存在します。JDK 21。

**再現手順**
```java
new FlatFileItemReaderBuilder<Foo>().name("fooReader")
    .resource(resource)
    .comments("@")
    .addComment("+")   // UnsupportedOperationException at AbstractList.add
    ...
```

**期待される動作**
`comments(...)` は（フィールドのデフォルト初期化と同様に）変更可能なリストを保持し、その後で `addComment(...)` を使用できるようにします。修正とテストを含む PR を提出する予定です。
