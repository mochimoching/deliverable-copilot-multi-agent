*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# 未オープンの JpaPagingItemReader をクローズする際の NullPointerException

**Issue番号**: #5539
**状態**: closed | **作成者**: COBI-98 | **作成日**: 2026-09-16
**ラベル**: in: infrastructure, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5539

## 内容

﻿**バグの説明**
一度もオープンされていない `JpaPagingItemReader` をクローズすると、`NullPointerException` を原因とする `ItemStreamException` がスローされます。`EntityManager` は `doOpen()` でのみ代入されますが、`doClose()` は無条件に `entityManager.close()` を呼び出しています。

これは、インスタンス化されたシングルトンのリーダー Bean に推論された close の destroy メソッドがあり、そのステップが実行されていない場合に、アプリケーションコンテキストのシャットダウン時に発生する可能性があります。

**環境**
Spring Batch main の a3028e3c8f78c0e385cb61fb800afb32b5f7846a。このクリーンアップの失敗を再現するのにデータベースは不要です。

**再現手順 / 最小限の完全な再現例**
次の JUnit 5 テストは、ファクトリに Mockito を使用しています:

```java
import jakarta.persistence.EntityManagerFactory;
import org.junit.jupiter.api.Test;
import org.springframework.batch.infrastructure.item.database.JpaPagingItemReader;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.mockito.Mockito.mock;

class JpaPagingItemReaderCloseTests {
    @Test
    void closeWithoutOpen() throws Exception {
        EntityManagerFactory factory = mock(EntityManagerFactory.class);
        JpaPagingItemReader<Object> reader = new JpaPagingItemReader<>(factory);
        reader.setQueryString("select o from Object o");
        reader.afterPropertiesSet();
        assertDoesNotThrow(reader::close);
    }
}
```

`close` の呼び出しは `ItemStreamException: Error while closing item reader` をスローします。原因は、`JpaPagingItemReader.doClose()` 内の `NullPointerException: Cannot invoke "jakarta.persistence.EntityManager.close()" because "this.entityManager" is null` です。

**期待される動作**
`EntityManager` が作成されていない場合は `EntityManager` のクリーンアップをスキップし、スーパークラスのクリーンアップは引き続き実行する必要があります。

`JpaCursorItemReader` に関連するシャットダウン時のケースは [#5486](https://github.com/spring-projects/spring-batch/issues/5486) / [#5489](https://github.com/spring-projects/spring-batch/issues/5489) で対処されました。ページングリーダーにおけるこのガードのない close は JSpecify への移行以前から存在しており、本報告はこれを当該移行によるものとはしていません。


## コメント

### コメント 1 by hunseonglee (2026-09-16)

再現を確認できましたので、この課題に取り組みたいと思います。修正は `JpaCursorItemReader` に対して [#5486](https://github.com/spring-projects/spring-batch/issues/5486) / [#5489](https://github.com/spring-projects/spring-batch/issues/5489) で行われた内容と同様で、`doClose()` 内の `EntityManager` のクリーンアップを null チェックでガードしつつ、スーパークラスのクリーンアップは維持します。回帰テストを含む PR をまもなく提出します。
