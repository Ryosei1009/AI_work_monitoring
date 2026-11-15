# 使い方:
#   voice_play.speak("読み上げたい文章")            # 同期再生（呼び出し元をブロック）
#   voice_play.speak_async("読み上げたい文章")       # 別スレッドで非同期再生
#   voice_play.prewarm([(text, speaker), ...])        # 起動時に音声を先合成してキャッシュ

import os
import threading

import winsound
import requests

VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://127.0.0.1:50021")
SPEAKER = 14

# 合成済みのWAVバイト列をメモリに保持しておくキャッシュ（追加コスト0で即再生）
#   キー: (text, speaker) / 値: wav バイト列
_audio_cache = {}
_cache_lock = threading.Lock()


def _synthesize(text, speaker):
    """VOICEVOX で音声を合成して WAV のバイト列を返す。"""
    query = requests.post(
        f"{VOICEVOX_URL}/audio_query",
        params={"text": text, "speaker": speaker},
    )
    query.raise_for_status()
    synthesis = requests.post(
        f"{VOICEVOX_URL}/synthesis",
        params={"speaker": speaker},
        json=query.json(),
    )
    synthesis.raise_for_status()
    return synthesis.content


def _get_audio(text, speaker):
    """キャッシュにあればそれを、なければ合成して（次回のためにキャッシュして）返す。"""
    key = (text, speaker)
    with _cache_lock:
        cached = _audio_cache.get(key)
    if cached is not None:
        return cached

    wav = _synthesize(text, speaker)
    with _cache_lock:
        _audio_cache[key] = wav
    return wav


def prewarm(items):
    """
    起動時に (text, speaker) のリストをまとめて先合成し、メモリへ載せておく。
    これにより本番の発話時は合成待ちなしで即座に鳴らせる。
    VOICEVOX のコールドスタート解消も兼ねる。
    """
    ok = 0
    for text, speaker in items:
        if not text:
            continue
        try:
            _get_audio(text, speaker)
            ok += 1
        except requests.RequestException as e:
            print(f"【システムエラー】音声の先合成に失敗しました（{text!r}）: {e}")
    print(f"音声を先合成しました（{ok}/{len(items)} 件）。")


def prewarm_async(items):
    """prewarm を別スレッドで走らせる（起動をブロックしない）。"""
    threading.Thread(target=prewarm, args=(items,), daemon=True).start()


def speak(text, speaker=SPEAKER):
    """音声を（キャッシュ優先で取得して）メモリから同期再生する。"""
    try:
        wav = _get_audio(text, speaker)
    except requests.RequestException as e:
        print(f"【システムエラー】音声の合成に失敗しました: {e}")
        return
    # 一時ファイルを書かずメモリから直接再生（SND_MEMORY）
    winsound.PlaySound(wav, winsound.SND_MEMORY)


def speak_async(text, speaker=SPEAKER):
    """speak を別スレッドで走らせる（呼び出し元をブロックしない）。"""
    threading.Thread(target=speak, args=(text, speaker), daemon=True).start()
