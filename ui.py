"""洗練されたモニタリングHUDの描画。検知ロジックからは独立している。"""
import time

import cv2
import numpy as np

FONT = cv2.FONT_HERSHEY_SIMPLEX

# --- カラーパレット (BGR) ---
COL_PANEL   = (28, 24, 20)      # 半透明パネルの下地（濃紺グレー）
COL_TEXT    = (240, 240, 240)   # 主テキスト
COL_MUTED   = (150, 150, 150)   # 補助テキスト
COL_OK      = (120, 200, 110)   # 正常（緑）
COL_ALERT   = (70, 70, 235)     # 警告（赤）
COL_TRACK   = (60, 55, 50)      # ゲージの溝

# ゲージのグラデーション用ストップ (緑 → 橙 → 赤)
_GAUGE_STOPS = [(110, 200, 120), (60, 180, 245), (70, 70, 235)]


def _lerp(c1, c2, t):
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

light_off = False
def set_light_off():
    global light_off
    light_off = True
    time.sleep(5)
    light_off = False

def _gauge_color(ratio):
    ratio = max(0.0, min(1.0, ratio))
    if ratio < 0.5:
        return _lerp(_GAUGE_STOPS[0], _GAUGE_STOPS[1], ratio / 0.5)
    return _lerp(_GAUGE_STOPS[1], _GAUGE_STOPS[2], (ratio - 0.5) / 0.5)


def _rounded_rect(img, x1, y1, x2, y2, r, color, thickness=-1):
    r = min(r, (x2 - x1) // 2, (y2 - y1) // 2)
    if thickness < 0:
        cv2.rectangle(img, (x1 + r, y1), (x2 - r, y2), color, -1)
        cv2.rectangle(img, (x1, y1 + r), (x2, y2 - r), color, -1)
        for cx, cy in ((x1 + r, y1 + r), (x2 - r, y1 + r), (x1 + r, y2 - r), (x2 - r, y2 - r)):
            cv2.circle(img, (cx, cy), r, color, -1, cv2.LINE_AA)
    else:
        cv2.ellipse(img, (x1 + r, y1 + r), (r, r), 180, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - r, y1 + r), (r, r), 270, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x1 + r, y2 - r), (r, r), 90, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.ellipse(img, (x2 - r, y2 - r), (r, r), 0, 0, 90, color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1 + r, y1), (x2 - r, y1), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1 + r, y2), (x2 - r, y2), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x1, y1 + r), (x1, y2 - r), color, thickness, cv2.LINE_AA)
        cv2.line(img, (x2, y1 + r), (x2, y2 - r), color, thickness, cv2.LINE_AA)


def _panel(frame, x1, y1, x2, y2, r, color, alpha):
    """角丸の半透明パネルを frame に合成する。"""
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(frame.shape[1], x2), min(frame.shape[0], y2)
    overlay = frame.copy()
    _rounded_rect(overlay, x1, y1, x2, y2, r, color, -1)
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)


def _text(frame, s, org, scale, color, thickness=1, shadow=True):
    if shadow:
        cv2.putText(frame, s, (org[0] + 1, org[1] + 1), FONT, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
    cv2.putText(frame, s, org, FONT, scale, color, thickness, cv2.LINE_AA)


def _text_right(frame, s, right_x, y, scale, color, thickness=1):
    (tw, _), _ = cv2.getTextSize(s, FONT, scale, thickness)
    _text(frame, s, (right_x - tw, y), scale, color, thickness)


def _banner(frame, text):
    """画面上部中央に強調バナーを表示する。"""
    w = frame.shape[1]
    scale, thick = 0.7, 2
    (tw, th), _ = cv2.getTextSize(text, FONT, scale, thick)
    pad_x, pad_y = 24, 14
    cx = w // 2
    x1, x2 = cx - tw // 2 - pad_x, cx + tw // 2 + pad_x
    y1, y2 = 62, 62 + th + pad_y * 2
    _panel(frame, x1, y1, x2, y2, 18, (30, 20, 60), 0.7)
    _rounded_rect(frame, x1, y1, x2, y2, 18, COL_ALERT, 2)
    _text(frame, text, (cx - tw // 2, y1 + th + pad_y), scale, (90, 120, 255), thick)


def draw_hud(frame, statuses, gauge_value, gauge_max=100, judging=False):
    """
    statuses: [(label, is_alert), ...]  例: [("POSTURE", False), ("PHONE", True)]
    gauge_value: 現在の怒りゲージ値
    judging:     裁判中フラグ。True のときは上部にバナーを出す
    """
    h, w = frame.shape[:2]

    # --- ヘッダー（左上のタイトルピル） ---
    _panel(frame, 16, 14, 232, 48, 16, COL_PANEL, 0.55)
    cv2.circle(frame, (34, 31), 5, COL_OK, -1, cv2.LINE_AA)
    _text(frame, "FOCUS MONITOR", (48, 37), 0.6, COL_TEXT, 1)

    # --- ステータスカード（左下） ---
    row_h = 34
    card_x1, card_x2 = 16, 250
    card_y2 = h - 16
    card_y1 = card_y2 - (len(statuses) * row_h + 66)
    _panel(frame, card_x1, card_y1, card_x2, card_y2, 16, COL_PANEL, 0.55)

    _text(frame, "STATUS", (card_x1 + 18, card_y1 + 26), 0.5, COL_MUTED, 1)

    y = card_y1 + 40
    for label, is_alert in statuses:
        col = COL_ALERT if is_alert else COL_OK
        cy = y + row_h // 2
        # インジケータドット（警告時はリング付き）
        cv2.circle(frame, (card_x1 + 26, cy), 6, col, -1, cv2.LINE_AA)
        if is_alert:
            cv2.circle(frame, (card_x1 + 26, cy), 10, col, 1, cv2.LINE_AA)
        _text(frame, label, (card_x1 + 44, cy + 5), 0.52, COL_TEXT, 1)
        _text_right(frame, "ALERT" if is_alert else "OK",
                    card_x2 - 16, cy + 5, 0.5, col, 1)
        y += row_h

    # --- 怒りゲージ（右下） ---
    ratio = max(0.0, min(1.0, gauge_value / gauge_max))
    g_x1, g_x2 = w - 236, w - 16
    g_y2 = h - 16
    g_y1 = g_y2 - 58
    _panel(frame, g_x1, g_y1, g_x2, g_y2, 16, COL_PANEL, 0.55)

    _text(frame, "ANGER", (g_x1 + 18, g_y1 + 24), 0.5, COL_MUTED, 1)
    _text_right(frame, f"{int(gauge_value)}", g_x2 - 18, g_y1 + 24, 0.55, COL_TEXT, 1)

    bar_x1, bar_x2 = g_x1 + 18, g_x2 - 18
    bar_y1, bar_y2 = g_y1 + 34, g_y1 + 44
    _rounded_rect(frame, bar_x1, bar_y1, bar_x2, bar_y2, 5, COL_TRACK, -1)
    fill_x2 = bar_x1 + int((bar_x2 - bar_x1) * ratio)
    if fill_x2 > bar_x1 + 5:
        _rounded_rect(frame, bar_x1, bar_y1, fill_x2, bar_y2, 5, _gauge_color(ratio), -1)

    if judging:
        _banner(frame, "COURT IN SESSION")

    if light_off:
        _banner(frame, "LIGHT OFF")

    return frame
