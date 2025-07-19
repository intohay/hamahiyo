import warnings

import numpy as np
import pandas as pd
import pytz
# ガンマ分布でフィッティング
from scipy import stats

warnings.filterwarnings("ignore")

# CSVファイルを読み込み
df = pd.read_csv("濱岸ひより.csv")

# published_atをdatetimeに変換（UTC）
df["published_at"] = pd.to_datetime(df["published_at"])

# 日本時間に変換
jst = pytz.timezone("Asia/Tokyo")
df["published_at_jst"] = df["published_at"].dt.tz_convert(jst)

# テキストメッセージのみを抽出（画像や動画を除外）
text_messages = df[df["text"].notna() & (df["text"] != "")].copy()

# 時系列順にソート
text_messages = text_messages.sort_values("published_at_jst").reset_index(drop=True)

print(f"総メッセージ数: {len(df)}")
print(f"テキストメッセージ数: {len(text_messages)}")
print(
    f"期間: {text_messages['published_at_jst'].min()} - {text_messages['published_at_jst'].max()}"
)

# NaNチェック
nan_count = text_messages["published_at_jst"].isna().sum()
print(f"NaN timestamp count: {nan_count}")

# 先頭数行を確認
print("\n先頭5行のタイムスタンプ:")
for i in range(min(5, len(text_messages))):
    print(f"  {i}: {text_messages.iloc[i]['published_at_jst']}")

# メッセージ間隔を計算（秒単位）
intervals = []
for i in range(1, len(text_messages)):
    current_time = text_messages.iloc[i]["published_at_jst"]
    previous_time = text_messages.iloc[i - 1]["published_at_jst"]
    if pd.notna(current_time) and pd.notna(previous_time):
        interval = (current_time - previous_time).total_seconds()
        if interval > 0:  # 正の値のみ
            intervals.append(interval)

intervals = np.array(intervals)
print(f"有効な間隔データ数: {len(intervals)}")

if len(intervals) == 0:
    print("有効な間隔データがありません。データを確認してください。")
    exit()

# 時間単位に変換
intervals_hours = intervals / 3600

# 基本統計
print("\n=== メッセージ間隔の統計 ===")
print(f"平均間隔: {np.mean(intervals_hours):.2f} 時間")
print(f"中央値: {np.median(intervals_hours):.2f} 時間")
print(f"標準偏差: {np.std(intervals_hours):.2f} 時間")
print(f"最小間隔: {np.min(intervals_hours):.2f} 時間")
print(f"最大間隔: {np.max(intervals_hours):.2f} 時間")

# 時間帯別の分析
text_messages["hour"] = text_messages["published_at_jst"].dt.hour
text_messages["day_of_week"] = text_messages["published_at_jst"].dt.day_name()

# 時間帯別メッセージ数
hourly_counts = text_messages["hour"].value_counts().sort_index()
print("\n=== 時間帯別メッセージ数 ===")
for hour, count in hourly_counts.items():
    print(f"{int(hour):02d}時台: {count} 件")

# 曜日別メッセージ数
weekly_counts = text_messages["day_of_week"].value_counts()
print("\n=== 曜日別メッセージ数 ===")
days_order = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]
for day in days_order:
    if day in weekly_counts:
        print(f"{day}: {weekly_counts[day]} 件")

# 異常な間隔を除外（1週間以上空いたものは除外）
normal_intervals = intervals_hours[intervals_hours <= 168]  # 168時間 = 1週間

print("\n=== 正常な間隔（1週間以内）の統計 ===")
print(f"データ数: {len(normal_intervals)}")
print(f"平均間隔: {np.mean(normal_intervals):.2f} 時間")
print(f"中央値: {np.median(normal_intervals):.2f} 時間")
print(f"標準偏差: {np.std(normal_intervals):.2f} 時間")

# パーセンタイル
percentiles = [25, 50, 75, 90, 95, 99]
print("\n=== パーセンタイル ===")
for p in percentiles:
    value = np.percentile(normal_intervals, p)
    print(f"{p}%: {value:.2f} 時間")



# ガンマ分布のパラメータを推定
shape, loc, scale = stats.gamma.fit(normal_intervals)
print("\n=== ガンマ分布パラメータ ===")
print(f"shape (α): {shape:.3f}")
print(f"scale (β): {scale:.3f}")
print(f"location: {loc:.3f}")

# 対数正規分布でもフィッティング
log_shape, log_loc, log_scale = stats.lognorm.fit(normal_intervals)
print("\n=== 対数正規分布パラメータ ===")
print(f"s (σ): {log_shape:.3f}")
print(f"scale (exp(μ)): {log_scale:.3f}")
print(f"location: {log_loc:.3f}")

# 指数分布でもフィッティング
exp_loc, exp_scale = stats.expon.fit(normal_intervals)
print("\n=== 指数分布パラメータ ===")
print(f"scale (λ): {exp_scale:.3f}")
print(f"location: {exp_loc:.3f}")

# モデルの適合度をKS検定で評価
gamma_ks = stats.kstest(
    normal_intervals, lambda x: stats.gamma.cdf(x, shape, loc, scale)
)
lognorm_ks = stats.kstest(
    normal_intervals, lambda x: stats.lognorm.cdf(x, log_shape, log_loc, log_scale)
)
expon_ks = stats.kstest(
    normal_intervals, lambda x: stats.expon.cdf(x, exp_loc, exp_scale)
)

print("\n=== KS検定結果（p値が大きいほど良い適合） ===")
print(f"ガンマ分布: p-value = {gamma_ks.pvalue:.4f}")
print(f"対数正規分布: p-value = {lognorm_ks.pvalue:.4f}")
print(f"指数分布: p-value = {expon_ks.pvalue:.4f}")

# 活動時間の分析（メッセージが多い時間帯）
active_hours = hourly_counts[hourly_counts > hourly_counts.quantile(0.5)].index.tolist()
print("\n=== 活動的な時間帯 ===")
print(f"活動的な時間帯: {sorted(active_hours)}")

# 結果をファイルに保存
results = {
    "mean_hours": float(np.mean(normal_intervals)),
    "std_hours": float(np.std(normal_intervals)),
    "median_hours": float(np.median(normal_intervals)),
    "gamma_shape": float(shape),
    "gamma_scale": float(scale),
    "gamma_loc": float(loc),
    "lognorm_s": float(log_shape),
    "lognorm_scale": float(log_scale),
    "lognorm_loc": float(log_loc),
    "expon_scale": float(exp_scale),
    "expon_loc": float(exp_loc),
    "active_hours": active_hours,
    "hourly_distribution": hourly_counts.to_dict(),
}

import json

with open("message_timing_analysis.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

print("\n分析結果を message_timing_analysis.json に保存しました。")
