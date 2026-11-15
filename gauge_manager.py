import threading

import light_control
import sentence_create
import voice_play

angry_gauge = 0
TRIAL_THRESHOLD = 100  # このゲージ値に達すると裁判が開廷する
# ライトオフ（居眠り確定）でシステム終了を要求するフラグ。main.py が監視する
shutdown_requested = False
DETECT_KEYS = ["sleep", "phone", "posture"]
gauge_manage = [
    {"sleep": False, "phone": False, "posture": False},
    {"sleep": False, "phone": False, "posture": False}
]
toggle_manage = [
    {"sleep": False, "phone": False, "posture": False},  # 0: 10秒警告
    {"sleep": False, "phone": False, "posture": False},  # 1: 30秒警告
    {"sleep": False, "phone": False, "posture": False}   # 2: ライト制御
]

def reset_gauge():
    global angry_gauge
    angry_gauge = 0
    for state in gauge_manage:
        for key in DETECT_KEYS:
            state[key] = False

def update_gauge(detect_flags, gauge_state, points):
    gained = 0
    for idx, key in enumerate(DETECT_KEYS):
        detected = detect_flags[idx]
        if detected and not gauge_state[key]:
            gained += points
            gauge_state[key] = True
        elif not detected and gauge_state[key]:
            gauge_state[key] = False
    return gained


def gauge_manager(ten_detect, thirty_detect):
    global angry_gauge, toggle_manage, shutdown_requested
    # for idx, key in enumerate(DETECT_KEYS):
    #     if ten_detect[idx]:
    #         print(f"{key}が10秒以上検知")
    #     if thirty_detect[idx]:
    #         print(f"{key}が30秒以上検知")

    angry_gauge += update_gauge(ten_detect, gauge_manage[0], 5)
    angry_gauge += update_gauge(thirty_detect, gauge_manage[1], 15)

    # このフレームでゲージが裁判のしきい値に達したら、裁判の音声と重ならないよう
    # 開廷のトリガーとなった警告文の読み上げはスキップする
    opening_trial = angry_gauge >= TRIAL_THRESHOLD - 10

    targets = [
        ("sleep", "睡眠"),
        ("phone", "スマホ利用"),
        ("posture", "姿勢が悪いの"),
    ]

    for key, label in targets:
        idx = DETECT_KEYS.index(key)

        if ten_detect[idx] and not toggle_manage[0][key]:
            if not opening_trial:
                # 文章はメインプロセスの先読みプールから即座に取得し、
                # 時間のかかる読み上げだけを別プロセスへ渡す
                text = sentence_create.next_10warning_text(label)
                # 音声は先合成キャッシュから即再生。スレッドなら同一メモリの
                # キャッシュを共有できる（プロセスだと共有されず再合成になる）
                voice_play.speak_async(text)
            toggle_manage[0][key] = True
        elif not ten_detect[idx] and toggle_manage[0][key]:
            toggle_manage[0][key] = False

        if thirty_detect[idx] and not toggle_manage[1][key]:
            if not opening_trial:
                text = sentence_create.next_30warning_text(label)
                voice_play.speak_async(text)
            toggle_manage[1][key] = True
        elif not thirty_detect[idx] and toggle_manage[1][key]:
            toggle_manage[1][key] = False

    if thirty_detect[DETECT_KEYS.index("sleep")] and not toggle_manage[2]["sleep"]:
        # ui.light_off はメインプロセスの HUD が参照するグローバル。
        # プロセスだとメモリが共有されず反映されないため、スレッドで実行する
        threading.Thread(
            target=light_control.control_light,
            args=("turnOff",),
            daemon=True,
        ).start()
        toggle_manage[2]["sleep"] = True
        # ライトを消したらシステム自体を終了する（main.py が検知して後始末する）
        shutdown_requested = True
    elif not thirty_detect[DETECT_KEYS.index("sleep")] and toggle_manage[2]["sleep"]:
        toggle_manage[2]["sleep"] = False
