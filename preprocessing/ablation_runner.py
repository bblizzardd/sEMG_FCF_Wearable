"""
Ablation Runner (A1–A10)
=========================
Script chạy toàn bộ 10 ablation theo đặc tả thầy (Master Plan Phần 9).

⚠️ THỨ TỰ CHẠY CÓ PHỤ THUỘC:
  A1 → A2 (A2 cần biết feature set tốt nhất từ A1)
  A1–A5, A7–A8: chạy được ngay trên Zenodo
  A6, A9, A10: chỉ code khung, chạy khi có WP4 data

Usage:
    # Chạy tất cả ablation khả dụng:
    python ablation_runner.py --data ../data/processed/per_cycle_features.csv

    # Chạy ablation cụ thể:
    python ablation_runner.py --ablations A1 A3 A5

    # Chạy qua đêm (tất cả):
    python ablation_runner.py --ablations all --verbose
"""

import os
import sys
import json
import argparse
import warnings
from datetime import datetime

import numpy as np
import pandas as pd

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(__file__))

from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from iqr_filter import filter_outlier_trials

try:
    from xgboost import XGBRegressor

    HAS_XGB = True
except ImportError:
    HAS_XGB = False
    warnings.warn("xgboost not installed, skipping XGBRegressor in ablation")

from n1_features import (
    F0_COLS,
    F1_ZSCORE_COLS,
    F1_RATIO_COLS,
    F1_DIFF_COLS,
    build_all_feature_sets,
)
from eval_protocols import (
    run_loso,
    run_lomo,
    run_loso_near_failure,
    summary,
    compare_paired,
    check_go_no_go,
)
from stats_utils import bootstrap_ci_table, friedman_nemenyi


# ── Constants ────────────────────────────────────────────────────────────────
TARGET_FCF = "FCF"
TARGET_RIR = "RIR_clipped"

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# Model configs
RF_KWARGS = {"n_estimators": 200, "max_depth": 10, "n_jobs": -1, "random_state": 42}
XGB_KWARGS = {
    "n_estimators": 300,
    "max_depth": 6,
    "learning_rate": 0.05,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "random_state": 42,
}
LR_KWARGS = {"alpha": 1.0}


def _save_result(ablation_id, results_df, suffix=""):
    """Lưu kết quả ablation ra CSV."""
    path = os.path.join(RESULTS_DIR, f"ablation_{ablation_id}{suffix}.csv")
    results_df.to_csv(path, index=False)
    print(f"  → Saved: {path}")
    return path


# ══════════════════════════════════════════════════════════════════════════════
# A1: Chuẩn hóa neo
# ══════════════════════════════════════════════════════════════════════════════
def run_a1_normalization(df, feature_sets, verbose=True):
    """
    A1: So sánh F0 vs F1_ZSCORE vs F1_RATIO vs F1_DIFF vs F1_FULL.
    LOSO trên RF cho mỗi feature set.

    Returns
    -------
    dict: {feature_set_name: results_df}
    best_feature_set: str (tên feature set tốt nhất)
    """
    print("\n" + "=" * 60)
    print("ABLATION A1: Normalization Variants")
    print("=" * 60)

    configs = [
        "F0",
        "F1_ZSCORE",
        "F1_RATIO",
        "F1_DIFF",
        "F1_FULL",
        "F1_ZSCORE_SLOPE",
        "F1_FULL_SLOPE",
    ]
    all_results = {}
    summary_rows = []

    for config_name in configs:
        if config_name not in feature_sets:
            print(f"  Skipping {config_name}: not in feature_sets")
            continue

        feat_cols = feature_sets[config_name]
        # Check all columns exist
        missing = [c for c in feat_cols if c not in df.columns]
        if missing:
            print(f"  Skipping {config_name}: missing columns {missing[:3]}...")
            continue

        print(f"\n  Running LOSO RF with {config_name} ({len(feat_cols)} features)...")
        res = run_loso(
            RandomForestRegressor, feat_cols, TARGET_FCF, df, model_kwargs=RF_KWARGS
        )
        all_results[config_name] = res
        s = summary(res)
        s["config"] = config_name
        s["n_features"] = len(feat_cols)
        summary_rows.append(s)

        if verbose:
            print(f"    RMSE = {s['rmse_mean']:.2f}% ± {s['rmse_std']:.2f}")

    # Summary table
    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values("rmse_mean")
    print(f"\n{'─' * 60}")
    print("A1 Summary (sorted by RMSE):")
    print(
        summary_df[["config", "n_features", "rmse_mean", "rmse_std"]].to_string(
            index=False
        )
    )

    best = summary_df.iloc[0]["config"]
    print(
        f"\n  ✓ Best feature set: {best} (RMSE = {summary_df.iloc[0]['rmse_mean']:.2f}%)"
    )

    _save_result("A1", summary_df)

    # Bootstrap CI
    ci_table = bootstrap_ci_table(all_results, metric="rmse")
    _save_result("A1", ci_table, suffix="_bootstrap_ci")

    # Pairwise comparisons vs F0
    if "F0" in all_results:
        print(f"\n  Pairwise vs F0:")
        for name, res in all_results.items():
            if name != "F0":
                compare_paired(all_results["F0"], res, "F0", name)

    return all_results, best


# ══════════════════════════════════════════════════════════════════════════════
# A2: Model comparison
# ══════════════════════════════════════════════════════════════════════════════
def run_a2_model_comparison(df, feature_sets, best_feature_set=None, verbose=True):
    """
    A2: Ridge vs RF vs XGB trên feature set tốt nhất từ A1.

    ⚠️ PHỤ THUỘC A1: Cần best_feature_set từ A1.
    Nếu chưa có, sẽ dùng F1_ZSCORE_SLOPE mặc định và cảnh báo.
    """
    print("\n" + "=" * 60)
    print("ABLATION A2: Model Comparison")
    print("=" * 60)

    if best_feature_set is None:
        # Check if A1 results exist
        a1_path = os.path.join(RESULTS_DIR, "ablation_A1.csv")
        if os.path.exists(a1_path):
            a1_df = pd.read_csv(a1_path)
            best_feature_set = a1_df.sort_values("rmse_mean").iloc[0]["config"]
            print(f"  Loaded best feature set from A1: {best_feature_set}")
        else:
            best_feature_set = "F1_ZSCORE_SLOPE"
            print(f"  ⚠️ A1 not found! Using default: {best_feature_set}")
            print(f"     Run A1 first for rigorous ablation.")

    feat_cols = feature_sets[best_feature_set]
    print(f"  Feature set: {best_feature_set} ({len(feat_cols)} features)")

    models = {
        "Ridge": (Ridge, LR_KWARGS, True),
        "RF": (RandomForestRegressor, RF_KWARGS, False),
    }
    if HAS_XGB:
        models["XGB"] = (XGBRegressor, XGB_KWARGS, False)

    all_results = {}
    summary_rows = []

    for model_name, (model_cls, kwargs, needs_scale) in models.items():
        print(f"\n  Running LOSO {model_name}...")
        res = run_loso(
            model_cls,
            feat_cols,
            TARGET_FCF,
            df,
            model_kwargs=kwargs,
            model_needs_scale=needs_scale,
        )
        all_results[model_name] = res
        s = summary(res)
        s["model"] = model_name
        summary_rows.append(s)
        if verbose:
            print(f"    RMSE = {s['rmse_mean']:.2f}% ± {s['rmse_std']:.2f}")

    summary_df = pd.DataFrame(summary_rows)
    _save_result("A2", summary_df)

    # Friedman test
    if len(all_results) >= 3:
        friedman_nemenyi(all_results, metric="rmse")

    return all_results


# ══════════════════════════════════════════════════════════════════════════════
# A3: Single-head vs Dual-head
# ══════════════════════════════════════════════════════════════════════════════
def run_a3_single_vs_dual(df, feature_sets, best_feature_set=None, verbose=True):
    """
    A3: FCF-only head vs RIR-only head vs Dual-head.
    So sánh loss weighting impact.
    """
    print("\n" + "=" * 60)
    print("ABLATION A3: Single-Head vs Dual-Head")
    print("=" * 60)

    try:
        from dual_head_model import DualHeadMLP, run_dual_head_loso
    except ImportError:
        print("  ⚠️ dual_head_model not available. Skipping A3.")
        return {}

    if best_feature_set is None:
        best_feature_set = "F1_ZSCORE_SLOPE"
    feat_cols = feature_sets.get(best_feature_set, feature_sets.get("F1_ZSCORE_SLOPE"))

    configs = {
        "FCF-only (λ=1.0)": 1.0,
        "RIR-only (λ=0.0)": 0.0,
        "Dual λ=0.5": 0.5,
        "Dual λ=0.7": 0.7,
        "Dual λ=0.9": 0.9,
    }

    all_results = {}
    summary_rows = []

    for config_name, lambda_val in configs.items():
        print(f"\n  Running {config_name}...")
        res = run_dual_head_loso(
            DualHeadMLP,
            {"hidden_dim": 32},
            feat_cols,
            df,
            lambda_fcf=lambda_val,
            epochs=100,
            verbose=False,
        )
        all_results[config_name] = res
        s = {
            "config": config_name,
            "lambda": lambda_val,
            "rmse_fcf_mean": res["rmse_fcf"].mean(),
            "mae_rir_nf_mean": res["mae_rir_near_failure"].mean(),
        }
        summary_rows.append(s)
        if verbose:
            print(
                f"    FCF RMSE={s['rmse_fcf_mean']:.2f}%, "
                f"RIR MAE(nf)={s['mae_rir_nf_mean']:.2f}"
            )

    summary_df = pd.DataFrame(summary_rows)
    _save_result("A3", summary_df)
    return all_results


# ══════════════════════════════════════════════════════════════════════════════
# A4: Feature group ablation
# ══════════════════════════════════════════════════════════════════════════════
def run_a4_feature_groups(df, verbose=True):
    """
    A4: Time-domain only (RMS) vs Freq-domain only (MNF+MDF+TP) vs All.
    Includes pairwise Wilcoxon tests (Freq-only vs All N1) để quyết định
    có nên bỏ RMS khỏi thiết kế nhúng N5 không.
    """
    print("\n" + "=" * 60)
    print("ABLATION A4: Feature Groups")
    print("=" * 60)

    # Using N1 z-score variants for each group
    freq_cols = [c for c in F1_ZSCORE_COLS if any(f in c for f in ["MNF", "MDF", "TP"])]
    time_cols = [c for c in F1_ZSCORE_COLS if "RMS" in c]

    groups = {
        "Freq-only (MNF+MDF+TP)": freq_cols,
        "Time-only (RMS)": time_cols,
        "All N1": F1_ZSCORE_COLS,
    }

    all_results = {}
    summary_rows = []

    for group_name, feat_cols in groups.items():
        print(f"\n  {group_name}: {len(feat_cols)} features")
        res = run_loso(
            RandomForestRegressor, feat_cols, TARGET_FCF, df, model_kwargs=RF_KWARGS
        )
        all_results[group_name] = res
        s = summary(res)
        s["group"] = group_name
        s["n_features"] = len(feat_cols)
        summary_rows.append(s)
        if verbose:
            print(f"    RMSE = {s['rmse_mean']:.2f}% +- {s['rmse_std']:.2f}")

    summary_df = pd.DataFrame(summary_rows)
    _save_result("A4", summary_df)

    # Pairwise tests — quan trọng để quyết định có bỏ RMS khỏi N5 không
    print("\n  Pairwise Wilcoxon tests:")
    ref = "All N1"
    for name in ["Freq-only (MNF+MDF+TP)", "Time-only (RMS)"]:
        if name in all_results and ref in all_results:
            compare_paired(
                all_results[ref], all_results[name],
                label_a=ref, label_b=name,
            )

    # Kết luận nhanh cho người đọc
    if "Freq-only (MNF+MDF+TP)" in summary_df["group"].values:
        freq_rmse = summary_df.loc[summary_df["group"] == "Freq-only (MNF+MDF+TP)", "rmse_mean"].values[0]
        all_rmse  = summary_df.loc[summary_df["group"] == "All N1", "rmse_mean"].values[0]
        diff_pp = freq_rmse - all_rmse
        print(f"\n  Freq-only vs All N1: delta={diff_pp:+.2f}pp")
        if abs(diff_pp) < 0.5:
            print("  -> Delta < 0.5pp: RMS co the bo khoi thiet ke nhung N5 (kiem tra p-value)")
        else:
            print("  -> Delta >= 0.5pp: RMS co dong gop, nen giu lai")

    return all_results


# ==============================================================================
# A5: Rolling slope window
# ==============================================================================
def run_a5_slope_window(df, verbose=True):
    """
    A5: no-slope / slope3 / slope5 / slope7 / slope9 / slope11.
    Mở rộng so với A5 cũ (chỉ tới slope7) để tìm điểm bão hòa thật.
    """
    print("\n" + "=" * 60)
    print("ABLATION A5: Rolling Slope Window (extended: slope3-11)")
    print("=" * 60)

    from n1_features import apply_rolling_slope

    configs = {
        "no-slope": None,
        "slope3": 3,
        "slope5": 5,
        "slope7": 7,
        "slope9": 9,   # mới
        "slope11": 11, # mới
    }
    all_results = {}
    summary_rows = []

    for config_name, window in configs.items():
        if window is not None:
            slope_col = f"MNF_mean_N1_slope{window}"
            if slope_col not in df.columns:
                df = apply_rolling_slope(df, feature_col="MNF_mean_N1", window=window)
            feat_cols = F1_ZSCORE_COLS + [slope_col]
        else:
            feat_cols = F1_ZSCORE_COLS

        print(f"\n  {config_name}: {len(feat_cols)} features")
        res = run_loso(
            RandomForestRegressor, feat_cols, TARGET_FCF, df, model_kwargs=RF_KWARGS
        )
        all_results[config_name] = res
        s = summary(res)
        s["config"] = config_name
        s["window"] = window if window else 0
        summary_rows.append(s)
        if verbose:
            print(f"    RMSE = {s['rmse_mean']:.2f}% +- {s['rmse_std']:.2f}")

    summary_df = pd.DataFrame(summary_rows).sort_values("window")
    _save_result("A5", summary_df)

    # Pairwise vs no-slope
    print("\n  Pairwise vs no-slope (Wilcoxon):")
    if "no-slope" in all_results:
        for name, res in all_results.items():
            if name != "no-slope":
                compare_paired(all_results["no-slope"], res, "no-slope", name)

    # Tìm điểm bão hòa: window lớn nhất mà RMSE vẫn giảm so với window trước
    print("\n  Xu huong RMSE theo window size:")
    for _, row in summary_df.iterrows():
        print(f"    window={int(row['window']):2d}: RMSE={row['rmse_mean']:.3f}%")
    rmse_vals = summary_df[summary_df["window"] > 0]["rmse_mean"].values
    windows   = summary_df[summary_df["window"] > 0]["window"].values
    if len(rmse_vals) >= 2:
        last_delta = rmse_vals[-1] - rmse_vals[-2]
        if last_delta > -0.1:
            print(f"  -> Bao hoa: RMSE thay doi {last_delta:+.3f}pp (slope{int(windows[-2])} -> slope{int(windows[-1])})")
            print(f"  -> KHONG can tang window them nua.")
        else:
            print(f"  -> Van dang giam ({last_delta:+.3f}pp) — co the thu them slope13 neu can")

    return all_results


# ══════════════════════════════════════════════════════════════════════════════
# A6: IMU necessity (STUB — cần WP4 data)
# ══════════════════════════════════════════════════════════════════════════════
def run_a6_imu_necessity(df, verbose=True):
    """
    A6: sEMG-only vs sEMG+IMU features.
    ⚠️ STUB — Chỉ chạy được khi có IMU data từ WP4.
    """
    print("\n" + "=" * 60)
    print("ABLATION A6: IMU Necessity [STUB — awaiting WP4 data]")
    print("=" * 60)
    print("  Cần WP4 data với IMU 6 trục (ICM-42688-P / MPU6050).")
    print("  Khi có data: so sánh sEMG-only vs sEMG+IMU features.")
    print("  IMU features gợi ý: velocity_loss, peak_angular_vel, ROM")
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# A7: Muscle selection
# ══════════════════════════════════════════════════════════════════════════════
def run_a7_muscle_selection(df, feature_sets, best_feature_set=None, verbose=True):
    """
    A7: 3 clean muscles vs 6 uni-articular vs all 12.
    """
    print("\n" + "=" * 60)
    print("ABLATION A7: Muscle Selection")
    print("=" * 60)

    clean_muscles = ["L DELTOID ANTERIOR", "R DELTOID MEDIUS", "L BICEPS BRACHII"]
    uni_muscles = df[df["movement_type"] == "uni-articular"]["muscle"].unique().tolist()

    subsets = {
        "3 clean muscles": df[df["muscle"].isin(clean_muscles)],
        "Uni-articular only": df[df["movement_type"] == "uni-articular"],
        "All 12 muscles": df,
    }

    if best_feature_set is None:
        a1_path = os.path.join(RESULTS_DIR, "ablation_A1.csv")
        if os.path.exists(a1_path):
            a1_df = pd.read_csv(a1_path)
            best_feature_set = a1_df.sort_values("rmse_mean").iloc[0]["config"]
            print(f"  Loaded best feature set from A1: {best_feature_set}")
        else:
            best_feature_set = "F1_ZSCORE_SLOPE"
            print(f"  ⚠️ A1 not found! Using default: {best_feature_set}")

    feat_cols = feature_sets.get(best_feature_set, F1_ZSCORE_COLS)
    all_results = {}
    summary_rows = []

    for subset_name, df_sub in subsets.items():
        n_muscles = df_sub["muscle"].nunique()
        n_reps = len(df_sub)
        print(f"\n  {subset_name}: {n_muscles} muscles, {n_reps} reps")

        res = run_loso(
            RandomForestRegressor, feat_cols, TARGET_FCF, df_sub, model_kwargs=RF_KWARGS
        )

        res_f0 = run_loso(
            RandomForestRegressor, F0_COLS, TARGET_FCF, df_sub, model_kwargs=RF_KWARGS
        )
        improvement = (
            (res_f0["rmse"].mean() - res["rmse"].mean()) / res_f0["rmse"].mean() * 100
        )

        all_results[subset_name] = res
        s = summary(res)
        s["subset"] = subset_name
        s["n_muscles"] = n_muscles
        s["n_reps"] = n_reps
        summary_rows.append(s)
        if verbose:
            print(f"    RMSE = {s['rmse_mean']:.2f}% ± {s['rmse_std']:.2f}")
        print(f"    Improvement over F0: {improvement:.2f}%")

    summary_df = pd.DataFrame(summary_rows)
    _save_result("A7", summary_df)
    return all_results


# ══════════════════════════════════════════════════════════════════════════════
# A8: Baseline rep count
# ══════════════════════════════════════════════════════════════════════════════
def run_a8_baseline_reps(df, verbose=True):
    """
    A8: baseline_n ∈ {1, 2, 3, 5} cho N1 z-score.
    Cần re-normalize từ raw data mỗi lần.
    """

    print("\n" + "=" * 60)
    print("ABLATION A8: Baseline Rep Count")
    print("=" * 60)

    from n1_features import apply_N1_ratio, apply_rolling_slope

    baseline_values = [2, 3, 5]
    all_results = {}
    summary_rows = []

    for baseline_n in baseline_values:
        config_name = f"baseline_n={baseline_n}"
        print(f"\n  {config_name}:")

        # Re-normalize z-score with different baseline
        df_temp = df.copy()
        feat_cols_temp = []
        for col in F0_COLS:
            n1_col = f"{col}_N1_b{baseline_n}"
            # Manual z-score with custom baseline_n
            for (subj, trial), grp in df_temp.groupby(["subject", "trial"]):
                base = grp[grp["rep_idx"] <= baseline_n]
                if len(base) < 2:
                    print(
                        f"  ⚠️ Skip baseline_n={baseline_n}: some trials have <2 reps in baseline"
                    )
                    continue
                mask = (df_temp["subject"] == subj) & (df_temp["trial"] == trial)
                mu = base[col].mean()
                sg = base[col].std() + 1e-9
                df_temp.loc[mask, n1_col] = (df_temp.loc[mask, col] - mu) / sg
            feat_cols_temp.append(n1_col)

        n_nan = df_temp[feat_cols_temp].isna().sum().sum()
        if n_nan > 0:
            print(
                f"  ⚠️ {config_name}: {n_nan} NaN values in features — SKIPPING (baseline_n quá nhỏ)"
            )
            continue

        res = run_loso(
            RandomForestRegressor,
            feat_cols_temp,
            TARGET_FCF,
            df_temp,
            model_kwargs=RF_KWARGS,
        )
        all_results[config_name] = res
        s = summary(res)
        s["baseline_n"] = baseline_n
        summary_rows.append(s)
        if verbose:
            print(f"    RMSE = {s['rmse_mean']:.2f}% ± {s['rmse_std']:.2f}")

    summary_df = pd.DataFrame(summary_rows)
    _save_result("A8", summary_df)
    return all_results


# ══════════════════════════════════════════════════════════════════════════════
# A9: Sampling rate impact (STUB — cần WP4 data)
# ══════════════════════════════════════════════════════════════════════════════
def run_a9_sampling_rate(df, verbose=True):
    """
    A9: Downsample 1259→630→250→125 Hz, re-extract features.
    ⚠️ STUB — Cần raw signal data + re-extraction pipeline.
    """
    print("\n" + "=" * 60)
    print(
        "ABLATION A9: Sampling Rate Impact [STUB — requires raw signal re-extraction]"
    )
    print("=" * 60)
    print("  Cần downsample raw sEMG từ 1259 Hz và re-extract features.")
    print("  Target rates: 1259 (full), 630, 250, 125 Hz")
    print("  Cần gọi lại toàn bộ pipeline: filter → segment → feature_extract")
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# A10: Cross-load generalization (STUB — cần WP4 data)
# ══════════════════════════════════════════════════════════════════════════════
def run_a10_cross_load(df, verbose=True):
    """
    A10: Train 60+75% 1RM, test 85% 1RM.
    ⚠️ STUB — Cần WP4 data với 3 mức tải (60/75/85% 1RM).

    Đây là câu trả lời bắt buộc cho phản biện:
    "mô hình chỉ đang học đếm rep, không học mỏi cơ"
    """
    print("\n" + "=" * 60)
    print("ABLATION A10: Cross-Load Generalization [STUB — awaiting WP4 data]")
    print("=" * 60)
    print("  Cần WP4 data với 3 mức tải: 60%, 75%, 85% 1RM")
    print("  Protocol: Train trên 60+75%, test trên 85%")
    print("  Nếu model generalizes → chứng minh học mỏi cơ, không chỉ đếm rep")
    print("  ĐÂY LÀ ABLATION QUAN TRỌNG NHẤT cho phản biện paper.")
    return {}


# ══════════════════════════════════════════════════════════════════════════════
# Registry & Runner
# ══════════════════════════════════════════════════════════════════════════════
ABLATION_REGISTRY = {
    "A1": {
        "func": "run_a1_normalization",
        "needs_feature_sets": True,
        "description": "Normalization variants",
    },
    "A2": {
        "func": "run_a2_model_comparison",
        "needs_feature_sets": True,
        "depends_on": "A1",
        "description": "Model comparison (uses best features from A1)",
    },
    "A3": {
        "func": "run_a3_single_vs_dual",
        "needs_feature_sets": True,
        "description": "Single-head vs Dual-head",
    },
    "A4": {"func": "run_a4_feature_groups", "description": "Feature group ablation"},
    "A5": {"func": "run_a5_slope_window", "description": "Rolling slope window size"},
    "A6": {
        "func": "run_a6_imu_necessity",
        "stub": True,
        "description": "IMU necessity [STUB]",
    },
    "A7": {
        "func": "run_a7_muscle_selection",
        "needs_feature_sets": True,
        "description": "Muscle selection",
    },
    "A8": {
        "func": "run_a8_baseline_reps",
        "needs_raw_df": True,
        "description": "Baseline rep count",
    },
    "A9": {
        "func": "run_a9_sampling_rate",
        "stub": True,
        "description": "Sampling rate impact [STUB]",
    },
    "A10": {
        "func": "run_a10_cross_load",
        "stub": True,
        "description": "Cross-load generalization [STUB]",
    },
}


def check_dependencies(ablation_id):
    """Check if ablation dependencies are satisfied."""
    info = ABLATION_REGISTRY[ablation_id]
    dep = info.get("depends_on")
    if dep:
        dep_path = os.path.join(RESULTS_DIR, f"ablation_{dep}.csv")
        if not os.path.exists(dep_path):
            raise RuntimeError(
                f"Ablation {ablation_id} depends on {dep}, but {dep_path} not found. "
                f"Run {dep} first!"
            )
    return True


def run_all(data_path, ablations="all", verbose=True):
    """
    Main runner: load data, enrich features, chạy ablation theo thứ tự.
    """
    print(f"{'═' * 60}")
    print(f"ABLATION RUNNER — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Data: {data_path}")
    print(f"{'═' * 60}")

    # Load data
    df_raw = pd.read_csv(data_path)
    print(f"Loaded {len(df_raw)} reps from {df_raw['subject'].nunique()} subjects")

    df_raw = filter_outlier_trials(df_raw, min_reps=10, verbose=verbose)
    print(f"After IQR filter: {len(df_raw)} reps")

    # Build feature sets
    feature_sets, df = build_all_feature_sets(df_raw)
    print(f"Feature sets: {list(feature_sets.keys())}")

    # Determine which ablations to run
    if ablations == "all" or ablations == ["all"]:
        ablation_ids = list(ABLATION_REGISTRY.keys())
    else:
        ablation_ids = ablations

    # Track A1 result for A2 dependency
    best_feature_set = None

    for ablation_id in ablation_ids:
        if ablation_id not in ABLATION_REGISTRY:
            print(f"\n⚠️ Unknown ablation: {ablation_id}")
            continue

        info = ABLATION_REGISTRY[ablation_id]

        # Check dependencies
        try:
            check_dependencies(ablation_id)
        except RuntimeError as e:
            print(f"\n❌ {e}")
            continue

        # Skip stubs with a note
        if info.get("stub"):
            func = globals()[info["func"]]
            func(df, verbose=verbose)
            continue

        # Run
        func = globals()[info["func"]]
        kwargs = {"verbose": verbose}

        if info.get("needs_feature_sets"):
            kwargs["feature_sets"] = feature_sets

        if info.get("needs_raw_df"):
            kwargs["df"] = df_raw
        else:
            kwargs["df"] = df

        if ablation_id in ("A2", "A7") and best_feature_set:
            kwargs["best_feature_set"] = best_feature_set

        result = func(**kwargs)

        # Capture A1's best for A2
        if ablation_id == "A1" and isinstance(result, tuple):
            _, best_feature_set = result

    print(f"\n{'═' * 60}")
    print(f"ABLATION RUNNER COMPLETE -- {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Results saved to: {RESULTS_DIR}")
    print(f"{'═' * 60}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="sEMG FCF/RIR Ablation Runner")
    parser.add_argument(
        "--data",
        type=str,
        default=os.path.join(
            os.path.dirname(__file__),
            "..",
            "data",
            "processed",
            "per_cycle_features.csv",
        ),
        help="Path to per_cycle_features.csv",
    )
    parser.add_argument(
        "--ablations",
        nargs="+",
        default=["all"],
        help='Ablation IDs to run (e.g., A1 A3 A5) or "all"',
    )
    parser.add_argument("--verbose", action="store_true", default=True)
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args()
    verbose = not args.quiet

    run_all(args.data, ablations=args.ablations, verbose=verbose)
