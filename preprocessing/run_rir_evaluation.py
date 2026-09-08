"""
RIR Evaluation — Full range (ceiling effect) vs Near-failure zone
=====================================================================
So sánh trực diện 2 cách đánh giá RIR để làm rõ ceiling effect trong paper.

Usage:
    python run_rir_evaluation.py
"""

import os
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor

from iqr_filter import filter_outlier_trials
from n1_features import build_all_feature_sets
from eval_protocols import (
    run_loso,
    run_loso_near_failure,
    run_loso_near_failure_train_filtered,
    summary,
    compare_paired,
)

CSV_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "processed", "per_cycle_features.csv"
)
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "results")
TARGET_RIR = "RIR_clipped"
RF_KWARGS = {"n_estimators": 200, "max_depth": 10, "n_jobs": -1, "random_state": 42}
LR_KWARGS = {"alpha": 1.0}

# Lấy best feature set từ A1 (nhất quán với toàn bộ pipeline)
a1_path = os.path.join(RESULTS_DIR, "ablation_A1.csv")
a1_df = pd.read_csv(a1_path)
best_feat_name = a1_df.sort_values("rmse_mean").iloc[0]["config"]
print(f"Best feature set (từ A1): {best_feat_name}")

df_raw = pd.read_csv(CSV_PATH)
df_filtered = filter_outlier_trials(df_raw, min_reps=10, verbose=False)
feature_sets, df = build_all_feature_sets(df_filtered)
feat_cols = feature_sets[best_feat_name]

# Kiểm tra ceiling effect thực tế
pct_ceiling = (df[TARGET_RIR] >= 10).mean() * 100
print(f"% reps có RIR=10 (ceiling): {pct_ceiling:.1f}%\n")

models = {
    "LR": (Ridge, LR_KWARGS, True),
    "RF": (RandomForestRegressor, RF_KWARGS, False),
}

print("=" * 60)
print("FULL RANGE (toàn bộ RIR, bao gồm ceiling) — DỄ GÂY HIỂU LẦM")
print("=" * 60)
rows_full = []
for name, (cls, kw, scale) in models.items():
    print(f"  Đang chạy FULL RANGE: {name}...", flush=True)
    res = run_loso(
        cls, feat_cols, TARGET_RIR, df, model_kwargs=kw, model_needs_scale=scale
    )
    s = summary(res)
    s["model"] = name
    rows_full.append(s)
    print(
        f"  {name}: MAE={s['mae_mean']:.2f} reps, RMSE={s['rmse_mean']:.2f}, R²={s['r2_mean']:.3f}",
        flush=True,
    )
    pd.DataFrame(rows_full).to_csv(
        os.path.join(RESULTS_DIR, "rir_full_range.csv"), index=False
    )


print("\n" + "=" * 60)
print("NEAR-FAILURE ONLY (RIR<10) — CON SỐ NÊN DÙNG CHO PAPER")
print("=" * 60)

rows_a, rows_b, rows_c = [], [], []
paired_tests = {}

for name, (cls, kw, scale) in models.items():
    res_a = run_loso_near_failure(
        cls, feat_cols, TARGET_RIR, df, model_kwargs=kw, model_needs_scale=scale
    )
    res_b = run_loso_near_failure_train_filtered(
        cls,
        feat_cols,
        TARGET_RIR,
        df,
        model_kwargs=kw,
        model_needs_scale=scale,
        train_fcf_min=0.5,
    )
    res_c = run_loso_near_failure(
        cls,
        feat_cols,
        TARGET_RIR,
        df[df["FCF"] > 0.5],
        model_kwargs=kw,
        model_needs_scale=scale,
    )
    for label, res, rows in [
        ("A", res_a, rows_a),
        ("B", res_b, rows_b),
        ("C", res_c, rows_c),
    ]:
        s = summary(res)
        s["model"] = name
        rows.append(s)

        print(
            f"  {label} {name}: MAE={s['mae_mean']:.2f} reps, RMSE={s['rmse_mean']:.2f}, R²={s['r2_mean']:.3f}",
            flush=True,
        )

    print(f"\n  Paired tests: {name}: A vs B")
    paired_tests[f"{name}"] = compare_paired(
        res_a, res_b, f"A-{name} (train full)", f"B-{name} (train FCF>0.5)"
    )

pd.DataFrame(rows_a).to_csv(
    os.path.join(RESULTS_DIR, "rir_A_baseline.csv"), index=False
)
pd.DataFrame(rows_b).to_csv(
    os.path.join(RESULTS_DIR, "rir_B_train_filtered.csv"), index=False
)
pd.DataFrame(rows_c).to_csv(
    os.path.join(RESULTS_DIR, "rir_C_both_filtered.csv"), index=False
)


# ══════════════════════════════════════════════════════════════════════════════
# SWEEP train_fcf_min — tìm ngưỡng tối ưu {0.3, 0.4, 0.5, 0.6}
# Mục tiêu: cô lập hiệu ứng "train sạch hơn" (cấu hình B) theo từng ngưỡng.
# Mỗi cấu hình: chỉ lọc TRAIN theo FCF > threshold, TEST giữ nguyên full near-failure.
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("SWEEP train_fcf_min: {0.3, 0.4, 0.5, 0.6}")
print("Cấu hình B — chỉ lọc TRAIN, TEST = full near-failure (RIR<10)")
print("=" * 60)

FCF_THRESHOLDS = [
    0.3,
    0.4,
    0.5,
    0.6,
    0.65,
    0.7,
]
sweep_rows = []

for fcf_min in FCF_THRESHOLDS:
    n_train_reps = (df["FCF"] > fcf_min).sum()
    print(
        f"\n  threshold={fcf_min}: giữ lại {n_train_reps}/{len(df)} train reps "
        f"({n_train_reps / len(df) * 100:.1f}%)"
    )
    for name, (cls, kw, scale) in models.items():
        res = run_loso_near_failure_train_filtered(
            cls,
            feat_cols,
            TARGET_RIR,
            df,
            model_kwargs=kw,
            model_needs_scale=scale,
            train_fcf_min=fcf_min,
        )
        s = summary(res)
        s["model"] = name
        s["train_fcf_min"] = fcf_min
        s["n_train_reps"] = n_train_reps
        sweep_rows.append(s)
        print(
            f"    {name}: MAE={s['mae_mean']:.2f} reps, "
            f"RMSE={s['rmse_mean']:.2f}, R²={s['r2_mean']:.3f}",
            flush=True,
        )

sweep_df = pd.DataFrame(sweep_rows)
sweep_path = os.path.join(RESULTS_DIR, "rir_sweep_fcf_threshold.csv")
sweep_df.to_csv(sweep_path, index=False)
print(f"\nSweep kết quả -> {sweep_path}")

# Tổng kết sweep: best threshold theo MAE cho từng model
print("\n  Tổng kết MAE theo threshold:")
pivot = sweep_df.pivot(index="train_fcf_min", columns="model", values="mae_mean")
print(pivot.to_string())


# ══════════════════════════════════════════════════════════════════════════════
# BLAND-ALTMAN thật — cấu hình (B) với best threshold từ sweep
# Dùng làm hình minh họa chính thay R² trong phần kết quả RIR.
# ══════════════════════════════════════════════════════════════════════════════
import sys

sys.path.insert(0, os.path.dirname(__file__))
from stats_utils import bland_altman_plot
import numpy as np

print("\n" + "=" * 60)
print("BLAND-ALTMAN — Cấu hình (B): train FCF>0.5, test near-failure")
print("=" * 60)

# Tìm best threshold từ sweep (RF, MAE thấp nhất)
sweep_rf = sweep_df[sweep_df["model"] == "RF"].sort_values("mae_mean")
best_thresh = sweep_rf.iloc[0]["train_fcf_min"]
print(f"  Best threshold (RF, MAE nhỏ nhất): {best_thresh}")

# Collect all actual vs predicted qua 13 fold cho RF cấu hình (B)
all_actual, all_pred = [], []
subjects = sorted(df["subject"].unique())

for test_subj in subjects:
    train_mask = (df["subject"] != test_subj) & (df["FCF"] > best_thresh)
    test_mask = (df["subject"] == test_subj) & (df[TARGET_RIR] < 10)

    if test_mask.sum() == 0:
        continue

    X_train = df.loc[train_mask, feat_cols].values
    y_train = df.loc[train_mask, TARGET_RIR].values
    X_test = df.loc[test_mask, feat_cols].values
    y_test = df.loc[test_mask, TARGET_RIR].values

    rf = RandomForestRegressor(**RF_KWARGS)
    rf.fit(X_train, y_train)
    y_pred = np.clip(rf.predict(X_test), 0, 10)

    all_actual.extend(y_test.tolist())
    all_pred.extend(y_pred.tolist())

all_actual = np.array(all_actual)
all_pred = np.array(all_pred)

# Bland-Altman plot
ba_path = os.path.join(RESULTS_DIR, "bland_altman_rir_B.png")
ba_stats = bland_altman_plot(
    all_actual,
    all_pred,
    title=f"Bland-Altman: RIR Near-Failure (B, train FCF>{best_thresh}, RF)",
    save_path=ba_path,
)
print(f"  Mean difference (bias): {ba_stats['mean_diff']:.3f} reps")
print(f"  SD of differences:      {ba_stats['std_diff']:.3f} reps")
print(f"  Upper LoA (+1.96 SD):   {ba_stats['upper_loa']:.3f} reps")
print(f"  Lower LoA (-1.96 SD):   {ba_stats['lower_loa']:.3f} reps")
print(f"  Plot saved -> {ba_path}")

# Lưu raw actual/pred cho paper nếu cần
ba_data_path = os.path.join(RESULTS_DIR, "bland_altman_rir_B_rawdata.csv")
pd.DataFrame({"actual": all_actual, "predicted": all_pred}).to_csv(
    ba_data_path, index=False
)
print(f"  Raw data saved -> {ba_data_path}")

print("\n" + "=" * 60)
print("RIR EVALUATION COMPLETE")
print(f"  rir_full_range.csv       : FULL RANGE (cap~10, gây hiểu lầm)")
print(f"  rir_A_baseline.csv       : Near-failure, train toàn bộ")
print(f"  rir_B_train_filtered.csv : Near-failure, train FCF>0.5")
print(f"  rir_C_both_filtered.csv  : Near-failure, cả train+test FCF>0.5")
print(f"  rir_sweep_fcf_threshold.csv : Sweep threshold {FCF_THRESHOLDS}")
print(f"  bland_altman_rir_B.png   : Hình Bland-Altman cho paper")
print("=" * 60)
