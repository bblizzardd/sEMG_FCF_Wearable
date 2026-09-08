"""
N1 Feature Extension Module
============================
Mở rộng hệ thống chuẩn hóa N1 theo đặc tả thầy hướng dẫn.

Ba biến thể chuẩn hóa neo theo 3 rep đầu mỗi (subject, trial):
  1. Z-score:     x̃_k = (x_k − μ_{1:3}) / σ_{1:3}      [ĐÃ CÓ trong notebook]
  2. Ratio:       r_k  = x_k / x̄_{1:3}                   [MỚI]
  3. Differential: Δx_k = x_k − x_{k-1}                   [MỚI]

Usage:
    from n1_features import build_all_feature_sets
    feature_sets, df = build_all_feature_sets(df)
"""

import numpy as np
import pandas as pd


# ── Feature column definitions ───────────────────────────────────────────────
# 12 raw features (F0) — same as notebook
F0_COLS = [
    "MNF_max",
    "MNF_min",
    "MNF_mean",
    "MDF_max",
    "MDF_min",
    "MDF_mean",
    "TP_max",
    "TP_min",
    "TP_mean",
    "RMS_max",
    "RMS_min",
    "RMS_mean",
]

# 12 z-score features (existing N1)
F1_ZSCORE_COLS = [f"{c}_N1" for c in F0_COLS]

# 12 ratio features (new)
F1_RATIO_COLS = [f"{c}_ratio" for c in F0_COLS]

# 12 differential features (new)
F1_DIFF_COLS = [f"{c}_diff" for c in F0_COLS]


def apply_N1_ratio(df, baseline_n=3):
    """
    N1 ratio normalization: r_k = x_k / x̄_{1:3}

    Chia mỗi feature cho mean của 3 rep đầu tiên trong mỗi (subject, trial).
    Ý nghĩa: giá trị ~1.0 = bình thường, <1.0 = suy giảm, >1.0 = tăng.
    Phù hợp cho amplitude features (TP, RMS) hơn z-score (không giả định
    phân phối chuẩn, dễ interpret hơn).

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame chứa các cột F0 + metadata (subject, trial, rep_idx)
    baseline_n : int
        Số rep đầu dùng làm baseline (default=3, theo thầy)

    Returns
    -------
    pd.DataFrame
        DataFrame gốc + 12 cột mới *_ratio
    """
    out = df.copy()
    for (subj, trial), grp in df.groupby(["subject", "trial"]):
        base = grp[grp["rep_idx"] <= baseline_n]
        mask = (out["subject"] == subj) & (out["trial"] == trial)
        for col in F0_COLS:
            mu = base[col].mean()
            # Tránh chia cho 0: nếu mean baseline = 0, giữ nguyên raw value
            if abs(mu) < 1e-12:
                out.loc[mask, f"{col}_ratio"] = 1.0
            else:
                out.loc[mask, f"{col}_ratio"] = out.loc[mask, col] / mu
    return out


def apply_N1_diff(df):
    """
    N1 differential: Δx_k = x_k − x_{k-1}

    Vi phân theo rep trong mỗi (subject, trial).
    Ý nghĩa: tốc độ thay đổi feature giữa 2 rep liên tiếp.
    Rep đầu tiên của mỗi trial: Δx_1 = 0 (không có rep trước đó).

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame chứa các cột F0 + metadata

    Returns
    -------
    pd.DataFrame
        DataFrame gốc + 12 cột mới *_diff
    """
    out = df.copy()
    # Sort trước để diff() đúng thứ tự rep
    out = out.sort_values(["subject", "trial", "rep_idx"]).reset_index(drop=True)
    for col in F0_COLS:
        out[f"{col}_diff"] = out.groupby(["subject", "trial"])[col].diff().fillna(0)
    return out


def apply_rolling_slope(df, feature_col="MNF_mean_N1", window=5):
    """
    Rolling linear regression slope trên feature chuẩn hóa.

    Đây là feature sinh lý hợp lệ (không leak target), đã được xác nhận
    đóng góp +3.4pp RMSE improvement trong kết quả 16.8% GO.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame đã có feature_col
    feature_col : str
        Tên cột feature để tính slope (default: MNF_mean_N1)
    window : int
        Số rep cho rolling window (default=5)

    Returns
    -------
    pd.DataFrame
        DataFrame gốc + 1 cột {feature_col}_slope{window}
    """
    out = df.copy()
    out = out.sort_values(["subject", "trial", "rep_idx"]).reset_index(drop=True)

    def _slope_fn(w):
        if len(w) < 2:
            return 0.0
        return np.polyfit(range(len(w)), w, 1)[0]

    slope_col = f"{feature_col}_slope{window}"
    out[slope_col] = out.groupby(["subject", "trial"])[feature_col].transform(
        lambda x: x.rolling(window, min_periods=2).apply(_slope_fn, raw=False)
    )
    out[slope_col] = out[slope_col].fillna(0)
    return out


def build_all_feature_sets(df, baseline_n=3, slope_window=5):
    """
    Xây dựng tất cả feature sets theo đặc tả thầy.

    Áp dụng tuần tự:
    1. Ratio normalization
    2. Differential features
    3. Rolling slope

    Trả về dict các feature sets và DataFrame đã enriched.

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame gốc (đã có F0 + F1_N1 z-score từ notebook)
    baseline_n : int
        Số rep baseline cho ratio normalization
    slope_window : int
        Window size cho rolling slope

    Returns
    -------
    feature_sets : dict
        Mapping tên feature set → list tên cột
    df_enriched : pd.DataFrame
        DataFrame đầy đủ với tất cả features mới
    """
    # Verify existing N1 z-score columns exist
    missing_zscore = [c for c in F1_ZSCORE_COLS if c not in df.columns]
    if missing_zscore:
        raise ValueError(
            f"Missing N1 z-score columns: {missing_zscore}. "
            "Chạy apply_N1_normalization() trong notebook trước."
        )

    # Step 1: Ratio normalization
    df = apply_N1_ratio(df, baseline_n=baseline_n)

    # Step 2: Differential features
    df = apply_N1_diff(df)

    # Step 3: Rolling slope (trên z-score MNF_mean, feature sinh lý chính)
    slope_col = f"MNF_mean_N1_slope{slope_window}"
    if slope_col not in df.columns:
        df = apply_rolling_slope(df, feature_col="MNF_mean_N1", window=slope_window)

    # ── Feature set definitions ──────────────────────────────────────────
    feature_sets = {
        # Từng biến thể riêng lẻ (cho ablation A1)
        "F0": F0_COLS,
        "F1_ZSCORE": F1_ZSCORE_COLS,
        "F1_RATIO": F1_RATIO_COLS,
        "F1_DIFF": F1_DIFF_COLS,
        # Tổ hợp
        "F1_ZSCORE_SLOPE": F1_ZSCORE_COLS + [slope_col],
        "F1_FULL": F1_ZSCORE_COLS + F1_RATIO_COLS + F1_DIFF_COLS,
        "F1_FULL_SLOPE": F1_ZSCORE_COLS + F1_RATIO_COLS + F1_DIFF_COLS + [slope_col],
        # Tổ hợp 2-feature (cho ablation A1 chi tiết hơn)
        "F1_ZSCORE_RATIO": F1_ZSCORE_COLS + F1_RATIO_COLS,
        "F1_ZSCORE_DIFF": F1_ZSCORE_COLS + F1_DIFF_COLS,
        "F1_RATIO_DIFF": F1_RATIO_COLS + F1_DIFF_COLS,
    }

    return feature_sets, df


# ── Convenience: load + enrich in one call ─────────────────────────────────
def load_and_enrich(csv_path, baseline_n=3, slope_window=5):
    """
    Load per_cycle_features.csv và thêm tất cả N1 variants.

    Parameters
    ----------
    csv_path : str
        Path tới per_cycle_features.csv

    Returns
    -------
    feature_sets : dict
    df : pd.DataFrame
    """
    df = pd.read_csv(csv_path)
    return build_all_feature_sets(df, baseline_n=baseline_n, slope_window=slope_window)


if __name__ == "__main__":
    # Quick smoke test
    import os

    csv_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "processed", "per_cycle_features.csv"
    )
    if os.path.exists(csv_path):
        feature_sets, df = load_and_enrich(csv_path)
        print(f"DataFrame shape: {df.shape}")
        print(f"\nFeature sets available:")
        for name, cols in feature_sets.items():
            print(f"  {name:25s} -> {len(cols)} features")
        # Sanity check: no NaN in new columns
        new_cols = F1_RATIO_COLS + F1_DIFF_COLS
        n_nan = df[new_cols].isna().sum().sum()
        print(f"\nNaN count in new features: {n_nan}")

    else:
        print(f"CSV not found at {csv_path}")
