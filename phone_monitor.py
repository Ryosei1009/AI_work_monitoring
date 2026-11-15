import math
import os
import sys
import time

# best.pt は Python 3.13 で保存されており、WindowsPath が `pathlib._local` に
# 属したものとしてpickleされている。Python 3.14 では `pathlib._local` が廃止され
# Pathクラスは `pathlib` 直下に戻ったため、unpickle時に ModuleNotFoundError になる。
# 3.14 以降で `pathlib._local` が無ければ `pathlib` を別名登録して読めるようにする。
import pathlib
if "pathlib._local" not in sys.modules:
    try:
        import pathlib._local  # noqa: F401  (3.13ではこちらが本体)
    except ModuleNotFoundError:
        sys.modules["pathlib._local"] = pathlib

import cv2
import mediapipe as mp
import torch

from mediapipe.tasks import python
from mediapipe.tasks.python import vision

YOLOV5_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yolov5-master")
YOLO_MODEL_PATH = os.path.join(YOLOV5_DIR, "runs", "train", "exp4", "weights", "best.pt")
HAND_MODEL_PATH = os.path.join(YOLOV5_DIR, "hand_landmarker.task")

DISTANCE_THRESHOLD = 300   # px — スマホと手がこれより近ければ「使用中」
CONF_THRESHOLD     = 0.35  # この信頼度未満のphoneは検出しない
PHONE_CONFIRM_FRAMES = 10  # このフレーム数続けて近ければ使用中と確定

HAND_LANDMARKS = [0, 4, 8]  # 手首、親指先、人差し指先


class PhoneMonitor:
    def __init__(self):
        self.model = torch.hub.load(YOLOV5_DIR, "custom", path=YOLO_MODEL_PATH, source="local")
        self.model.conf = CONF_THRESHOLD

        options = vision.HandLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=HAND_MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_hands=2,
        )
        self.detector = vision.HandLandmarker.create_from_options(options)

        self._start_t = time.time()
        self._last_ts = -1
        self._phone_frames = 0
        self._using_phone  = False

    @staticmethod
    def _distance(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    def _detect_phone(self, frame):
        """YOLOでスマホを検出し、検出したすべての中心座標を返す（複数同時対応）"""
        results = self.model(frame)
        centers = []

        for *xyxy, conf, cls in results.xyxy[0]:
            if self.model.names[int(cls)] != "phone":
                continue

            x1, y1, x2, y2 = map(int, xyxy)
            centers.append(((x1 + x2) // 2, (y1 + y2) // 2))

            cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            cv2.putText(frame, f"phone {float(conf):.2f}", (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

        return centers

    def _detect_hands(self, frame):
        """MediaPipeで手を検出し、判定に使う点の座標一覧を返す"""
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # detect_for_video は単調増加するタイムスタンプを要求する
        timestamp_ms = int((time.time() - self._start_t) * 1000)
        if timestamp_ms <= self._last_ts:
            timestamp_ms = self._last_ts + 1
        self._last_ts = timestamp_ms

        result = self.detector.detect_for_video(mp_image, timestamp_ms)

        hand_points = []
        for hand_landmarks in result.hand_landmarks:
            for idx in HAND_LANDMARKS:
                lm = hand_landmarks[idx]
                px, py = int(lm.x * w), int(lm.y * h)
                hand_points.append((px, py))
                cv2.circle(frame, (px, py), 6, (0, 255, 0), -1)

        return hand_points

    def process(self, frame):
        phone_centers = self._detect_phone(frame)
        hand_points   = self._detect_hands(frame)

        status = "No Phone"
        color  = (0, 255, 0)

        if phone_centers and hand_points:
            # 複数のスマホ×複数の手の全組み合わせで最も近い距離を見る
            min_distance = min(
                self._distance(c, p) for c in phone_centers for p in hand_points
            )
            near = min_distance < DISTANCE_THRESHOLD
        else:
            # スマホか手のどちらかが写っていなければ使用中とはみなさない
            near = False

        if near:
            self._phone_frames += 1
        else:
            self._phone_frames = 0
            self._using_phone  = False

        if self._phone_frames >= PHONE_CONFIRM_FRAMES:
            self._using_phone = True

        if self._using_phone:
            status = "Phone Use"
            color  = (0, 0, 255)

        # 4th value = このフレームの生の検知信号（STATUS表示用）。
        # using_phone は確定後にTrue、near は検知した瞬間から毎フレームTrueになる。
        return status, color, self._using_phone, near

    def close(self):
        self.detector.close()
