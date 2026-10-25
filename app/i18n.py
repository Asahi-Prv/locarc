"""Small message catalog for backend-facing strings (English / Japanese).

The UI sends its current language via the ``Accept-Language`` header. Background
workers remember the language of the request that started them through
``tasks`` so that progress messages stay consistent.
"""
from __future__ import annotations

DEFAULT_LANG = "en"
LANGS = ("en", "ja")

MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # generic
        "task.preparing": "Preparing...",
        "task.done": "Done",
        "task.failed": "Failed",
        "task.cancelled": "Cancelled",
        "task.downloading": "Downloading...",
        "task.hf_downloading": "Downloading {repo}...",
        "task.done_name": "Done: {name}",
        "task.extracting": "Extracting...",
        "task.verifying": "Verifying SHA256...",
        "task.install_done": "Installed: {label}",
        "task.ovms_install": "Install OVMS: {label}",
        "task.update_title": "Update: v{version}",
        "task.update_downloading": "Downloading the update...",
        "task.update_ready": "Update downloaded. Restarting to apply...",
        "task.tokenizer_title": "Convert tokenizer IR: {name}",
        "task.tokenizer_checking": "Checking the conversion tools...",
        "task.tokenizer_installing": "Installing converter packages into the OVMS runtime (first time only, a few hundred MB)...",
        "task.tokenizer_converting": "Converting the tokenizer to OpenVINO IR...",
        "task.tokenizer_done": "Tokenizer IR created",
        "task.hf_download": "HF: {repo}",
        "task.url_download": "URL: {url}",
        # chats
        "chat.new_title": "New chat",
        "chat.untitled": "Untitled",
        # errors
        "err.bad_channel": "channel must be 'stable' or 'weekly'",
        "err.versions_failed": "Failed to fetch the version list: {error}",
        "err.url_not_allowed": "URL is not allowed",
        "err.no_versions": "No matching version found",
        "err.runtime_not_found": "The selected runtime was not found",
        "err.not_found": "Not found",
        "err.bad_repo_id": "repo_id must be in 'org/name' format",
        "err.bad_url": "URL must start with http:// or https://",
        "err.search_query_required": "Enter a search query",
        "err.search_failed": "Model search failed: {error}",
        "err.update_failed": "Update check failed: {error}",
        "err.update_no_asset": "This release has no downloadable update asset",
        "err.update_checksums": "Update verification failed (no checksums in the release)",
        "err.update_not_available": "No update to apply. Check again first.",
        "err.update_source_mode": "In-app updates are only available for the packaged app. "
                                  "From source, update with git pull.",
        "err.model_not_found": "Model not found",
        "err.model_not_found_id": "Model '{name}' not found",
        "err.no_model_selected": "No model selected",
        "err.no_runtime": "No OVMS runtime installed. Install one from the Settings tab.",
        "err.hf_download_active": "This model is already being downloaded",
        "err.hf_download_done": "This model is already downloaded (delete it first to download again)",
        "err.bad_mode": "mode must be one of: {allowed}",
        "err.bad_option_value": "{key} must be one of: {allowed} (empty = model default)",
        "err.bad_option_number": "{key} must be a number",
        "err.bad_port": "{key} must be an integer between 1 and 65535",
        "err.ovms_not_running": "OVMS is not running",
        "err.bad_chat_id": "Invalid chat id",
        "err.chat_not_found": "Chat not found",
        "err.cancelled": "Cancelled",
        "err.sha_mismatch": "SHA256 mismatch (the download may be corrupted)",
        "err.exe_not_found": "{exe} was not found in the package",
        "err.weekly_structure": "Unexpected 'weekly' package listing structure",
        "err.runtime_not_found_id": "Runtime '{runtime_id}' not found",
        "err.runtime_exe_missing": "Runtime '{runtime_id}' does not contain {exe}",
        "err.already_running": "Already running. Stop it first.",
        "err.port_busy": "Port {port} is already in use. Close the other application or change the port in Settings.",
        "err.port_busy_ovms": "Port {port} is already served by another OVMS (models: {models}). Close that application or change the port in Settings.",
        "err.port_foreign": "Port {port} is answering with a different OVMS (models: {models}) — another application is using the port. Close it or change the port in Settings.",
        "err.unsafe_archive": "Archive contains an unsafe path",
        "err.load_timeout": "Model load timed out (300 s)",
        "err.ovms_exited": "ovms exited (code {code}). Check the logs in the Settings tab.",
        "err.delete_failed": "Failed to delete {path} (it may be in use by another process)",
        "err.runtime_python_missing": "The runtime does not contain a Python interpreter",
        "err.tokenizer_install_failed": "Could not install the conversion tools: {error}",
        "err.tokenizer_convert_failed": "Tokenizer conversion failed: {error}",
        # runtime log lines
        "log.flag_unsupported": "Skipping {flag}: not supported by this build",
        "log.api_key_enabled": "API_KEY auth enabled (external clients need a Bearer key)",
    },
    "ja": {
        # generic
        "task.preparing": "準備中...",
        "task.done": "完了",
        "task.failed": "失敗",
        "task.cancelled": "キャンセルしました",
        "task.downloading": "ダウンロード中...",
        "task.hf_downloading": "{repo} をダウンロード中...",
        "task.done_name": "完了: {name}",
        "task.extracting": "展開中...",
        "task.verifying": "SHA256 検証中...",
        "task.install_done": "インストール完了: {label}",
        "task.ovms_install": "OVMS インストール: {label}",
        "task.update_title": "アップデート: v{version}",
        "task.update_downloading": "アップデートをダウンロード中...",
        "task.update_ready": "更新をダウンロードしました。再起動して適用します...",
        "task.tokenizer_title": "トークナイザIR変換: {name}",
        "task.tokenizer_checking": "変換ツールを確認中...",
        "task.tokenizer_installing": "変換ツールをOVMSランタイムへインストール中（初回のみ・数百MB）...",
        "task.tokenizer_converting": "トークナイザをOpenVINO IRへ変換中...",
        "task.tokenizer_done": "トークナイザIRを作成しました",
        "task.hf_download": "HF: {repo}",
        "task.url_download": "URL: {url}",
        # chats
        "chat.new_title": "新しいチャット",
        "chat.untitled": "無題",
        # errors
        "err.bad_channel": "channel は stable / weekly のいずれかです",
        "err.versions_failed": "バージョン一覧の取得に失敗しました: {error}",
        "err.url_not_allowed": "許可されていないURLです",
        "err.no_versions": "対象バージョンが見つかりませんでした",
        "err.runtime_not_found": "指定されたランタイムが見つかりません",
        "err.not_found": "見つかりません",
        "err.bad_repo_id": "repo_id を 'org/name' 形式で指定してください",
        "err.bad_url": "http(s) のURLを指定してください",
        "err.search_query_required": "検索キーワードを入力してください",
        "err.search_failed": "モデル検索に失敗しました: {error}",
        "err.update_failed": "更新の確認に失敗しました: {error}",
        "err.update_no_asset": "このリリースには更新用ファイルがありません",
        "err.update_checksums": "更新の検証に失敗しました（リリースにチェックサムがありません）",
        "err.update_not_available": "適用できる更新がありません。先に更新を確認してください。",
        "err.update_source_mode": "アプリ内更新はパッケージ版専用です。ソース実行では git pull で更新してください。",
        "err.model_not_found": "モデルが見つかりません",
        "err.model_not_found_id": "モデル '{name}' が見つかりません",
        "err.no_model_selected": "モデルが選択されていません",
        "err.no_runtime": "OVMSランタイムがありません。「設定」タブでインストールしてください",
        "err.hf_download_active": "このモデルはすでにダウンロード中です",
        "err.hf_download_done": "このモデルはすでにダウンロード済みです（再取得するには先に削除してください）",
        "err.bad_mode": "mode は {allowed} のいずれかです",
        "err.bad_option_value": "{key} は {allowed} のいずれかです（空欄=モデル既定）",
        "err.bad_option_number": "{key} は数値で指定してください",
        "err.bad_port": "{key} は 1〜65535 の整数で指定してください",
        "err.ovms_not_running": "OVMS が起動していません",
        "err.bad_chat_id": "不正なIDです",
        "err.chat_not_found": "チャットが見つかりません",
        "err.cancelled": "キャンセルされました",
        "err.sha_mismatch": "SHA256 が一致しません（ダウンロード破損の可能性）",
        "err.exe_not_found": "パッケージ内に {exe} が見つかりません",
        "err.weekly_structure": "weekly packages の一覧構造が変わったようです",
        "err.runtime_not_found_id": "ランタイム '{runtime_id}' が見つかりません",
        "err.runtime_exe_missing": "ランタイム '{runtime_id}' に {exe} がありません",
        "err.already_running": "すでに起動しています。先に停止してください。",
        "err.port_busy": "{port} 番ポートは使用中です。他のアプリを終了するか、設定でポートを変更してください。",
        "err.port_busy_ovms": "{port} 番ポートは別の OVMS が使用中です（モデル: {models}）。そのアプリを終了するか、設定でポートを変更してください。",
        "err.port_foreign": "{port} 番ポートでは別の OVMS が応答しています（モデル: {models}）。他のアプリが使用中です。終了するか、設定でポートを変更してください。",
        "err.unsafe_archive": "アーカイブに安全でないパスが含まれています",
        "err.load_timeout": "ロードがタイムアウトしました（300秒）",
        "err.ovms_exited": "ovms が終了しました (code {code})。設定タブのログを確認してください。",
        "err.delete_failed": "削除に失敗しました（他のプロセスが使用中かもしれません）: {path}",
        "err.runtime_python_missing": "ランタイムにPythonが見つかりません",
        "err.tokenizer_install_failed": "変換ツールのインストールに失敗しました: {error}",
        "err.tokenizer_convert_failed": "トークナイザの変換に失敗しました: {error}",
        # runtime log lines
        "log.flag_unsupported": "このビルドは {flag} をサポートしていないため省略します",
        "log.api_key_enabled": "API_KEY 認証を有効化しました（外部利用には Bearer キーが必要）",
    },
}


def normalize(lang: str | None) -> str:
    """Map an Accept-Language-ish value to a supported language code."""
    if lang and lang.strip().lower().startswith("ja"):
        return "ja"
    return DEFAULT_LANG


def tr(lang: str | None, msg_key: str, **fmt) -> str:
    """Translate ``msg_key`` into ``lang``, falling back to English, then the key."""
    table = MESSAGES.get(normalize(lang), MESSAGES[DEFAULT_LANG])
    template = table.get(msg_key) or MESSAGES[DEFAULT_LANG].get(msg_key) or msg_key
    try:
        return template.format(**fmt)
    except (KeyError, IndexError, ValueError):
        return template
