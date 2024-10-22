import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from statsmodels.stats.inter_rater import fleiss_kappa

plt.rcParams['font.family'] = 'Hiragino Sans'
result_df = pd.read_csv('data/questionnaire.csv')

# 最後のコラムを削除
result_df = result_df.iloc[:, :-1]

model_df = pd.read_csv('data/merged_hamahiyo.csv')
# add index
model_df["id"] = model_df.index

model_df["id_plus_1"]  = model_df["id"] + 1

# model カラムがoldのものを抽出
old_model_df = model_df[model_df['model'] == 'old']

# model カラムがnewのものを抽出
new_model_df = model_df[model_df['model'] == 'new']

filtered_columns_old = [col for col in result_df.columns if any(f"Q{str(id_plus_1)} " in col for id_plus_1 in old_model_df['id_plus_1'])]
filtered_columns_new = [col for col in result_df.columns if any(f"Q{str(id_plus_1)} " in col for id_plus_1 in new_model_df['id_plus_1'])]

old_model_result_df = result_df[filtered_columns_old]
new_model_result_df = result_df[filtered_columns_new]

print(old_model_result_df.head())
print(new_model_result_df.head())

grammar = "文法の正しさ"
fluency = "流暢さ"
truth = "真実さ"
hiyotan = "ひよたんらしさ"

categories = [grammar, fluency, truth, hiyotan]

# 各モデルに対して、各カテゴリの平均と標準誤差を計算
def calculate_mean_se(df, category):
    cols = [col for col in df.columns if category in col]
    mean = df[cols].mean().mean()
    se = df[cols].std().mean() / np.sqrt(len(df))
    return mean, se

old_model_stats = {category: calculate_mean_se(old_model_result_df, category) for category in categories}
new_model_stats = {category: calculate_mean_se(new_model_result_df, category) for category in categories}

# サンプル数を取得
sample_size_old = len(old_model_result_df)
sample_size_new = len(new_model_result_df)

# 結果を棒グラフで表示
labels = categories
old_means = [old_model_stats[cat][0] for cat in categories]
old_se = [old_model_stats[cat][1] for cat in categories]
new_means = [new_model_stats[cat][0] for cat in categories]
new_se = [new_model_stats[cat][1] for cat in categories]

x = np.arange(len(labels))
width = 0.35

fig, ax = plt.subplots()
rects1 = ax.bar(x - width/2, old_means, width, label=f'旧ハマヒヨちゃん (japanese-gpt2-small)', yerr=old_se, capsize=5)
rects2 = ax.bar(x + width/2, new_means, width, label=f'新ハマヒヨちゃん (Llama-3.1-Swallow-8B-Q4_K_M)', yerr=new_se, capsize=5)

ax.set_ylabel('スコア')
ax.set_title('評価項目ごとのモデル比較 (平均 ± 標準誤差)')
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.legend(fontsize='small')


# plt.show()
# save the plot
plt.savefig('data/model_comparison.png')

# Timestamp列を削除
result_df = result_df.drop(columns=['Timestamp'])

# Fleiss' Kappaを計算するためにデータを準備する関数
def prepare_data_for_fleiss_kappa(df):
    # 評価データを3段階に簡略化（1-2: 低評価, 3: 中評価, 4-5: 高評価）
    simplified_df = df.apply(lambda x: x.map(lambda v: 1 if v in [1, 2] else (2 if v == 3 else 3)))
    
    # 評価者ごとに各スコアのカウントを計算
    fleiss_data = []
    for col in simplified_df.columns:
        counts = simplified_df[col].value_counts().reindex(range(1, 4), fill_value=0)  # 評価スコアが1-3であると仮定
        fleiss_data.append(counts.values)
    
    return np.array(fleiss_data)

# 各評価項目ごとにFleiss' Kappaを計算
categories = ["文法の正しさ", "流暢さ", "真実さ", "ひよたんらしさ"]
kappas = []

for category in categories:
    combined_model_data = prepare_data_for_fleiss_kappa(result_df.filter(like=category))
    kappa = fleiss_kappa(combined_model_data, method='fleiss')
    kappas.append(kappa)
    print(f"Fleiss' Kappa for {category}: {kappa:.3f}")

# 全体での一致度を計算
overall_data = prepare_data_for_fleiss_kappa(result_df)
overall_kappa = fleiss_kappa(overall_data, method='fleiss')
print(f"Overall Fleiss' Kappa: {overall_kappa:.3f}")
