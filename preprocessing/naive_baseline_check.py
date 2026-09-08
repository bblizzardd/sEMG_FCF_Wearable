"""
Naive Baseline Check — phân biệt "model học tín hiệu" vs "distribution matching"
=====================================================================
Trả lời trực tiếp câu hỏi phản biện: MAE giảm khi tăng train_fcf_min có
phải chỉ vì train distribution co hẹp về gần test distribution, không
phải vì RF/LR học được tín hiệu cơ tốt hơn?

Hai phép kiểm tra:
  1. Naive mean predictor (DummyRegressor) chạy qua ĐÚNG pipeline LOSO
     train-filtered đã có — nếu naive gần bằng RF/LR thì kết quả không
     có giá trị khoa học.
  2. Distribution-shift table: mean/std của RIR_clipped trong train pool
     (sau lọc FCF>threshold) so với test pool (toàn bộ near-failure,
     không lọc) — càng gần nhau thì nghi ngờ distribution-matching càng
     có cơ sở.

Usage:
    python naive_baseline_check.py
"""

import os
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.dummy import DummyRegressor

from iqr_filter import filter_outlier_trials
from n1_features import build_all_feature_sets
from eval_protocols import (
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

FCF_MIN_SWEEP = [0.3, 0.4, 0.5, 0.6, 0.7]

a1_path = os.path.join(RESULTS_DIR, "ablation_A1.csv")
a1_df = pd.read_csv(a1_path)
best_feat_name = a1_df.sort_values("rmse_mean").iloc[0]["config"]
print(f"Best feature set (từ A1): {best_feat_name}")

df_raw = pd.read_csv(CSV_PATH)
df_filtered = filter_outlier_trials(df_raw, min_reps=10, verbose=False)
feature_sets, df = build_all_feature_sets(df_filtered)
feat_cols = feature_sets[best_feat_name]

# ---------------------------------------------------------------------
# Phần 1 — Naive mean predictor qua đúng pipeline LOSO train-filtered
# ---------------------------------------------------------------------
models = {
    "Naive_mean": (DummyRegressor, {"strategy": "mean"}, False),
    "LR": (Ridge, LR_KWARGS, True),
    "RF": (RandomForestRegressor, RF_KWARGS, False),
}

print("\n" + "=" * 70)
print("PHẦN 1 — Naive mean predictor vs LR/RF, qua các threshold train_fcf_min")
print("=" * 70)

rows = []
raw_results = {}  # (model_name, fcf_min) -> res, để chạy paired test RF vs Naive

for fcf_min in FCF_MIN_SWEEP:
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
        raw_results[(name, fcf_min)] = res
        s = summary(res)
        s["model"] = name
        s["train_fcf_min"] = fcf_min
        rows.append(s)
        print(
            f"  fcf_min={fcf_min} | {name:11s}: MAE={s['mae_mean']:.3f} reps, "
            f"RMSE={s['rmse_mean']:.3f}, R²={s['r2_mean']:.3f}",
            flush=True,
        )
    # so sánh nhanh trong cùng threshold: RF có vượt naive rõ rệt không?
    naive_mae = [
        r["mae_mean"]
        for r in rows
        if r["model"] == "Naive_mean" and r["train_fcf_min"] == fcf_min
    ][-1]
    rf_mae = [
        r["mae_mean"]
        for r in rows
        if r["model"] == "RF" and r["train_fcf_min"] == fcf_min
    ][-1]
    gap = naive_mae - rf_mae
    gap_pct = gap / naive_mae * 100 if naive_mae else float("nan")
    print(
        f"  --> RF cải thiện so với Naive: {gap:.3f} reps ({gap_pct:.1f}%)\n",
        flush=True,
    )

check_df = pd.DataFrame(rows)
check_df.to_csv(os.path.join(RESULTS_DIR, "rir_naive_baseline_check.csv"), index=False)

# ---------------------------------------------------------------------
# Phần 1b — Paired test cho GAP (RF vs Naive) tại mỗi threshold.
# Đây mới là đại lượng khoa học thật sự cần kiểm định — KHÔNG phải mức
# giảm MAE theo threshold (cái đó bị confound bởi distribution shift,
# xem Phần 2). Nếu gap này SIG và ổn định qua các threshold, đó là
# bằng chứng RF học được tín hiệu thật, độc lập với việc chọn threshold.
# ---------------------------------------------------------------------
print("=" * 70)
print("PHẦN 1b — Paired test: RF vs Naive_mean, TẠI TỪNG threshold")
print("(đại lượng cần báo cáo trong paper, không phải mức giảm theo threshold)")
print("=" * 70)
for fcf_min in FCF_MIN_SWEEP:
    compare_paired(
        raw_results[("RF", fcf_min)],
        raw_results[("Naive_mean", fcf_min)],
        f"RF (fcf_min={fcf_min})",
        f"Naive_mean (fcf_min={fcf_min})",
    )

# ---------------------------------------------------------------------
# Phần 2 — Distribution-shift: mean/std(y_train | FCF>threshold) vs
# mean/std(y_test | full near-failure, không lọc)
# ---------------------------------------------------------------------
print("=" * 70)
print("PHẦN 2 — Distribution shift: train (lọc FCF) vs test (near-failure đầy đủ)")
print("=" * 70)

test_pool = df[df[TARGET_RIR] < 10][TARGET_RIR]
test_mean, test_std = test_pool.mean(), test_pool.std()
print(
    f"Test pool (RIR<10, không lọc): mean={test_mean:.3f}, std={test_std:.3f}, n={len(test_pool)}\n"
)

dist_rows = []
for fcf_min in FCF_MIN_SWEEP:
    train_pool = df[(df["FCF"] > fcf_min) & (df[TARGET_RIR] < 10)][TARGET_RIR]
    train_mean, train_std = train_pool.mean(), train_pool.std()
    mean_gap = abs(train_mean - test_mean)
    dist_rows.append(
        dict(
            train_fcf_min=fcf_min,
            n_train_pool=len(train_pool),
            train_mean=train_mean,
            train_std=train_std,
            test_mean=test_mean,
            mean_gap_to_test=mean_gap,
        )
    )
    print(
        f"  FCF>{fcf_min}: train mean={train_mean:.3f} (std={train_std:.3f}, n={len(train_pool)}) "
        f"| gap to test mean = {mean_gap:.3f} reps",
        flush=True,
    )

dist_df = pd.DataFrame(dist_rows)
dist_df.to_csv(os.path.join(RESULTS_DIR, "rir_distribution_shift.csv"), index=False)

print("\n" + "=" * 70)
print("CÁCH ĐỌC KẾT QUẢ")
print("=" * 70)
print(
    "- Nếu 'RF cải thiện so với Naive' ở Phần 1 NHỎ (vài %) VÀ mean_gap_to_test ở\n"
    "  Phần 2 giảm đều theo threshold giống hệt xu hướng giảm MAE của RF/LR\n"
    "  => nghi ngờ distribution-matching có cơ sở mạnh, KHÔNG nên báo cáo\n"
    "  MAE=3.26 reps (FCF>0.7) như một kết quả học được tín hiệu thật.\n"
    "- Nếu RF vượt Naive rõ rệt (>20-30%) ở MỌI threshold, kể cả threshold thấp\n"
    "  (nơi distribution gap còn lớn) => RF đang học tín hiệu thật, distribution\n"
    "  shift chỉ là yếu tố phụ trợ làm bài toán dễ hơn chứ không phải nguồn duy nhất."
)
