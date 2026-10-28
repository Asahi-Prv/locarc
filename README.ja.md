# LocArc

[English README is here](README.md)

> [!IMPORTANT]
> 本プロジェクトは個人が開発した非公式のコミュニティプロジェクトです。**Intel Corporation
> との提携・承認・スポンサー関係はありません**。「Intel」「OpenVINO」は Intel Corporation の
> 商標であり、本プロジェクトでは互換性の説明のためにのみ使用しています。Intel の公式製品では
> ありません。

**LocArc** は、[OpenVINO Model Server (OVMS)](https://github.com/openvinotoolkit/model_server) を
ネイティブウィンドウ（WebView2）で管理するローカル優先のデスクトップアプリです。ランタイムの
導入からモデルのダウンロード、ロード、チャットまでを一通り操作できます。

> [!NOTE]
> **LocArc** は旧称 **Intel AI Studio** です。既存の `data` フォルダはそのまま利用できます
> （[Intel AI Studio からの移行](#intel-ai-studio-からの移行)）。

- **OVMSランタイムのインストール** — Stable（GitHubリリース）/ Weekly、`python_on` 版のみ。
  可能な場合は SHA-256 を検証。
- **モデルのダウンロード** — Hugging Face（トークン使用のゲート付きモデル対応）または任意の
  直リンク（zip/tar は自動展開）。ダウンロードはタスクパネルからキャンセルできます。
- **モデル検索** — Hugging Face 上の **OpenVINO IR** モデルのみを検索。`openvino` タグと公式
  `OpenVINO` org を優先して検索し（通常の全文検索はPyTorch版が上位を占めるため）、一致する
  `.xml` + `.bin` のペアで検証したうえで、クエリとの関連度 → 公式 → 人気の順にランキング
  します。結果は無限スクロールでページング読み込みされ、ダウンロードでは IR 以外の重み
  （PyTorch / ONNX 等）を除外して容量を節約できます。リポジトリ名/タグから量子化を判定して
  CW（channel-wise）版にはバッジを表示します。ロード時に NPU を選ぶと CW 推奨のヒント
  （非CWモデルの場合は警告）を表示します。
- **モデルのロード / アンロード** — デバイス選択（CPU/GPU/NPU/AUTO）、サーブモード自動判定、
  KVキャッシュ容量・精度（u8）・コンテキスト長・prefixキャッシュなどのLLMロード設定。
- **チャット** — ストリーミング応答、Markdownレンダリング、思考（reasoning）表示、タイトル
  自動生成、チャットごとの生成パラメータ、履歴の保存。
- **画像生成** — `image_generation` モデルに対応。
- **API提供** — OVMS自身がOpenAI互換REST / gRPCを提供。外部クライアント向けの Bearer
  APIキーもUIから設定可能。
- **アップデート** — パッケージ版は起動時にGitHub Releasesを確認（1日1回まで）。ワンクリックで
  ダウンロード→SHA-256検証→自動で入れ替え・再起動（モデルやチャットは保持）。
- **日英UI** — 実行中にワンクリックで切り替え。

## インストール

各リリースには Windows / Linux 版があります。それぞれがPythonランタイムを同梱し、データ
（ランタイム・モデル・チャット・設定）は実行ファイルと同じフォルダの `data` に保存されます。

### Windows

| ビルド | ダウンロード | 動作 |
| --- | --- | --- |
| **インストーラー版**（推奨） | `LocArc-Setup-x64.exe` | ユーザー単位でインストール（管理者権限不要）。スタートメニューとデスクトップ（任意）にショートカットを作成し、ネイティブウィンドウ（WebView2）で起動します |
| **ポータブル版** | `LocArc-windows-x64.zip` | 任意の場所に展開して `LocArc.exe` を実行。ネイティブウィンドウ（WebView2）で起動します（インストール不要） |

どちらも同じexeを使い、インストーラーはショートカットとアンインストーラーを追加するだけです。
署名がないためWindowsのSmartScreen警告が出る場合があります（*詳細情報 → 実行*）。

### Linux（Ubuntu 24.04）

`LocArc-linux-x64.tar.gz` をダウンロードします。ポータブルフォルダに加えて、
ユーザー単位のインストーラーも同梱されています:

```bash
tar -xzf LocArc-linux-x64.tar.gz
cd LocArc
./install.sh          # ランチャーとアプリメニュー登録（管理者権限不要）
./LocArc          # インストールせず直接実行することもできます
```

`install.sh` はアプリを `~/.local/share/locarc` へコピーし、`~/.local/bin` に
`locarc` コマンドを、アプリメニューに `.desktop` エントリを登録します。
`./uninstall.sh` は `data` を残してアプリを削除します（`--purge` でデータも削除）。

Linux版はOVMS `python_on` パッケージと同じ Ubuntu 24.04 を対象にしています。ネイティブ
ウィンドウには WebKitGTK を使います:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.1
```

`install.sh` はこれを検出し、無い場合は上記コマンドを案内します。WebKitGTK が無い場合は既定の
ブラウザで開きます（機能は変わりません）。

## 動作要件

- Windows 10/11 (x64) または Ubuntu 24.04（OVMS `python_on` パッケージに準拠）
- Microsoft Edge WebView2 ランタイム（Windows 11 およびほとんどの Windows 10 に同梱）
- Linuxではネイティブウィンドウに WebKitGTK（`python3-gi` / `gir1.2-webkit2-4.1`）を使用（任意。無い場合はブラウザで起動）
- ソースから実行する場合は Python 3.12 以上（配布exeはPython同梱）
- ディスク容量: OVMSランタイム 約1〜2GB + モデルサイズ

## クイックスタート（ソースから）

Windows:

```bat
git clone https://github.com/Asahi-Prv/locarc.git
cd locarc
run.bat
```

Linux:

```bash
git clone https://github.com/Asahi-Prv/locarc.git
cd locarc
./run.sh
```

または手動で:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.main
```

デスクトップウィンドウが自動で開きます（ローカルサーバーは `http://127.0.0.1:8810` で待受け）。

## はじめの手順

1. **ランタイムをインストール** — 「初期セットアップ」カードの「おすすめ（最新Stable）を
   インストール」、または「設定」タブで Stable / Weekly を選んで一覧取得→インストール。
2. **モデルをダウンロード** — 「モデル管理」タブで Hugging Face のリポジトリID
   （例: `OpenVINO/Qwen3-8B-int4-ov`）または直リンクURLを指定。
3. **ロード** — ロードダイアログでデバイスと（必要なら）サーブモードを選び「ロード」。
   OVMS がモデルを `AVAILABLE` と報告するまで待機します。
4. **チャット** — 右サイドバーにチャット専用の生成パラメータ（temperature、top-p/k、
   max_tokens、systemプロンプト、思考制御）があります。

## 単体実行ファイルのビルド

Windows:

```bat
build.bat
```

`dist\LocArc\LocArc.exe`（Python同梱のポータブルフォルダ）が生成されます。
出荷前にスモークテストで起動確認できます:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\smoke-test.ps1
```

Linux:

```bash
./build.sh
```

`dist/LocArc/LocArc`（`install.sh` / `uninstall.sh` 込み・Python同梱の
ポータブルフォルダ）が生成されます。起動確認:

```bash
scripts/smoke-test.sh dist/LocArc/LocArc
```

データはexeと同じフォルダの `data` に保存されます。配布するときは `dist/LocArc`
フォルダごと固めます（Windowsはzip、Linuxは `tar.gz`）。Windowsは署名がないためSmartScreen
警告が出る場合があります（*詳細情報 → 実行*）。Linuxは展開して `./install.sh` を実行するか、
実行ファイルを直接起動します。

ビルド設定は `locarc.spec`（datas・windowed・UPXなし）にあります。CIは同じspecで
WindowsとLinuxを `v*` タグでビルドし、それぞれの起動確認後に全ファイルをGitHubリリースへ
添付します（`.github/workflows/build.yml`）。

## 画像生成

OVMSの `image_generation` タスク向けにエクスポートされたモデル（例:
[`OpenVINO/stable-diffusion-v1-5-int8-ov`](https://huggingface.co/OpenVINO/stable-diffusion-v1-5-int8-ov)）
は、検索・ダウンロード・ロードして画像パネルから生成できます。詳細は
[OVMSの画像生成デモ](https://docs.openvino.ai/2026/model-server/ovms_demos_image_generation.html)
を参照してください。

コミュニティのリポジトリには、変換済みトークナイザIR（`openvino_tokenizer.xml`）を含まない
ものがあります。OVMSはそのようなモデルをロードできても生成時に失敗するため、ロードダイアログで
警告し、**トークナイザIRを自動変換**ボタンを用意しています。初回のみ `openvino` /
`openvino-tokenizers` / `transformers` を選択中ランタイム同梱のPythonへ導入し（ネット接続・
数百MB・ランタイムごとに1回）、その後ローカルで変換します。2回目以降は導入済みツールを再利用
します。

## 他アプリからモデルAPIを利用する

外部アプリはOVMS本体へ直接接続してください（UIの `/proxy/*` は自ページ用のCORS回避です）:

| インターフェース | エンドポイント |
| --- | --- |
| Chat completions（OpenAI互換） | `POST http://<host>:8000/v3/chat/completions` |
| Embeddings | `POST http://<host>:8000/v3/embeddings` |
| Rerank | `POST http://<host>:8000/v3/rerank` |
| 音声合成 / 認識 | `POST http://<host>:8000/v3/audio/speech`, `/v3/audio/transcriptions` |
| Classic IR/ONNX | KServe / TFS API 例: `POST http://<host>:8000/v2/models/<名>/infer` |
| gRPC | ポート `9000` |

「設定」で OVMS APIキーを設定した場合、クライアントは
`Authorization: Bearer <キー>` を送る必要があります。

## リモートAPIアクセス

管理UIは常に `127.0.0.1` にのみ待ち受け、ネットワークには公開されません。モデルAPI（OVMS本体）
は別途公開できます:

1. **設定 → 詳細設定（OVMS）** でバインドアドレスを `0.0.0.0` に変更し、**OVMS APIキー**を
   設定（強く推奨）。
2. 外部クライアントは `http://<host>:<RESTポート>/v3` に
   `Authorization: Bearer <キー>` を付けて接続します（gRPCはgRPCポート）。
3. localhost外へ出す場合はリバースプロキシ（Caddy / nginx 等）でTLS化してください。

## 設定とデータ保存先

- ソース実行: `<プロジェクト>/data/`
- 配布exe: `<exeのあるフォルダ>/data/`
- 環境変数 `LOCARC_DATA` で変更可能（`AI_STUDIO_DATA` も引き続き使用可）。

| パス | 内容 |
| --- | --- |
| `config.json` | UI/OVMS設定、選択状態、シークレット（HFトークン、OVMS APIキー） |
| `load_presets.json` | モデルごとのロード設定 |
| `models/` | ダウンロード済みモデル（1モデル1フォルダ） |
| `runtimes/` | インストール済みOVMSランタイム |
| `chats/` | チャット履歴（JSON） |
| `app.log` | windowedビルド用ログ |

> HFトークンとOVMS APIキーは `config.json` に**平文**で保存されます。データフォルダの管理に
> 注意してください。

## セキュリティ上の注意

- 管理UIは `127.0.0.1` 固定で、外部に公開されるのはOVMSのモデルAPIのみです。
- ランタイムのダウンロード先は公式のGitHubリリース / OpenVINOストレージURLに制限され、
  公開されているSHA-256を検証します。アーカイブ展開はパストラバーサルを拒否します。
- UIプロキシはOVMS APIキーをサーバー側で付与するため、ブラウザにキーが渡りません。
- モデル/ランタイムの削除はデータフォルダ内に限定されています。

## トラブルシューティング

- **モデルのロードに失敗する** — 「設定 → ログ」を確認。LLMのメモリ不足はKVキャッシュ縮小、
  `u8` KV精度、コンテキスト長短縮で改善することが多いです（ロードダイアログの「推奨値を
  自動入力」は空きRAMから算出します）。
- **`max_prompt_len` が無視される** — NPU専用オプションです。CPU/GPUではエラーになるため
  自動的に省略します。
- **OneDriveフォルダでビルドが失敗する** — `build.bat` は `%TEMP%` でビルドして `dist\` に
  コピーするため、OneDriveの同期ロックを回避します。
- **Weekly で一覧構造エラーが出る** — 上流のファイル一覧構造が変わっています。Issueで
  報告してください。

## プロジェクト構成

```
locarc.py             エントリポイント（PyInstallerでも使用）
locarc.spec           PyInstallerビルド設定（onedir・windowed）
build.bat / build.sh  ビルドスクリプト（Windows / Linux）
run.bat / run.sh      開発用ランチャー（Windows / Linux）
app/
  main.py             FastAPIルート、OVMSプロキシ、静的配信
  ovms.py             ランタイム検出/インストール、プロセス制御
  models.py           Hugging Face / URLダウンロード・検索、モデル管理
  chats.py            チャット履歴の永続化
  config.py           パス・設定・パスワードハッシュ
  i18n.py             バックエンドメッセージカタログ（en/ja）
  tasks.py            バックグラウンドタスク管理
  fsutil.py           ファイル操作ヘルパー（安全な削除・パス検証）
  updater.py          自動更新の確認・適用処理（Windows / Linux）
  static/             SPA: index.html, app.js, i18n.js, style.css
scripts/              補助スクリプト（smoke-test.ps1 / smoke-test.sh、リリースノート）
packaging/linux/      Linux用 install.sh / uninstall.sh / .desktop テンプレート
tests/                バックエンドAPIテスト（pytest）
.github/              ワークフローとIssue/PRテンプレート
```

## 開発

```bash
pip install -r requirements-dev.txt
ruff check .
python -m compileall -q app locarc.py
```

プルリクエストではCIで同じチェックがWindowsとLinuxの両方で実行されます。Windows / Linux の
実行ファイルは *Build apps* ワークフロー（`v*` タグまたは手動実行）でビルドされます。

## アップデート

パッケージ版は起動時にGitHub Releasesを確認し（1日1回まで）、新しいバージョンがあれば
**設定**タブに通知ドットを表示します。**設定 → アップデート**から手動確認とワンクリック更新が
できます:

1. プラットフォーム別のアーカイブ（`LocArc-windows-x64.zip` /
   `LocArc-linux-x64.tar.gz`）をダウンロードし、リリースの `SHA256SUMS.txt` と照合して
   検証します。
2. 新ビルドをステージングし、アプリは終了。分離起動した小さなヘルパーがアプリ本体
   （`LocArc.exe` / `LocArc` と `_internal`）を入れ替えて再起動します。
   ヘルパーはWindowsではPowerShell + robocopy、LinuxではPOSIX `sh` スクリプトです。

`data` フォルダ（ランタイム・モデル・チャット・設定）は一切変更されません。起動時の確認は同じ
カードで無効化できます。ソース実行の場合は `git pull` で更新してください。

> **v1.4.0以前**のビルドでは自動更新の適用に失敗することがあります（ヘルパースクリプトの起動方式
> に問題があり、終了後に実行されませんでした）。更新後にアプリが再起動しない場合は、一度だけ
> 手動で最新リリースを導入してください。v1.4.1以降は自動更新が正常に動作します。

## Intel AI Studio からの移行

データの配置は変わっていません。実行ファイルと同じフォルダの `data` をそのまま使用します。
ポータブル版は新しいバージョンを旧フォルダに上書き展開すればデータを引き継げます。Windows
インストーラーは Inno Setup の App ID を変更していないため、旧インストール先と `data` を
維持したままアップグレードします。Linux では `install.sh` が初回実行時に
`~/.local/share/intel-ai-studio/data` を `~/.local/share/locarc/data` へコピーします。旧環境
変数 `AI_STUDIO_DATA` も `LOCARC_DATA` の別名として引き続き使用できます。

旧リポジトリ名（`Asahi-Prv/i-AI-Studio`）には旧 `Intel-AI-Studio-*` アセット名と旧レイアウトを
含む互換リリースを置いているため、v1.14.x のビルドからも LocArc を自動で検出・導入できます。
更新後の `update_repo` 設定は `Asahi-Prv/locarc` に移行されます。自動更新が表示されない場合は、
最新リリースを一度手動で導入してください。

## コントリビュート

コントリビュート歓迎です。開発環境・コーディング規約・ローカライズ・PRの流れは
[CONTRIBUTING.ja.md](CONTRIBUTING.ja.md)（英語版: [CONTRIBUTING.md](CONTRIBUTING.md)）を
参照してください。

- バグ報告・機能リクエストはIssueフォームからお願いします。
- セキュリティ問題は [SECURITY.md](SECURITY.md) の手順で非公開で報告してください。
- リリース履歴は [CHANGELOG.md](CHANGELOG.md) を参照してください。

## ライセンス

[MIT](LICENSE) © 2026 Asahi

Intel および OpenVINO は Intel Corporation の商標です。本プロジェクトは Intel Corporation
との提携・承認・スポンサー関係はありません。
