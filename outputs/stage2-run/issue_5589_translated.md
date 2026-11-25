# MongoCursorItemReader が open() の前に close() されると NullPointerException をスローする

**Issue番号**: #5589
**状態**: closed | **作成者**: ryujungkyun | **作成日**: 2026-10-12
**ラベル**: in: infrastructure, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5589

## 内容

### Bug description

`close()` が `open()` の前に呼び出されると、`MongoCursorItemReader` は `NullPointerException` を原因とする `ItemStreamException` をスローします。

cursor は `doOpen()` で初期化されますが、`doClose()` は初期化されているかどうかを確認せずにそれを close しようとします。

### Steps to reproduce

1. `MongoCursorItemReader` のインスタンスを作成する。
2. 先に `open()` を呼び出さずに `close()` を呼び出す。
3. 例外を確認する。

### Expected behavior

open されていない reader に対して `close()` を呼び出しても、close すべき初期化済みの cursor が存在しないため、例外をスローしないべきです。

### Actual behavior

`this.cursor` が null であるため、`NullPointerException` を原因とする `ItemStreamException` がスローされます。

### Additional context

`JpaCursorItemReader` と `JpaPagingItemReader` は、`doClose()` の中で未初期化のリソースをすでに適切に扱っています。
