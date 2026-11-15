"""
.env ファイルを os.environ に読み込む小さなヘルパー。
python-dotenv などの外部ライブラリに依存しない。

このモジュールを import した時点で、同じフォルダの .env を自動的に読み込む。
GEMINI_API_KEY などを import 時に使うモジュールより「先に」import すること。
"""
import os


def load_env(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # 既に環境変数が設定されている場合はそちらを優先する
            if key and key not in os.environ:
                os.environ[key] = value


# import しただけで読み込まれるようにしておく
load_env()
