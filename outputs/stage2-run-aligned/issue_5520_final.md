*このドキュメントは生成AI(GitHub Copilot / Claude Sonnet 5.5)によって2026年11月18日に生成されました。*

## 課題概要

[#5520](https://github.com/spring-projects/spring-batch/issues/5520) は、`FlatFileItemReaderBuilder` で `comments(String...)` を呼んだ後に `addComment(String)` を呼ぶと `UnsupportedOperationException` が発生するバグです。

`FlatFileItemReader` は、指定した接頭辞で始まる行をコメント行として読み飛ばします。その接頭辞を、ビルダーは `comments(...)`（一括指定）または `addComment(...)`（1件ずつ追加）で受け取ります。

失敗するのは `comments("@").addComment("+")` の組み合わせだけです。どちらか一方のみの場合は動作します。修正後は `@` と `+` の両方がコメント接頭辞になります。

影響として、この組み合わせを使っているジョブは、Reader の設定コードの実行時に例外で失敗します。自分のコードで `comments(...)` の後に `addComment(...)` を呼んでいないか検索して確認してください。回避策は、接頭辞を `comments(...)` だけにまとめて指定することです。

## 原因

`comments(String...)` が `Arrays.asList` の戻り値（要素を追加できない固定サイズのリスト）をそのまま保持していました。`addComment` はそのリストに要素を追加するため、例外になります。

## 対応方針

`comments(...)` が変更可能なリストを保持するように直します（`Arrays.asList(comments)` を `new ArrayList<>(Arrays.asList(comments))` に変更。[コミット 523eeda0e0af](https://github.com/spring-projects/spring-batch/commit/523eeda0e0af566ca2c1dd58d5a9847cf7b4e1e1)、2026-09-30）。利用側のコード変更は不要で、アップグレードすれば `addComment` が使えます。

`FlatFileItemReaderBuilderTests` に `testAddCommentAfterComments` を追加し、`comments("@").addComment("+")` で `@` と `+` で始まる行が読み飛ばされ、`1,2,3` と `4,5,6` の2件だけが読まれることを確認しています。

issue には `for: backport-to-6.0.x` ラベルがありますが、入力の diff には main 側のコミットしか含まれず、backport の有無は分かりません。

## バグの発生タイミング

- **確認バージョン**: `main`（`cb69762`、6.0.x 系）。5.x にも存在すると報告されていますが、具体的なバージョンと混入コミットは不明です。
- **参考（修正コミット）**: [523eeda0e0af](https://github.com/spring-projects/spring-batch/commit/523eeda0e0af566ca2c1dd58d5a9847cf7b4e1e1)（マイルストーン: 6.1.0-RC1）
