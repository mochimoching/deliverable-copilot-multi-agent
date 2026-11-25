*（このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました）*

# MongoCursorItemReaderがオープン前にクローズされるとNullPointerExceptionをスローする

**Issue番号**: #5589
**状態**: closed | **作成者**: ryujungkyun | **作成日**: 2026-10-12
**ラベル**: in: infrastructure, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5589

## 内容

### バグの説明

`MongoCursorItemReader`は、`open()`の前に`close()`が呼び出されると、`NullPointerException`を原因とする`ItemStreamException`をスローします。

カーソルは`doOpen()`で初期化されますが、`doClose()`では初期化されているかどうかを確認せずにクローズしようとします。

### 再現手順

1. `MongoCursorItemReader`インスタンスを作成します。
2. 先に`open()`を呼び出さずに`close()`を呼び出します。
3. 例外が発生することを確認します。

### 期待される動作

オープンされていないリーダーに対して`close()`を呼び出しても、クローズすべき初期化済みのカーソルが存在しないため、例外をスローすべきではありません。

### 実際の動作

`this.cursor`が null であるため、`NullPointerException`を原因とする`ItemStreamException`がスローされます。

### 補足情報

`JpaCursorItemReader`と`JpaPagingItemReader`は、`doClose()`の際に未初期化のリソースをすでに適切に処理しています。
