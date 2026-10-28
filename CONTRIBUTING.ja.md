# LocArc へのコントリビュート

[English version is here](CONTRIBUTING.md)

コントリビュートに興味を持っていただきありがとうございます。このガイドでは開発環境のセットアップ、
プロジェクトの規約、レビューの流れを説明します。

> **セキュリティ問題:** 公開Issueには書かないでください。[SECURITY.md](SECURITY.md) を参照してください。

## コントリビュートの種類

- バグ報告 — Issueフォームを使い、ログと環境情報を添えてください。
- 機能リクエスト・UXへのフィードバック。
- プルリクエスト: バグ修正、機能追加、ドキュメント、翻訳。
- さまざまなハードウェア（CPU / GPU / NPU）やOSでの動作確認。

## 開発環境のセットアップ

必要なもの: Python 3.12 以上、Git、Windows 10/11 または Ubuntu 24.04。

```bash
git clone https://github.com/Asahi-Prv/locarc.git
cd locarc
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m app.main        # Windowsは run.bat、Linuxは ./run.sh でも可
```

アプリのデータは `./data` に保存されます（環境変数 `LOCARC_DATA` で変更可能）。テストは一時
ディレクトリを使うため、実際のデータには触れません。

## push前のチェック

```bash
ruff check .
pytest -q
python -m compileall -q app tests locarc.py
```

CIでも同じチェックが全プルリクエストに対してWindowsとLinuxの両方で実行され、タグでは
Windows / Linux 実行ファイルのビルドも行われます。

## コーディング規約

- Python 3.12 を対象とし、モジュール先頭に `from __future__ import annotations` を付けます。
- 公開ヘルパーには型ヒントを付け、関数は小さく保ちます。
- コメントとdocstringは英語で書きます。
- `app.js` やバックエンドのハンドラにユーザー向け文字列を直書きせず、i18nを経由します。
- 標準ライブラリと `requirements.txt` にある依存関係を優先します。
- ローカル優先の方針を維持し、新機能が既定で待受ポートを開かないようにします。

## ローカライズ (i18n)

ユーザー向け文字列は2つのカタログにあります:

| ファイル | 対象 | 例 |
| --- | --- | --- |
| `app/static/i18n.js` | UIラベル・ボタン・トースト・動的文言 | `t("models.download")` |
| `app/i18n.py` | APIエラー・タスク進捗メッセージ | `tr(lang, "err.not_found")` |

ルール:

- 新しいキーは `en` と `ja` の**両方**に追加します。不足時は英語にフォールバックします。
- HTMLでは `data-i18n` / `data-i18n-html` / `data-i18n-placeholder` / `data-i18n-title` を使います。
- マークアップを含む翻訳は `data-i18n-html` を使います（値は信頼済みの定数のみ）。
- 埋め込みは `{name}` プレースホルダ形式です: `t("search.results", { n: 10 })`。

## テスト

- バックエンドのテストは `tests/test_api.py` にあり、`pytest -q` で実行します。
- テストからネットワークを呼ばないでください。検索エンドポイントのテストのようにモジュール関数を
  モンキーパッチします。
- UI変更は日英両方（サイドバーの `#btnLang`）と狭いウィンドウ幅で確認してください。
- 手動スモークテスト: ランタイム導入 → モデルDL → ロード → チャット。

## プルリクエスト

1. リポジトリをフォークし、`fix/...` `feat/...` `docs/...` `i18n/...` のようなブランチを作成します。
2. レビューしやすいよう、1つのPRには1つの論理的な変更にまとめます。
3. PRテンプレートを埋め、関連Issueをリンクし、テスト方法を書きます。
4. CIがグリーンであることを確認します。マージ前にメンテナが修正を依頼することがあります。

## コミットメッセージ

- 命令形で簡潔に: `fix: reject path traversal in model delete`
- 任意のプレフィックス: `feat:` `fix:` `docs:` `refactor:` `test:` `build:` `chore:`
- 差分から自明でない場合は本文に「なぜ」を書きます。

## Issueのガイドライン

- 既存Issueを検索してから、バグ報告または機能リクエストのフォームを使ってください。
- バグ報告にはアプリのバージョン/コミット、OS、実行方法、OVMSランタイムのバージョン、モデル、
  デバイス、マスク済みのログ（**設定 → ログ**）を含めてください。
- OVMS本体の問題は上流へ:
  <https://github.com/openvinotoolkit/model_server/issues>

## リリース手順（メンテナ向け）

1. `main` のCIがグリーンであることを確認します。
2. `CHANGELOG.md` を更新し、該当する `[Unreleased]` の項目を新しいバージョンのセクションへ
   移します。
3. `app/version.py` を更新します（リリースビルドではタグから上書きされます）。
4. タグを作成してpushします:

   ```bash
   git tag v1.2.3
   git push origin v1.2.3
   ```

*Build apps* ワークフローが以下を自動実行します:

- タグのバージョンを `app/version.py` に反映
- Windows / Linux 実行ファイルのビルドと各スモークテスト
- Windowsポータブルzip・Inno Setupインストーラー・Linux tarballの作成と、統合 `SHA256SUMS.txt`
  の生成（旧 `Intel-AI-Studio-*` 名の互換アセットも同梱）
- Conventional Commitsから分類済みリリースノートを生成（`scripts/release_notes.py`）
- 全ファイルを添付してGitHubリリースを公開

ノートはコミットタイプ（`feat:` `fix:` など）で分類されるため、コミットメッセージは
Conventional Commits形式を維持してください。

## ライセンス

コントリビュートすると、あなたの貢献が [MIT License](LICENSE) の下でライセンスされることに
同意したものとみなされます。
