import threading
import time

import env_loader  # noqa: F401  他モジュールより先に .env を読み込む
import cv2

import gauge_manager
import sentence_create
import ui
import voice_play
from detect_manager import DetectManager
from judgement import judgement
from phone_monitor import PhoneMonitor
from posture_monitor import PostureMonitor

FRAME_RATE  = 60           # target FPS
WINDOW_NAME = "Focus Monitor"


def main():
    # 警告文・裁判文は生成に時間がかかるため、起動時に先読みして
    # プール（sentence_cache.json）へ溜めておく
    sentence_create.prefetch_all()

    # 溜めた文章の「音声」も起動時に先合成してメモリへ載せておく。
    # 本番の発話時は合成待ちなしで即再生でき、読み上げの頭の間がなくなる。
    # （カメラ初期化と並行させるため別スレッドで実行）
    warmup = []
    for label in sentence_create.WARNING_LABELS:
        for text in sentence_create.peek_pool(f"10warning:{label}"):
            warmup.append((text, voice_play.SPEAKER))
        for text in sentence_create.peek_pool(f"30warning:{label}"):
            warmup.append((text, voice_play.SPEAKER))
    for text in sentence_create.peek_pool("excuse"):
        warmup.append((text, 11))
    for text in sentence_create.peek_pool("prosecutor"):
        warmup.append((text, 9))
    for text in sentence_create.peek_pool("judgment"):
        warmup.append((text, 13))
    # 裁判の定型セリフも先合成しておく
    warmup += [
        ("裁判を開廷します。", 16),
        ("弁護士", 16),
        ("検察官", 16),
        ("裁判官", 16),
    ]
    voice_play.prewarm_async(warmup)

    monitor = PostureMonitor()
    phone_monitor = PhoneMonitor()
    detector = DetectManager()
    cap = cv2.VideoCapture(0)

    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    T  = 1 / FRAME_RATE
    t0 = time.time()

    judge_thread = None
    was_judging  = False
    shutdown_at  = None   # ライトオフによる終了要求を受けた時刻
    SHUTDOWN_GRACE = 3  # 消灯オーバーレイを見せてから終了するまでの猶予(秒)
    # 裁判中はプレビューだけ更新するため、直前の検知状態を保持しておく
    statuses = [("POSTURE", False), ("DROWSINESS", False), ("PHONE", False)]

    while True:
        elapsed = time.time() - t0
        if elapsed < T:
            time.sleep(T - elapsed)
        t0 = time.time()

        ok, frame = cap.read()
        if not ok:
            break

        judging = judge_thread is not None and judge_thread.is_alive()

        # 裁判が終わった直後にゲージをリセット
        if was_judging and not judging:
            gauge_manager.reset_gauge()
            judge_thread = None

        if not judging:
            # 通常時のみ検知とゲージ更新を行う（裁判中は増やさない）
            _, _, napping, bad_posture, drowsy_now = monitor.process(frame)
            _, _, using_phone, phone_now = phone_monitor.process(frame)

            # ゲージ・警告は誤検知防止のため確定フラグを使う
            detects = []
            if napping:
                detects.append("sleep")
            if bad_posture:
                detects.append("posture")
            if using_phone:
                detects.append("phone")

            ten_detect, thirty_detect = detector.detect_manager(detects)
            gauge_manager.gauge_manager(ten_detect, thirty_detect)

            # STATUSのALERTは毎フレームの生の検知信号を反映（即時に更新）
            statuses = [
                ("POSTURE",    bad_posture),
                ("DROWSINESS", drowsy_now),
                ("PHONE",      phone_now),
            ]

            # ゲージが満タンになったら裁判をバックグラウンドで開始
            if gauge_manager.angry_gauge >= gauge_manager.TRIAL_THRESHOLD:
                judge_thread = threading.Thread(target=judgement, daemon=True)
                judge_thread.start()
                judging = True

        # 洗練されたHUDを重ねて表示（裁判中もカメラは動き続ける）
        ui.draw_hud(
            frame,
            statuses=statuses,
            gauge_value=gauge_manager.angry_gauge,
            judging=judging,
        )
        cv2.imshow(WINDOW_NAME, frame)

        was_judging = judging

        # ライトオフ（居眠り確定）が発火したらシステムを終了する。
        # 消灯オーバーレイを一瞬見せるため少しだけ猶予を置いてから抜ける。
        if gauge_manager.shutdown_requested and shutdown_at is None:
            shutdown_at = time.time()
            print("居眠りを検知しました。ライトを消してシステムを終了します。")
        if shutdown_at is not None and time.time() - shutdown_at >= SHUTDOWN_GRACE:
            break

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    monitor.close()
    phone_monitor.close()


if __name__ == "__main__":
    main()
