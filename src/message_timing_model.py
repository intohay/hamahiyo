import json
import os
import random
from datetime import datetime, timedelta, timezone
from typing import List


class MessageTimingModel:
    """
    濱岸ひよりのメッセージ送信パターンを分析結果に基づいてモデル化するクラス
    """

    def __init__(self, analysis_file_path: str = None):
        """分析結果をロードして初期化"""
        if analysis_file_path is None:
            # srcディレクトリから見て上位ディレクトリのjsonファイルを参照
            analysis_file_path = os.path.join(
                os.path.dirname(__file__), "..", "message_timing_analysis.json"
            )

        with open(analysis_file_path, "r", encoding="utf-8") as f:
            self.analysis_data = json.load(f)

        # 基本統計
        self.mean_hours = self.analysis_data["mean_hours"]
        self.std_hours = self.analysis_data["std_hours"]
        self.median_hours = self.analysis_data["median_hours"]

        # 活動時間帯（11時-20時がメイン）
        self.active_hours = self.analysis_data["active_hours"]

        # 時間別分布（重み付け用）
        self.hourly_distribution = self.analysis_data["hourly_distribution"]

        # ガンマ分布パラメータ
        self.gamma_shape = self.analysis_data["gamma_shape"]
        self.gamma_scale = self.analysis_data["gamma_scale"]

        # 正規化された時間別重み
        self._setup_hourly_weights()

    def _setup_hourly_weights(self):
        """時間別の投稿確率重みを設定"""
        total_messages = sum(self.hourly_distribution.values())
        self.hourly_weights = {}

        for hour in range(24):
            hour_key = str(float(hour))
            count = self.hourly_distribution.get(hour_key, 0)
            # 基本重み + 活動時間ボーナス
            weight = count / total_messages
            if hour in self.active_hours:
                weight *= 2.0  # 活動時間帯は2倍の重み
            self.hourly_weights[hour] = weight

    def _gamma_sample(self, shape, scale):
        """ガンマ分布の簡単な近似サンプリング"""
        # ガンマ分布の近似：指数分布の和を使用
        if shape < 1:
            # shapeが小さい場合の近似
            return random.expovariate(1 / scale) * shape
        else:
            # Marsaglia and Tsang's method の簡単版
            samples = []
            for _ in range(int(shape)):
                samples.append(random.expovariate(1 / scale))
            return sum(samples) + random.expovariate(1 / scale) * (shape - int(shape))

    def should_post_at_hour(self, hour: int) -> bool:
        """指定時間に投稿すべきかを確率的に判定"""
        if hour < 6 or hour > 23:  # 深夜早朝は投稿しない
            return False

        weight = self.hourly_weights.get(hour, 0)
        # 活動時間帯は高確率、それ以外は低確率
        threshold = 0.3 if hour in self.active_hours else 0.1
        return random.random() < weight * threshold

    def get_next_interval_hours(self, current_hour: int) -> float:
        """
        次の投稿までの間隔を時間単位で取得
        時間帯と実データ分析に基づいて調整
        """

        # 連続投稿の可能性（中央値が1分なので）
        if random.random() < 0.15:  # 15%の確率で連続投稿
            return random.uniform(0.02, 0.5)  # 1分-30分

        # 活動時間帯かどうかで間隔を調整
        if current_hour in self.active_hours:
            # 活動時間帯：短い間隔でより頻繁に投稿
            base_interval = self._gamma_sample(self.gamma_shape, self.gamma_scale * 0.5)
        else:
            # 非活動時間帯：長い間隔
            base_interval = self._gamma_sample(self.gamma_shape, self.gamma_scale * 1.5)

        # 異常に長い間隔を制限（最大48時間）
        return min(base_interval, 48.0)

    def get_next_post_time(self, last_post_time: datetime = None) -> datetime:
        """
        次の投稿時刻を計算
        """
        if last_post_time is None:
            last_post_time = datetime.now(timezone(timedelta(hours=9)))

        current_hour = last_post_time.hour
        interval_hours = self.get_next_interval_hours(current_hour)
        next_time = last_post_time + timedelta(hours=interval_hours)

        # 深夜早朝を避ける調整
        if next_time.hour < 6:
            # 朝7時以降に調整
            next_time = next_time.replace(hour=7, minute=random.randint(0, 59))
        elif next_time.hour > 23:
            # 翌日の朝に調整
            next_time = (next_time + timedelta(days=1)).replace(
                hour=random.randint(7, 11), minute=random.randint(0, 59)
            )

        return next_time

    def is_burst_mode_time(self, current_time: datetime) -> bool:
        """
        バースト投稿（連続投稿）モードの時間かどうか判定
        """
        hour = current_time.hour
        # 活動時間帯の中でも特に投稿が多い時間（12-19時）
        peak_hours = [12, 13, 14, 15, 16, 17, 18, 19]
        return hour in peak_hours and random.random() < 0.2

    def get_burst_intervals(self) -> List[float]:
        """
        バースト投稿の間隔リストを生成（分単位）
        """
        num_posts = random.randint(2, 5)  # 2-5連続投稿
        intervals = []
        for _ in range(num_posts - 1):
            # 1分-10分の間隔
            intervals.append(random.uniform(1, 10))
        return intervals

    def print_model_info(self):
        """モデル情報を表示"""
        print("=== メッセージタイミングモデル情報 ===")
        print(f"平均間隔: {self.mean_hours:.2f}時間")
        print(f"標準偏差: {self.std_hours:.2f}時間")
        print(f"中央値: {self.median_hours:.2f}時間")
        print(f"活動時間帯: {self.active_hours}")
        print(
            f"ガンマ分布パラメータ: shape={self.gamma_shape:.3f}, scale={self.gamma_scale:.3f}"
        )

        print("\n時間別投稿重み:")
        for hour in range(24):
            weight = self.hourly_weights[hour]
            if weight > 0.01:  # 1%以上の重みがある時間のみ表示
                print(f"  {hour:02d}時: {weight:.3f}")
