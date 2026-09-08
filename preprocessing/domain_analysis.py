"""
Phase 4: Domain Analysis & Sanity Check
=========================================
Tách bạch 2 bước theo feedback:

Step A (Sanity Check thuần túy):
  Chạy lại đúng recipe cũ (F1_SLOPE5, RF, 3 clean muscles)
  để xác nhận bug fix reproducibility không làm lệch 16.8% gốc.

Step B (Rep-Zone Analysis):
  Chạy RMSE tách zone (anaerobic ≤25 vs aerobic >25)
  để lượng hóa domain-dependency của kết quả.

⚠️ Step A KHÔNG phải thí nghiệm mới — chỉ verify số cũ.
⚠️ Step B là phân tích mới, thuộc domain mismatch investigation.

Usage:
    python domain_analysis.py
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from sklearn.ensemble import RandomForestRegressor
from eval_protocols import run_loso, summary, compare_paired, check_go_no_go
from n1_features import F0_COLS, F1_ZSCORE_COLS, apply_rolling_slope
from iqr_filter import filter_outlier_trials


# ── Constants ────────────────────────────────────────────────────────────────
CSV_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "processed", "per_cycle_features.csv"
)
TARGET_FCF = "FCF"
RF_KWARGS = {"n_estimators": 200, "max_depth": 10, "n_jobs": -1, "random_state": 42}
CLEAN_MUSCLES = ["L DELTOID ANTERIOR", "R DELTOID MEDIUS", "L BICEPS BRACHII"]


def step_a_sanity_check(df):
    """
    STEP A: Sanity check - chay lai dung recipe cu.

    Recipe goc cho 16.8% GO:
      - 3 co sach (L DELTOID ANTERIOR, R DELTOID MEDIUS, L BICEPS BRACHII)
      - RF (n_estimators=200, max_depth=10)
      - F0 baseline vs F1_ZSCORE + MNF_mean_N1_slope5
      - LOSO-CV (13 fold)
      - Go/No-Go: (RMSE_F0 - RMSE_F1_slope5) / RMSE_F0 >= 15%

    Muc dich: XAC NHAN 16.8% KHONG BI LECH sau khi fix bug.
    Day KHONG PHAI thi nghiem moi.
    """
    print("\n" + "=" * 60)
    print("STEP A: SANITY CHECK — Re-verify 16.8% GO (exact old recipe)")
    print("=" * 60)
    print("  Recipe: 3 clean muscles, RF, F1_ZSCORE + slope5, LOSO")
    print("  NOTE: Ket qua nay tren domain ENDURANCE (Zenodo, N_total=56-164).")
    print("        KHONG dai dien cho resistance training (N_total=5-20).")
    print()

    # Filter clean muscles

    df_filtered = filter_outlier_trials(
        df, min_reps=10, verbose=False
    )  # ← THÊM DÒNG NÀY
    df_clean = df_filtered[df_filtered["muscle"].isin(CLEAN_MUSCLES)].copy()
    n_reps = len(df_clean)
    n_subjects = df_clean["subject"].nunique()
    print(
        f"  Data: {n_reps} reps, {n_subjects} subjects, "
        f"{df_clean['muscle'].nunique()} muscles"
    )

    # Ensure slope5 exists
    slope_col = "MNF_mean_N1_slope5"
    if slope_col not in df_clean.columns:
        df_clean = apply_rolling_slope(df_clean, feature_col="MNF_mean_N1", window=5)

    F1_SLOPE5 = F1_ZSCORE_COLS + [slope_col]

    # Run F0 baseline
    print("\n  Running LOSO RF with F0 (raw)...")
    res_f0 = run_loso(
        RandomForestRegressor, F0_COLS, TARGET_FCF, df_clean, model_kwargs=RF_KWARGS
    )
    rmse_f0 = res_f0["rmse"].mean()

    # Run F1 + slope5
    print("  Running LOSO RF with F1_ZSCORE + slope5...")
    res_f1 = run_loso(
        RandomForestRegressor, F1_SLOPE5, TARGET_FCF, df_clean, model_kwargs=RF_KWARGS
    )
    rmse_f1 = res_f1["rmse"].mean()

    # Go/No-Go
    improvement = (rmse_f0 - rmse_f1) / rmse_f0
    decision = "GO" if improvement >= 0.15 else "NO-GO"

    print(f"\n  {'─' * 50}")
    print(f"  F0 (raw):           RMSE = {rmse_f0:.2f}%")
    print(f"  F1 + slope5:        RMSE = {rmse_f1:.2f}%")
    print(f"  Relative improvement: {improvement * 100:.1f}%")
    print(f"  Decision: [{decision}]")
    print(f"  {'─' * 50}")

    if abs(improvement * 100 - 16.8) > 1.0:
        print(
            f"  !! CAM BAO: Ket qua {improvement * 100:.1f}% lech qua 1pp so voi 16.8% goc."
        )
        print(f"     Kiem tra lai per_cycle_features.csv co bi thay doi khong.")
    else:
        print(f"  Sanity check PASS: {improvement * 100:.1f}% ~ 16.8% goc.")

    # Statistical significance
    compare_paired(res_f0, res_f1, "F0", "F1+slope5")

    return {
        "rmse_f0": rmse_f0,
        "rmse_f1": rmse_f1,
        "improvement_pct": improvement * 100,
        "decision": decision,
    }


def step_b_rep_zone_analysis(df):
    """
    STEP B: Rep-zone analysis — luong hoa domain-dependency.

    Chia reps theo rep_idx:
      - Anaerobic zone: rep_idx <= 25 (tuong ung dau set, 'warmup/fresh')
      - Aerobic zone: rep_idx > 25 (vung sEMG fatigue ro, chu yeu la zone nay)

    Chay RMSE TACH RIENG theo zone de xem improvement 16.8% den tu dau.
    Neu tap trung o aerobic zone -> bang chung domain mismatch voi
    resistance training (chi co 5-15 reps, toan bo roi vao 'anaerobic zone').
    """
    print("\n" + "=" * 60)
    print("STEP B: REP-ZONE ANALYSIS — Domain dependency quantification")
    print("=" * 60)

    df_iqr = filter_outlier_trials(df, min_reps=10, verbose=False)
    df_clean = df_iqr[df_iqr["muscle"].isin(CLEAN_MUSCLES)].copy()

    # Ensure slope5
    slope_col = "MNF_mean_N1_slope5"
    if slope_col not in df_clean.columns:
        df_clean = apply_rolling_slope(df_clean, feature_col="MNF_mean_N1", window=5)

    F1_SLOPE5 = F1_ZSCORE_COLS + [slope_col]

    # Zone split
    df_clean["rep_zone"] = pd.cut(
        df_clean["rep_idx"],
        bins=[0, 25, 10000],
        labels=["anaerobic(<=25)", "aerobic(>25)"],
    )

    # Distribution
    print("\n  Zone distribution (3 clean muscles):")
    for zone, grp in df_clean.groupby("rep_zone", observed=True):
        n_total_stats = grp["N_total"].describe()
        print(
            f"    {zone}: n={len(grp)} reps | "
            f"N_total: mean={n_total_stats['mean']:.1f}, "
            f"min={n_total_stats['min']:.0f}, max={n_total_stats['max']:.0f}"
        )

    # RMSE per zone
    results = {}
    for zone in ["anaerobic(<=25)", "aerobic(>25)"]:
        df_zone = df_clean[df_clean["rep_zone"] == zone]
        n_subjects = df_zone["subject"].nunique()

        if n_subjects < 5:
            print(f"\n  Skipping {zone}: only {n_subjects} subjects (need >= 5)")
            continue

        print(f"\n  Zone: {zone} ({len(df_zone)} reps, {n_subjects} subjects)")

        res_f0 = run_loso(
            RandomForestRegressor, F0_COLS, TARGET_FCF, df_zone, model_kwargs=RF_KWARGS
        )
        res_f1 = run_loso(
            RandomForestRegressor,
            F1_SLOPE5,
            TARGET_FCF,
            df_zone,
            model_kwargs=RF_KWARGS,
        )

        rmse_f0 = res_f0["rmse"].mean()
        rmse_f1 = res_f1["rmse"].mean()
        improvement = (rmse_f0 - rmse_f1) / rmse_f0 * 100

        print(
            f"    F0: {rmse_f0:.2f}%  ->  F1+slope5: {rmse_f1:.2f}%  "
            f"| improvement: {improvement:.1f}%"
        )
        compare_paired(res_f0, res_f1, f"{zone}-F0", f"{zone}-F1+slope5")

        results[zone] = {
            "rmse_f0": rmse_f0,
            "rmse_f1": rmse_f1,
            "improvement_pct": improvement,
            "n_reps": len(df_zone),
        }

    # Interpretation
    print(f"\n  {'─' * 50}")
    print("  INTERPRETATION:")
    if results:
        anaerobic = results.get("anaerobic(<=25)", {})
        aerobic = results.get("aerobic(>25)", {})
        diff = anaerobic.get("improvement_pct", 0) - aerobic.get("improvement_pct", 0)
    if abs(diff) > 5:
        zone_name = "anaerobic (rep sớm)" if diff > 0 else "aerobic (rep muộn)"
        print(
            f"  -> Improvement TẬP TRUNG ở {zone_name}, chênh lệch {abs(diff):.1f}pp."
        )
        if diff > 0:
            print("     Tín hiệu KHẢ QUAN cho domain transfer (vùng gần resistance")
            print("     training thật cải thiện nhiều hơn), nhưng p riêng từng zone")
            print("     chưa SIG (power thấp do n giảm một nửa) — cần WP4 xác nhận.")
    else:
        print("  -> Improvement dàn đều giữa 2 zone.")
    return results


if __name__ == "__main__":
    print("Loading data...")
    if not os.path.exists(CSV_PATH):
        print(f"ERROR: {CSV_PATH} not found!")
        sys.exit(1)

    df = pd.read_csv(CSV_PATH)
    print(f"Loaded {len(df)} reps")

    # Need N1 z-score columns
    if "MNF_max_N1" not in df.columns:
        print("ERROR: N1 z-score columns missing. Run notebook first.")
        sys.exit(1)

    result_a = step_a_sanity_check(df)
    result_b = step_b_rep_zone_analysis(df)

    print("\n" + "=" * 60)
    print("DOMAIN ANALYSIS COMPLETE")
    print("=" * 60)
