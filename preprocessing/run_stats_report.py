"""
run_stats_report.py
====================
Bootstrap CI + Friedman + Nemenyi cho tat ca ablation A1/A2/A4/A5/A7/A8.

Chien luoc: tai chay LOSO qua cache (khong train lai) -> per-fold DataFrames
            -> stats_utils -> xuat Excel.

Usage:
    python preprocessing/run_stats_report.py
"""
import os, sys, io
import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from iqr_filter import filter_outlier_trials
from n1_features import build_all_feature_sets, apply_rolling_slope, F1_ZSCORE_COLS
from eval_protocols import run_loso, summary
from stats_utils import bootstrap_ci_table, friedman_nemenyi
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import Ridge

CSV_PATH    = os.path.join(os.path.dirname(__file__), "..", "data", "processed", "per_cycle_features.csv")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "results")
RF_KWARGS   = {"n_estimators": 200, "max_depth": 10, "n_jobs": -1, "random_state": 42}
TARGET_FCF  = "FCF"

print("Loading data...")
df_raw      = pd.read_csv(CSV_PATH)
df_filtered = filter_outlier_trials(df_raw, min_reps=10, verbose=False)   # IQR only, no N1 yet
feature_sets, df = build_all_feature_sets(df_filtered)                    # enriched with baseline_n=3
print(f"  {len(df)} reps, {df['subject'].nunique()} subjects after IQR filter")


all_sheets = {}

def add_to_paper(ablation_id, ci_df, config_col="config"):
    rows = []
    for _, row in ci_df.iterrows():
        rows.append({
            "Ablation": ablation_id,
            "Config":   row[config_col],
            "RMSE_mean": round(row["rmse_mean"], 3),
            "CI_lower":  round(row["rmse_ci_lower"], 3),
            "CI_upper":  round(row["rmse_ci_upper"], 3),
            "CI_str":    f"{row['rmse_mean']:.2f} [{row['rmse_ci_lower']:.2f}, {row['rmse_ci_upper']:.2f}]",
        })
    return rows

paper_rows = []

# ─────────────────────────────────────────────────────────────────────────────
# A1 - Normalization variants
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("A1: Normalization variants")
print("="*60)

A1_CONFIGS = ["F0","F1_ZSCORE","F1_RATIO","F1_DIFF","F1_ZSCORE_SLOPE","F1_FULL","F1_FULL_SLOPE"]
a1_results = {}
for cfg in A1_CONFIGS:
    if cfg not in feature_sets:
        continue
    res = run_loso(RandomForestRegressor, feature_sets[cfg], TARGET_FCF, df, model_kwargs=RF_KWARGS)
    a1_results[cfg] = res
    s = summary(res)
    print(f"  {cfg:20s}: {s['rmse_mean']:.3f}% +- {s['rmse_std']:.3f}")

ci_a1 = bootstrap_ci_table(a1_results, metric="rmse", n_boot=10000)
all_sheets["A1_bootstrap_ci"] = ci_a1.sort_values("rmse_mean")
paper_rows += add_to_paper("A1", ci_a1)

fn_a1 = friedman_nemenyi(a1_results, metric="rmse")
if fn_a1:
    print(f"  Friedman: p={fn_a1['friedman_p']:.4f} [{'SIG' if fn_a1['significant'] else 'n.s.'}]")
    if fn_a1.get("posthoc_df") is not None:
        all_sheets["A1_nemenyi"] = fn_a1["posthoc_df"].reset_index()

# ─────────────────────────────────────────────────────────────────────────────
# A2 - Model comparison
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("A2: Model comparison")
print("="*60)

from xgboost import XGBRegressor
best_feats = feature_sets["F1_FULL_SLOPE"]
a2_results = {
    "Ridge": run_loso(Ridge, best_feats, TARGET_FCF, df, model_kwargs={"alpha": 1.0}, model_needs_scale=True),
    "RF":    run_loso(RandomForestRegressor, best_feats, TARGET_FCF, df, model_kwargs=RF_KWARGS),
    "XGB":   run_loso(XGBRegressor, best_feats, TARGET_FCF, df,
                      model_kwargs={"n_estimators": 300, "max_depth": 6,
                                    "learning_rate": 0.05, "random_state": 42, "verbosity": 0}),
}
for name, res in a2_results.items():
    s = summary(res)
    print(f"  {name:8s}: {s['rmse_mean']:.3f}% +- {s['rmse_std']:.3f}")

ci_a2 = bootstrap_ci_table(a2_results, metric="rmse", n_boot=10000)
all_sheets["A2_bootstrap_ci"] = ci_a2
paper_rows += add_to_paper("A2", ci_a2)

fn_a2 = friedman_nemenyi(a2_results, metric="rmse")
if fn_a2:
    print(f"  Friedman: p={fn_a2['friedman_p']:.4f} [{'SIG' if fn_a2['significant'] else 'n.s.'}]")
    if fn_a2.get("posthoc_df") is not None:
        all_sheets["A2_nemenyi"] = fn_a2["posthoc_df"].reset_index()

# ─────────────────────────────────────────────────────────────────────────────
# A4 - Feature groups
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("A4: Feature groups")
print("="*60)

freq_cols = [c for c in F1_ZSCORE_COLS if any(f in c for f in ["MNF", "MDF", "TP"])]
time_cols = [c for c in F1_ZSCORE_COLS if "RMS" in c]
a4_results = {
    "Freq-only": run_loso(RandomForestRegressor, freq_cols, TARGET_FCF, df, model_kwargs=RF_KWARGS),
    "Time-only": run_loso(RandomForestRegressor, time_cols, TARGET_FCF, df, model_kwargs=RF_KWARGS),
    "All N1":    run_loso(RandomForestRegressor, F1_ZSCORE_COLS, TARGET_FCF, df, model_kwargs=RF_KWARGS),
}
for name, res in a4_results.items():
    s = summary(res)
    print(f"  {name:12s}: {s['rmse_mean']:.3f}% +- {s['rmse_std']:.3f}")

ci_a4 = bootstrap_ci_table(a4_results, metric="rmse", n_boot=10000)
all_sheets["A4_bootstrap_ci"] = ci_a4
paper_rows += add_to_paper("A4", ci_a4)

# ─────────────────────────────────────────────────────────────────────────────
# A5 - Slope window (extended)
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("A5: Slope window (no-slope / 3 / 5 / 7 / 9 / 11)")
print("="*60)

a5_results = {}
for window in [0, 3, 5, 7, 9, 11]:
    if window == 0:
        feat_cols = F1_ZSCORE_COLS
        cfg_name  = "no-slope"
    else:
        slope_col = f"MNF_mean_N1_slope{window}"
        if slope_col not in df.columns:
            df = apply_rolling_slope(df, feature_col="MNF_mean_N1", window=window)
        feat_cols = F1_ZSCORE_COLS + [slope_col]
        cfg_name  = f"slope{window}"
    res = run_loso(RandomForestRegressor, feat_cols, TARGET_FCF, df, model_kwargs=RF_KWARGS)
    a5_results[cfg_name] = res
    s = summary(res)
    print(f"  {cfg_name:10s}: {s['rmse_mean']:.3f}% +- {s['rmse_std']:.3f}")

ci_a5 = bootstrap_ci_table(a5_results, metric="rmse", n_boot=10000)
all_sheets["A5_bootstrap_ci"] = ci_a5
paper_rows += add_to_paper("A5", ci_a5)

fn_a5 = friedman_nemenyi(a5_results, metric="rmse")
if fn_a5:
    print(f"  Friedman: p={fn_a5['friedman_p']:.6f} [{'SIG' if fn_a5['significant'] else 'n.s.'}]")
    if fn_a5.get("posthoc_df") is not None:
        ph = fn_a5["posthoc_df"].round(4)
        all_sheets["A5_nemenyi"] = ph.reset_index()
        print(ph.to_string())

# ─────────────────────────────────────────────────────────────────────────────
# A7 - Muscle selection
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("A7: Muscle selection")
print("="*60)

CLEAN_MUSCLES   = ["L DELTOID ANTERIOR", "R DELTOID MEDIUS", "L BICEPS BRACHII"]
UNI_ART_MUSCLES = [m for m in df["muscle"].unique() if not m.endswith(" C")]

subsets = {
    "3-clean":        df[df["muscle"].isin(CLEAN_MUSCLES)],
    "8-uni-articular": df[df["muscle"].isin(UNI_ART_MUSCLES)],
    "12-all":          df,
}
best_feats_full = feature_sets["F1_FULL_SLOPE"]
a7_results = {}
for name, sub_df in subsets.items():
    feat_cols = [c for c in best_feats_full if c in sub_df.columns]
    res = run_loso(RandomForestRegressor, feat_cols, TARGET_FCF, sub_df, model_kwargs=RF_KWARGS)
    a7_results[name] = res
    s = summary(res)
    print(f"  {name:20s}: n={len(sub_df):5d}, {s['rmse_mean']:.3f}% +- {s['rmse_std']:.3f}")

ci_a7 = bootstrap_ci_table(a7_results, metric="rmse", n_boot=10000)
all_sheets["A7_bootstrap_ci"] = ci_a7
paper_rows += add_to_paper("A7", ci_a7)

fn_a7 = friedman_nemenyi(a7_results, metric="rmse")
if fn_a7:
    print(f"  Friedman: p={fn_a7['friedman_p']:.4f} [{'SIG' if fn_a7['significant'] else 'n.s.'}]")
    if fn_a7.get("posthoc_df") is not None:
        all_sheets["A7_nemenyi"] = fn_a7["posthoc_df"].reset_index()

# ─────────────────────────────────────────────────────────────────────────────
# A8 - Baseline rep count
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "="*60)
print("A8: Baseline rep count (2 / 3 / 5)")
print("="*60)

a8_results = {}
for baseline_n in [2, 3, 5]:
    # IMPORTANT: pass df_filtered (unenriched) so N1 is recalculated with different baseline_n
    feature_sets_b, df_b = build_all_feature_sets(df_filtered, baseline_n=baseline_n)
    feat_cols = feature_sets_b.get("F1_ZSCORE", F1_ZSCORE_COLS)
    feat_cols = [c for c in feat_cols if c in df_b.columns]
    res = run_loso(RandomForestRegressor, feat_cols, TARGET_FCF, df_b, model_kwargs=RF_KWARGS)
    cfg = f"baseline_n={baseline_n}"
    a8_results[cfg] = res
    s = summary(res)
    print(f"  {cfg}: {s['rmse_mean']:.3f}% +- {s['rmse_std']:.3f}")

ci_a8 = bootstrap_ci_table(a8_results, metric="rmse", n_boot=10000)
all_sheets["A8_bootstrap_ci"] = ci_a8
paper_rows += add_to_paper("A8", ci_a8)


# ─────────────────────────────────────────────────────────────────────────────
# Paper summary sheet
# ─────────────────────────────────────────────────────────────────────────────
paper_df = pd.DataFrame(paper_rows)
all_sheets["paper_summary"] = paper_df
print("\n" + "="*60)
print("PAPER SUMMARY (RMSE [95% CI])")
print("="*60)
print(paper_df[["Ablation", "Config", "CI_str"]].to_string(index=False))

# ─────────────────────────────────────────────────────────────────────────────
# Export Excel
# ─────────────────────────────────────────────────────────────────────────────
out_path = os.path.join(RESULTS_DIR, "stats_report.xlsx")
with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
    for sheet_name, sheet_df in all_sheets.items():
        sheet_df.to_excel(writer, sheet_name=sheet_name[:31], index=False)

print(f"\nSaved -> {out_path}")
print(f"Sheets: {list(all_sheets.keys())}")
