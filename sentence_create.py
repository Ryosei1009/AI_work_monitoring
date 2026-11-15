import json
import os
import threading

import env_loader  # noqa: F401  .env を os.environ へ読み込む（genai.Client より前に必要）
from google import genai

# 取得したAPIキーをここに設定
ai_client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))
DEBUG = 0

# 生成済みの文章を溜めておくプール（在庫）と、その保存先ファイル
CACHE_FILE = os.path.join(os.path.dirname(__file__), "sentence_cache.json")
VARIANTS = 3  # 各カテゴリで作っておくバリエーション数（使い回す）

# 警告文の対象ラベル（gauge_manager.py の targets と対応）
WARNING_LABELS = ["睡眠", "スマホ利用", "姿勢が悪いの"]


def _call_gemini(prompt, as_json=False):
    """
    Gemini APIを呼び出してテキストを取得する共通関数。
    as_json=True のときは JSON 形式での出力を要求する。
    """
    try:
        config = {"response_mime_type": "application/json"} if as_json else None
        response = ai_client.models.generate_content(
            model='gemini-3.1-flash-lite',
            contents=prompt,
            config=config,
        )
        return response.text.strip()
    except Exception as e:
        print(f"【システムエラー】AIとの通信に失敗しました: {e}")
        return "" if as_json else "通信エラーが発生しました。"


# ---------------------------------------------------------------------------
# 単発生成（在庫が尽きたときのフォールバック用）
# ---------------------------------------------------------------------------

def generate_10warning_text(violation_type):
    """サボり検知（10秒）時の警告文を1つ生成する"""
    prompt = (
        f"あなたはデスクワークを監視する厳しいAIです。"
        f"ユーザーが「{violation_type}」を10秒以上続けています。"
        f"サボりをやめさせるような、短くて鋭い警告文を20文字以内で言ってください。"
    )
    if DEBUG:
        return "【DEBUG】警告文生成テスト中です。"
    return _call_gemini(prompt)


def generate_30warning_text(violation_type):
    """サボり検知（30秒）時の警告文を1つ生成する"""
    prompt = (
        f"あなたはデスクワークを監視する厳しいAIです。"
        f"ユーザーが「{violation_type}」を30秒以上続けています。"
        f"サボりをやめさせるような、短くて鋭い警告文を20文字以内で言ってください。"
    )
    if DEBUG:
        return "【DEBUG】警告文生成テスト中です。"
    return _call_gemini(prompt)

def generate_30warning_sleep_text(violation_type):
    """サボり検知（30秒）時の警告文を1つ生成する"""
    prompt = (
        f"あなたはデスクワークを監視する厳しいAIです。"
        f"ユーザーが「{violation_type}」を30秒以上続けています。"
        f"もう諦めて睡眠するよう推奨するような、短くて鋭い警告文を20文字以内で言ってください。"
    )
    if DEBUG:
        return "【DEBUG】警告文生成テスト中です。"
    return _call_gemini(prompt)


def generate_lawyer_excuse():
    """弁護士AIの言い訳を1つ生成する"""
    prompt = (
        "あなたはサボってしまったユーザーを熱心に擁護する敏腕弁護士AIです。"
        "ユーザーが「疲労」や「業務上の理由」などでサボったのだという、"
        "もっともらしい言い訳を50文字以内で生成してください。"
    )
    if DEBUG:
        return "【DEBUG】弁護士の言い訳生成テスト中です。"
    return _call_gemini(prompt)


def generate_prosecutor_sentence():
    """検察官AIの求刑を1つ生成する"""
    prompt = (
        "あなたはサボったユーザーを絶対に許さない冷酷な検察官AIです。"
        "サボった罪に対する求刑（例：スマホ没収の刑、スクワット10回の刑など）と、"
        "厳しい言葉を50文字以内で生成してください。"
    )
    if DEBUG:
        return "【DEBUG】検察の求刑生成テスト中です。"
    return _call_gemini(prompt)


def generate_judgment():
    """裁判長AIの最終判決を1つ生成する"""
    prompt = (
        "あなたは厳格な裁判長AIです。"
        "デスクワークをサボったユーザーに対する最終判決（有罪か無罪かと、具体的な処罰）を"
        "50文字以内で厳かに言い渡してください。"
    )
    if DEBUG:
        return "【DEBUG】判決生成テスト中です。"
    return _call_gemini(prompt)


# ---------------------------------------------------------------------------
# 先読みキャッシュ
#   起動時に「1回だけ」Geminiへ送信して全カテゴリの文章をまとめて作り、
#   ファイルへ保存する。2回目以降はファイルから読むだけで送信しない。
#   使うときは保存済みのバリエーションを順番に使い回す（追加コスト0）。
# ---------------------------------------------------------------------------

# カテゴリ名 -> 単発生成関数（フォールバック用）の対応表
_GENERATORS = {
    "excuse": generate_lawyer_excuse,
    "prosecutor": generate_prosecutor_sentence,
    "judgment": generate_judgment,
}
for _label in WARNING_LABELS:
    _GENERATORS[f"10warning:{_label}"] = (
        lambda label=_label: generate_10warning_text(label)
    )
    if _label == "睡眠":
        # 30秒睡眠時だけは「諦めて寝るよう推奨する」専用の文章を使う
        _GENERATORS[f"30warning:{_label}"] = (
            lambda label=_label: generate_30warning_sleep_text(label)
        )
    else:
        _GENERATORS[f"30warning:{_label}"] = (
            lambda label=_label: generate_30warning_text(label)
        )

_pools = {key: [] for key in _GENERATORS}
_cursors = {key: 0 for key in _GENERATORS}  # 使い回し用のカーソル
_lock = threading.Lock()


def _save_cache():
    """現在のプールをファイルへ保存する。"""
    with _lock:
        snapshot = {key: list(values) for key, values in _pools.items()}
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"【システムエラー】文章キャッシュの保存に失敗しました: {e}")


def _load_cache():
    """
    ファイルから在庫を読み込む。中身のある在庫を復元できたら True を返す。
    """
    if not os.path.exists(CACHE_FILE):
        return False
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"【システムエラー】文章キャッシュの読み込みに失敗しました: {e}")
        return False

    has_any = False
    with _lock:
        for key in _pools:
            loaded = data.get(key)
            if isinstance(loaded, list):
                texts = [t for t in loaded if isinstance(t, str) and t]
                _pools[key] = texts
                if texts:
                    has_any = True
    return has_any


def _batch_prompt(variants):
    """全カテゴリの文章をまとめて作るための1本のプロンプトを組み立てる。"""
    labels = "、".join(f'「{l}」' for l in WARNING_LABELS)
    return (
        "あなたは複数のAIキャラクターのセリフをまとめて作る台本作家です。"
        f"以下の各カテゴリについて、それぞれ{variants}個ずつ、"
        "互いに重複しないセリフを作ってください。\n"
        "\n"
        f"- warning_10: デスクワークを監視する厳しいAIが、ユーザーが各行為（{labels}）を"
        "10秒以上続けたときに言う、20文字以内の短く鋭い警告文。\n"
        "- warning_30: 同じ行為を30秒以上続けたときの、20文字以内のさらに厳しい警告文。"
        "ただし「睡眠」だけは例外で、厳しく責めるのではなく"
        "『もう諦めて眠るよう推奨する』内容にしてください。\n"
        "- excuse: サボったユーザーを熱心に擁護する敏腕弁護士AIの、もっともらしい言い訳（50文字以内）。\n"
        "- prosecutor: サボったユーザーを許さない冷酷な検察官AIの求刑と厳しい言葉（50文字以内）。\n"
        "- judgment: 厳格な裁判長AIの最終判決（有罪か無罪かと処罰、50文字以内）。\n"
        "\n"
        "出力は必ず次のJSON形式のみとし、説明やコードブロックは付けないでください。\n"
        "{\n"
        '  "warning_10": {"睡眠": [...], "スマホ利用": [...], "姿勢が悪いの": [...]},\n'
        '  "warning_30": {"睡眠": [...], "スマホ利用": [...], "姿勢が悪いの": [...]},\n'
        '  "excuse": [...],\n'
        '  "prosecutor": [...],\n'
        '  "judgment": [...]\n'
        "}\n"
        f"各配列にはちょうど{variants}個の文字列を入れてください。"
    )


def _strip_json(text):
    """```json ... ``` のようなコードブロックが付いていても中身を取り出す。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]  # 先頭の ``` 行を除去
        if text.endswith("```"):
            text = text[: -3]
    return text.strip()


def _generate_all_batch(variants):
    """
    Geminiへ「1回だけ」送信して全カテゴリの文章を生成し、プールへ格納する。
    成功したら True を返す。
    """
    raw = _call_gemini(_batch_prompt(variants), as_json=True)
    if not raw:
        return False
    try:
        data = json.loads(_strip_json(raw))
    except json.JSONDecodeError as e:
        print(f"【システムエラー】文章のJSON解析に失敗しました: {e}")
        return False

    def _as_list(value):
        return [t for t in value if isinstance(t, str) and t] if isinstance(value, list) else []

    with _lock:
        for label in WARNING_LABELS:
            _pools[f"10warning:{label}"] = _as_list(
                (data.get("warning_10") or {}).get(label)
            )
            _pools[f"30warning:{label}"] = _as_list(
                (data.get("warning_30") or {}).get(label)
            )
        _pools["excuse"] = _as_list(data.get("excuse"))
        _pools["prosecutor"] = _as_list(data.get("prosecutor"))
        _pools["judgment"] = _as_list(data.get("judgment"))

    return any(_pools[key] for key in _pools)


def prefetch_all(variants=VARIANTS, force=False):
    """
    main.py の起動時に呼び出す。
    - キャッシュファイルがあれば、そこから復元して終わり（Gemini送信なし）。
    - なければ Gemini へ1回だけ送信して全文章を作り、ファイルへ保存する。
    force=True にすると、キャッシュを無視して作り直す。
    """
    if not force and _load_cache():
        print("文章キャッシュを読み込みました（API送信なし）。")
        return

    print("文章をまとめて生成します（Gemini送信は1回）…")
    if _generate_all_batch(variants):
        _save_cache()
        print("文章の生成・保存が完了しました。")
    else:
        print("【システムエラー】文章の一括生成に失敗しました。必要時に個別生成します。")


def peek_pool(key):
    """プールの中身を消費せずにコピーで取り出す（音声の先合成用）。"""
    with _lock:
        return list(_pools.get(key, []))


def _get(key):
    """
    プールから使い回しで1つ取り出す（順番に巡回）。
    万一在庫が空なら、そのときだけ単発生成する（フォールバック）。
    """
    with _lock:
        pool = _pools.get(key)
        if pool:
            text = pool[_cursors[key] % len(pool)]
            _cursors[key] += 1
            return text

    # 在庫なし。ここだけAPIを1回使う。
    return _GENERATORS[key]()


# 各カテゴリの取り出し口（保存済みの文章を使うので基本ノーコスト）
def next_10warning_text(violation_type):
    return _get(f"10warning:{violation_type}")


def next_30warning_text(violation_type):
    return _get(f"30warning:{violation_type}")


def next_lawyer_excuse():
    return _get("excuse")


def next_prosecutor_sentence():
    return _get("prosecutor")


def next_judgment():
    return _get("judgment")
