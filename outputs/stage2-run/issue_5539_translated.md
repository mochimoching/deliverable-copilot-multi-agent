# 未オープンの JpaPagingItemReader をクローズすると NullPointerException が発生する

**Issue番号**: #5539
**状態**: closed | **作成者**: COBI-98 | **作成日**: 2026-09-16
**ラベル**: in: infrastructure, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5539

## 内容

﻿**バグの説明**
一度もオープンされていない JpaPagingItemReader をクローズすると、NullPointerException を原因とする ItemStreamException がスローされます。その EntityManager は doOpen() でのみ代入されますが、doClose() は entityManager.close() を無条件に呼び出しています。

これは、インスタンス化されたシングルトンの reader bean が推論された close の destroy メソッドを持ち、かつその step が実行されていない場合に、アプリケーションコンテキストのシャットダウン時に発生し得ます。

**環境**
Spring Batch main の a3028e3c8f78c0e385cb61fb800afb32b5f7846a。このクリーンアップ失敗の再現にデータベースは不要です。

**再現手順 / 最小限の完全な再現例**
次の JUnit 5 テストは、factory に Mockito を使用しています：

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

close の呼び出しは `ItemStreamException: Error while closing item reader` をスローします。原因は JpaPagingItemReader.doClose() 内の `NullPointerException: Cannot invoke "jakarta.persistence.EntityManager.close()" because "this.entityManager" is null` です。

**期待される動作**
EntityManager が作成されていない場合、close は EntityManager のクリーンアップをスキップしつつ、スーパークラスのクリーンアップは引き続き実行すべきです。

`JpaCursorItemReader` に関連するシャットダウン時のケースは #5486 / #5489 で対処されました。paging reader のガードされていない close は JSpecify への移行より前から存在しています。このレポートはこれを当該移行に起因するものとはしていません。


## コメント

### コメント 1 by hunseonglee (2026-09-16)

これを再現できたので、取り組みたいと思います。修正は `JpaCursorItemReader` に対して #5486 / #5489 で行われたものと同様で、`doClose()` 内の `EntityManager` のクリーンアップを null チェックでガードしつつ、スーパークラスのクリーンアップは維持します。回帰テストを含む PR をまもなく提出します。
