import cv2
import mediapipe as mp
import math
import time
import os
from collections import deque

from mediapipe.tasks.python import vision
from mediapipe.tasks.python import BaseOptions

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models", "pose_landmarker.task")

LEFT_EAR = 7
LEFT_SHOULDER = 11
LEFT_HIP = 23
LEFT_WRIST = 15
RIGHT_WRIST = 16

# 値を大きくするほど「大きく傾かないと悪い姿勢と判定しない」＝検知が弱くなる
NECK_ANGLE_LIMIT    = 30
TORSO_ANGLE_LIMIT   = 30

# --- 居眠り(SLEEP)検知の感度設定 ---
# gap も hand も胴の長さ(肩〜腰)で正規化しているので、カメラからの距離に依存しない。
# どちらも「値を大きくするほど検知しやすい（緩い）」。まず DEBUG_SLEEP=True で
# 実際の gap_ratio / hand_ratio を見ながら調整するのがおすすめ。
NAP_GAP_RATIO   = 0.25   # 耳が肩に近い（首が前/横に折れている）: gap_ratio がこの値未満で検知
NAP_HAND_RATIO  = 0.55   # 手が耳に近い（頬杖・目こすりなど）: hand_ratio がこの値未満で検知
NAP_CONFIRM_FRAMES = 30
DEBUG_SLEEP     = False   # True にすると毎フレーム gap_ratio / hand_ratio をコンソール表示

SMOOTH_WINDOW       = 10   # frames to average angles over


class PostureMonitor:
    def __init__(self):
        options = vision.PoseLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=MODEL_PATH),
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
        )
        self.landmarker = vision.PoseLandmarker.create_from_options(options)
        self._start_t   = time.time()
        self._last_ts   = -1
        self._nap_frames = 0
        self._napping   = False

        # Rolling buffers for smoothing — one per measurement
        self._neck_buf  = deque(maxlen=SMOOTH_WINDOW)
        self._torso_buf = deque(maxlen=SMOOTH_WINDOW)
        self._gap_buf   = deque(maxlen=SMOOTH_WINDOW)
        self._hand_buf  = deque(maxlen=SMOOTH_WINDOW)

    @staticmethod
    def _angle_from_vertical(x1, y1, x2, y2):
        dx = x2 - x1
        dy = y1 - y2
        return math.degrees(math.atan2(abs(dx), abs(dy)))

    @staticmethod
    def _distance(p1, p2):
        return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

    @staticmethod
    def _smooth(buf):
        return sum(buf) / len(buf)

    def _clear_buffers(self):
        self._neck_buf.clear()
        self._torso_buf.clear()
        self._gap_buf.clear()
        self._hand_buf.clear()

    def process(self, frame):
        h, w, _ = frame.shape
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        # detect_for_video requires strictly increasing timestamps
        timestamp_ms = int((time.time() - self._start_t) * 1000)
        if timestamp_ms <= self._last_ts:
            timestamp_ms = self._last_ts + 1
        self._last_ts = timestamp_ms

        result = self.landmarker.detect_for_video(mp_image, timestamp_ms)

        status = "Good Posture"
        color  = (0, 255, 0)
        bad_posture = False

        if not result.pose_landmarks:
            # Nobody in frame: drop stale samples so the next person starts clean
            self._clear_buffers()
            self._nap_frames = 0
            self._napping    = False
            # 5th value = このフレームの生の居眠り信号（STATUS表示用）
            return status, color, self._napping, bad_posture, False

        lm = result.pose_landmarks[0]

        shoulder = (lm[LEFT_SHOULDER].x * w, lm[LEFT_SHOULDER].y * h)
        ear      = (lm[LEFT_EAR].x * w,      lm[LEFT_EAR].y * h)
        hip      = (lm[LEFT_HIP].x * w,      lm[LEFT_HIP].y * h)
        l_wrist  = (lm[LEFT_WRIST].x * w,    lm[LEFT_WRIST].y * h)
        r_wrist  = (lm[RIGHT_WRIST].x * w,   lm[RIGHT_WRIST].y * h)

        # 胴の長さ(肩〜腰)を基準スケールに使い、距離非依存にする
        torso_len = self._distance(shoulder, hip)
        if torso_len < 1.0:
            torso_len = 1.0

        # Push raw values into buffers and read smoothed averages
        self._neck_buf.append(self._angle_from_vertical(shoulder[0], shoulder[1], ear[0], ear[1]))
        self._torso_buf.append(self._angle_from_vertical(hip[0], hip[1], shoulder[0], shoulder[1]))
        # gap_ratio: 耳が肩に近づくほど小さくなる（正規化済み）
        self._gap_buf.append((shoulder[1] - ear[1]) / torso_len)

        # Use the closer of the two wrists to the ear（正規化済み）
        hand_ear_dist = min(self._distance(l_wrist, ear), self._distance(r_wrist, ear))
        self._hand_buf.append(hand_ear_dist / torso_len)

        neck_angle  = self._smooth(self._neck_buf)
        torso_angle = self._smooth(self._torso_buf)
        gap_ratio   = self._smooth(self._gap_buf)
        hand_ratio  = self._smooth(self._hand_buf)

        # Nap signal: ear near shoulder OR hand raised close to ear
        nap_signal = gap_ratio < NAP_GAP_RATIO or hand_ratio < NAP_HAND_RATIO

        if DEBUG_SLEEP:
            print(f"[sleep] gap_ratio={gap_ratio:.2f} hand_ratio={hand_ratio:.2f} signal={nap_signal}")

        if nap_signal:
            self._nap_frames += 1
        else:
            self._nap_frames = 0
            self._napping    = False

        if self._nap_frames >= NAP_CONFIRM_FRAMES:
            self._napping = True

        # Posture check
        if neck_angle > NECK_ANGLE_LIMIT or torso_angle > TORSO_ANGLE_LIMIT:
            status = "Bad Posture"
            color  = (0, 0, 255)
            bad_posture = True

        # 5th value = このフレームの生の居眠り信号（STATUS表示用）。
        # napping は確定後にTrue、nap_signal は検知した瞬間から毎フレームTrueになる。
        return status, color, self._napping, bad_posture, nap_signal

    def close(self):
        self.landmarker.close()
