# MultiResourceItemWriter が 0 以下の itemCountLimitPerResource 値を検証しない

**Issue番号**: #5597
**状態**: closed | **作成者**: ryujungkyun | **作成日**: 2026-10-14
**ラベル**: in: infrastructure, type: bug, for: backport-to-6.0.x
**マイルストーン**: 6.1.0-RC1
**URL**: https://github.com/spring-projects/spring-batch/issues/5597

## 内容

### バグの説明

`MultiResourceItemWriter` は `itemCountLimitPerResource` に 0 や負の値を受け付けますが、これらの値は書き込み中に失敗を引き起こします。

上限が 0 で、チャンクが空でない場合、`write()` は空のチャンクを繰り返し delegate に渡し、アイテムを一切処理しないまま次のリソースへ進みます。このループは正常に完了できません。

負の上限の場合は、書き込み中に不正な sublist の範囲が発生します。

### 再現手順

1. delegate と出力リソースを指定して `MultiResourceItemWriter` を構成します。
2. `itemCountLimitPerResource` を `0` に設定します。
3. writer を open します。
4. 空でないチャンクを書き込みます。

writer は空のチャンクの書き込みを繰り返し試み、進捗のないままリソースを切り替え続けます。

代わりに上限を `-1` に設定すると、書き込み中に不正な sublist の範囲が発生します。

### 期待される動作

0 以下の上限は、書き込みが始まる前の設定時に `IllegalArgumentException` で拒否されるべきです。

これは、`setItemCountLimitPerResource` による直接の設定と、`MultiResourceItemWriterBuilder.build()` による構築の両方に適用されるべきです。

### 実際の動作

どちらの設定経路も、`0` や負の値を例外をスローせずに受け付けます。不正な設定は書き込みが始まって初めて表面化します。

### 補足情報

上限が 0 で、チャンクに 1 件のアイテムが含まれる場合、書き込むアイテム数は次のように計算されます:

```text
itemsToWrite = min(remaining resource capacity, remaining chunk items)
            = min(0, 1)
            = 0
```

処理済みアイテム数は 0 のままですが、リソースの上限にはすでに達しています(`0 >= 0`)。writer は次のリソースへ進み、同じ計算を繰り返します。

`0` と `-1` に対して `IllegalArgumentException` を期待するパラメータ化テストは、どちらの設定経路でも例外がスローされないため失敗します。これらのテストは検証の欠如を示すものであり、終了しない書き込みループを実行するものではありません。
