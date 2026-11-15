import time


class DetectManager:

    def __init__(self):
        self.targets = [
            {"key": "sleep", "idx": 0},
            {"key": "phone", "idx": 1},
            {"key": "posture", "idx": 2},
        ]

        self.state = [
            {"sleep": {"start_time": None, "last_seen": 0}},
            {"phone": {"start_time": None, "last_seen": 0}},
            {"posture": {"start_time": None, "last_seen": 0}}
        ]

    def detect_manager(self, detects):
        ten_detect = [False, False, False] # 10秒検知でTrue
        thirty_detect = [False, False, False] # 30秒検知でTrue
        current_time = int(time.time())

        for target in self.targets:
            key = target["key"]
            idx = target["idx"]
            data = self.state[idx][key]

            if key in detects:
                data["last_seen"] = current_time
                if data["start_time"] is None:
                    data["start_time"] = current_time

            if current_time - data["last_seen"] > 2.0:
                data["start_time"] = None

            if data["start_time"] is not None:
                duration = current_time - data["start_time"]
                print(f"{key}の検知時間: {duration}秒")
                if duration > 5:
                    ten_detect[idx] = True
                if duration > 15:
                    thirty_detect[idx] = True

        return ten_detect, thirty_detect