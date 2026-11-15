# Focus Monitor（サボり監視 AI）

デスクワーク中のサボりをカメラで見張るプログラムです。居眠り・スマホ・悪い姿勢を見つけると AI が声で注意し、サボりが続くと「AI 裁判」が始まります。

## できること

- **3種類のサボりを検知**：カメラの映像から次の3つを見つけます。
  - 居眠り（首が前や横に折れている、手が耳の近くにある）
  - スマホの使用（スマホと手が近い）
  - 悪い姿勢（首や背中が傾いている）
- **声で注意**：サボりが5秒を超えると注意し、15秒を超えるとさらに強く注意します。
- **怒りゲージ**：注意するたびにゲージがたまります（5秒で +5、15秒で +15）。
- **AI 裁判**：ゲージが100になると裁判が始まり、弁護士・検察官・裁判官の AI が順に話します。終わるとゲージは0に戻ります。
- **消灯**：居眠りが15秒を超えるとライトを消し、3秒後にプログラムを終了します。

注意や裁判のセリフは Gemini で作り、VOICEVOX で読み上げます。

## 準備

Windows で動きます（音声の再生に `winsound` を使うため）。

1. ライブラリを入れます。YOLOv5 の実行に必要なライブラリは `ultralytics` と一緒に入ります。

   ```powershell
   python -m pip install opencv-python mediapipe ultralytics google-genai python-dotenv requests
   ```

2. [VOICEVOX](https://voicevox.hiroshiba.jp/) を起動します。初期値では `http://127.0.0.1:50021` につなぎます。
3. このフォルダに `.env` を作り、Gemini の API キーを書きます。

   ```text
   GEMINI_API_KEY=ここにAPIキー
   # VOICEVOX が別の場所にあるとき
   # VOICEVOX_URL=http://127.0.0.1:50021
   ```

セリフは `sentence_cache.json` に保存してあるので、このファイルがあれば Gemini には送信しません。作り直すときはこのファイルを消してから起動します。

## 実行

```powershell
python main.py
```

カメラ（ID 0）の映像に、検知の状態と怒りゲージを重ねたウィンドウが開きます。`q` キーで終了します。

## 画面

| 場所 | 表示 |
|---|---|
| 左上 | タイトル（FOCUS MONITOR） |
| 左下 | STATUS：POSTURE（姿勢）、DROWSINESS（居眠り）、PHONE（スマホ）の OK／ALERT |
| 右下 | ANGER：怒りゲージ（緑 → 橙 → 赤） |
| 上部中央 | 裁判中は「COURT IN SESSION」、消灯時は「LIGHT OFF」 |

## 仕組み

```text
カメラ ┬→ 姿勢推定（MediaPipe Pose）→ 居眠り・姿勢の判定 ┐
       └→ スマホ検出（YOLOv5）＋手の検出（MediaPipe Hand）→ スマホの判定 ┤
                                                                         ↓
                    続いた時間を計測 → 注意の読み上げ・怒りゲージ → AI 裁判／消灯
```

起動時に、全部のセリフの音声を VOICEVOX で先に作っておきます。本番では待たずにすぐ読み上げられます。

| ファイル | 役割 |
|---|---|
| `main.py` | カメラの読み込み、全体の流れ、終了処理 |
| `posture_monitor.py` | 姿勢推定から居眠りと悪い姿勢を判定 |
| `phone_monitor.py` | スマホと手の位置から、スマホの使用を判定 |
| `detect_manager.py` | サボりが続いた時間を計測（2秒途切れたら数え直す） |
| `gauge_manager.py` | 注意の読み上げ、怒りゲージ、消灯の指示 |
| `judgement.py` | AI 裁判の進行 |
| `sentence_create.py` | Gemini でセリフを作り、`sentence_cache.json` に保存 |
| `voice_play.py` | VOICEVOX で音声を作って再生 |
| `light_control.py` | ライトの消灯（SwitchBot API） |
| `ui.py` | 画面の表示（HUD） |
| `env_loader.py` | `.env` の読み込み |
| `models/pose_landmarker.task` | 姿勢推定のモデル |
| `yolov5-master/` | YOLOv5 の本体、スマホ検出の学習済みモデル（`runs/train/exp4/weights/best.pt`）、手の検出のモデル |

### 調整する場所

- 姿勢の判定の厳しさ：`posture_monitor.py` の `NECK_ANGLE_LIMIT`、`TORSO_ANGLE_LIMIT`
- 居眠りの判定の厳しさ：`posture_monitor.py` の `NAP_GAP_RATIO`、`NAP_HAND_RATIO`（`DEBUG_SLEEP = True` で実際の値を表示）
- スマホの判定：`phone_monitor.py` の `DISTANCE_THRESHOLD`（スマホと手の距離）、`CONF_THRESHOLD`（検出の信頼度）
- 注意するまでの時間：`detect_manager.py` の `duration > 5`、`duration > 15`
- 裁判が始まるゲージの値：`gauge_manager.py` の `TRIAL_THRESHOLD`

## 今後の課題

- 本物のライトを消す処理（SwitchBot API）はコメントアウトしてあり、今は画面に「LIGHT OFF」を出すだけです。使うときは `.env` に `SWITCHBOT_TOKEN` と `SWITCHBOT_SECRET` を書き、`light_control.py` のコメントを外します。
- コード内の名前は「10秒」「30秒」（`ten_detect`、`thirty_detect` など）ですが、実際は5秒と15秒で判定しています。
