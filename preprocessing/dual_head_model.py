"""
Dual-Head Regression Model (N2)
================================
Kiến trúc dual-head FCF + RIR theo đặc tả thầy hướng dẫn.

Hai variant:
  - Model 4A: Per-Rep MLP (~2k params) — lightweight, dùng cho nhúng
  - Model 4B: Sliding-Window CNN + GRU (~10-30k params) — sequence model,
              dùng để chứng minh N2/N3 trên Zenodo

Loss: L = λ·MSE(FCF) + (1-λ)·Huber(RIR)
  - Huber cho RIR (thầy yêu cầu, robust với outlier RIR cao)
  - FCF head: Sigmoid → output ∈ [0, 1]
  - RIR head: Softplus → output ≥ 0 (thầy yêu cầu Softplus, KHÔNG phải ReLU×10)

Usage:
    from dual_head_model import DualHeadMLP, DualHeadCNNGRU, DualHeadTrainer
    model = DualHeadMLP(input_dim=13)
    trainer = DualHeadTrainer(model, lambda_fcf=0.7)
    trainer.train(train_loader, val_loader, epochs=100)
"""

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader


# ══════════════════════════════════════════════════════════════════════════════
# Model 4A: Per-Rep MLP Dual-Head
# ══════════════════════════════════════════════════════════════════════════════
class DualHeadMLP(nn.Module):
    """
    Per-Rep MLP Dual-Head.
    ~2k parameters (lightweight, deployable on ESP32-S3 after INT8 quantization).

    Architecture:
        Input(F) → Linear(F, hidden) → ReLU → Dropout → Linear(hidden, hidden//2) → ReLU
          ├─ FCF Head: Linear(hidden//2, 1) → Sigmoid
          └─ RIR Head: Linear(hidden//2, 1) → Softplus
    """

    def __init__(self, input_dim, hidden_dim=32, dropout=0.2):
        super().__init__()
        mid_dim = hidden_dim // 2

        self.shared = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, mid_dim),
            nn.ReLU(),
        )

        # FCF head: Sigmoid → output ∈ [0, 1]
        self.fcf_head = nn.Sequential(
            nn.Linear(mid_dim, 1),
            nn.Sigmoid(),
        )

        # RIR head: Softplus → output ≥ 0 (thầy đặc tả Softplus)
        self.rir_head = nn.Sequential(
            nn.Linear(mid_dim, 1),
            nn.Softplus(),
        )

    def forward(self, x):
        """
        Parameters
        ----------
        x : Tensor, shape (batch, input_dim)

        Returns
        -------
        fcf_pred : Tensor, shape (batch, 1) — ∈ [0, 1]
        rir_pred : Tensor, shape (batch, 1) — ≥ 0
        """
        shared = self.shared(x)
        fcf = self.fcf_head(shared)
        rir = self.rir_head(shared)
        return fcf, rir

    def count_params(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ══════════════════════════════════════════════════════════════════════════════
# Model 4B: Sliding-Window CNN + GRU Dual-Head
# ══════════════════════════════════════════════════════════════════════════════
class DualHeadCNNGRU(nn.Module):
    """
    Sliding-Window 1D-CNN + GRU Dual-Head.
    ~10-30k parameters (cho chứng minh N2/N3 trên Zenodo, KHÔNG nhất thiết
    là model nhúng cuối cùng — theo Master Plan, model nhúng là P1 INT8).

    Architecture:
        Input(W×F, W=window reps) → Conv1D(F, conv_dim, k=3) → ReLU
          → Conv1D(conv_dim, conv_dim, k=3) → ReLU
          → GRU(conv_dim, gru_dim) → last hidden state
          ├─ FCF Head: Linear(gru_dim, 1) → Sigmoid
          └─ RIR Head: Linear(gru_dim, 1) → Softplus
    """

    def __init__(self, input_dim, window_size=5, conv_dim=32, gru_dim=16, dropout=0.2):
        super().__init__()
        self.window_size = window_size

        # Conv layers: input shape (batch, input_dim, window_size)
        self.conv = nn.Sequential(
            nn.Conv1d(input_dim, conv_dim, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Conv1d(conv_dim, conv_dim, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.Dropout(dropout),
        )

        # GRU: input shape (batch, window_size, conv_dim)
        self.gru = nn.GRU(conv_dim, gru_dim, batch_first=True)

        # Dual heads
        self.fcf_head = nn.Sequential(
            nn.Linear(gru_dim, 1),
            nn.Sigmoid(),
        )
        self.rir_head = nn.Sequential(
            nn.Linear(gru_dim, 1),
            nn.Softplus(),
        )

    def forward(self, x):
        """
        Parameters
        ----------
        x : Tensor, shape (batch, window_size, input_dim)

        Returns
        -------
        fcf_pred : Tensor, shape (batch, 1)
        rir_pred : Tensor, shape (batch, 1)
        """
        # Conv1D expects (batch, channels, length)
        conv_in = x.permute(0, 2, 1)  # (batch, input_dim, window)
        conv_out = self.conv(conv_in)  # (batch, conv_dim, window)
        gru_in = conv_out.permute(0, 2, 1)  # (batch, window, conv_dim)

        _, hidden = self.gru(gru_in)  # hidden: (1, batch, gru_dim)
        hidden = hidden.squeeze(0)  # (batch, gru_dim)

        fcf = self.fcf_head(hidden)
        rir = self.rir_head(hidden)
        return fcf, rir

    def count_params(self):
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


# ══════════════════════════════════════════════════════════════════════════════
# Dataset classes
# ══════════════════════════════════════════════════════════════════════════════
class PerRepDataset(Dataset):
    """Dataset cho Model 4A: mỗi sample = 1 rep."""

    def __init__(self, X, y_fcf, y_rir):
        self.X = torch.FloatTensor(X)
        self.y_fcf = torch.FloatTensor(y_fcf).unsqueeze(1)
        self.y_rir = torch.FloatTensor(y_rir).unsqueeze(1)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y_fcf[idx], self.y_rir[idx]


class SequenceDataset(Dataset):
    """
    Dataset cho Model 4B: mỗi sample = window reps liên tiếp.
    Target = FCF/RIR của rep cuối cùng trong window.
    Padding đầu set bằng rep đầu tiên (repeat).
    """

    def __init__(self, X_seq, y_fcf, y_rir):
        self.X_seq = torch.FloatTensor(X_seq)
        self.y_fcf = torch.FloatTensor(y_fcf).unsqueeze(1)
        self.y_rir = torch.FloatTensor(y_rir).unsqueeze(1)

    def __len__(self):
        return len(self.X_seq)

    def __getitem__(self, idx):
        return self.X_seq[idx], self.y_fcf[idx], self.y_rir[idx]


def create_sequences(df, feat_cols, window=5):
    """
    Tạo sliding window sequences cho Model 4B.

    Mỗi (subject, trial) tạo ra (N_total - window + 1) sequences
    (hoặc N_total sequences nếu pad đầu set).

    Parameters
    ----------
    df : pd.DataFrame
        Phải sorted theo (subject, trial, rep_idx)
    feat_cols : list of str
    window : int

    Returns
    -------
    X_seq : ndarray, shape (n_samples, window, n_features)
    y_fcf : ndarray, shape (n_samples,)
    y_rir : ndarray, shape (n_samples,)
    meta : pd.DataFrame
        Metadata (subject, trial, rep_idx) cho mỗi sample
    """
    df_sorted = df.sort_values(["subject", "trial", "rep_idx"]).reset_index(drop=True)

    all_X, all_fcf, all_rir = [], [], []
    meta_rows = []

    for (subj, trial), grp in df_sorted.groupby(["subject", "trial"]):
        features = grp[feat_cols].values  # (N_total, F)
        fcf_vals = grp["FCF"].values
        rir_vals = grp["RIR_clipped"].values

        n = len(features)
        for i in range(n):
            # Window: [i-window+1, ..., i], padding đầu bằng repeat
            start = max(0, i - window + 1)
            seq = features[start : i + 1]
            # Pad nếu cần
            if len(seq) < window:
                pad = np.repeat(seq[0:1], window - len(seq), axis=0)
                seq = np.vstack([pad, seq])
            all_X.append(seq)
            all_fcf.append(fcf_vals[i])
            all_rir.append(rir_vals[i])
            meta_rows.append(
                {
                    "subject": subj,
                    "trial": trial,
                    "rep_idx": grp.iloc[i]["rep_idx"],
                }
            )

    X_seq = np.array(all_X)
    y_fcf = np.array(all_fcf)
    y_rir = np.array(all_rir)
    meta = pd.DataFrame(meta_rows)

    return X_seq, y_fcf, y_rir, meta


# ══════════════════════════════════════════════════════════════════════════════
# Dual-Head Loss
# ══════════════════════════════════════════════════════════════════════════════
class DualHeadLoss(nn.Module):
    """
    Combined loss: L = λ·MSE(FCF) + (1-λ)·Huber(RIR)

    Huber loss cho RIR theo đặc tả thầy:
    - Robust với outlier RIR cao
    - delta=1.0 (default PyTorch SmoothL1Loss)
    """

    def __init__(self, lambda_fcf=0.7, huber_delta=1.0):
        super().__init__()
        self.lambda_fcf = lambda_fcf
        self.mse = nn.MSELoss()
        self.huber = nn.SmoothL1Loss(beta=huber_delta)

    def forward(self, fcf_pred, fcf_true, rir_pred, rir_true):
        loss_fcf = self.mse(fcf_pred, fcf_true)
        loss_rir = self.huber(rir_pred, rir_true)
        return self.lambda_fcf * loss_fcf + (1 - self.lambda_fcf) * loss_rir


# ══════════════════════════════════════════════════════════════════════════════
# Trainer
# ══════════════════════════════════════════════════════════════════════════════
class DualHeadTrainer:
    """
    Training loop cho dual-head models với LOSO-CV integration.

    Features:
    - Combined loss (λ·MSE + (1-λ)·Huber)
    - Early stopping (patience=10)
    - ReduceLROnPlateau scheduler
    - Separate FCF/RIR metrics
    """

    def __init__(self, model, lambda_fcf=0.7, lr=1e-3, patience=10, device=None):
        self.model = model
        self.lambda_fcf = lambda_fcf
        self.lr = lr
        self.patience = patience
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(self.device)

        self.criterion = DualHeadLoss(lambda_fcf=lambda_fcf)
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=lr)
        self.scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            self.optimizer, mode="min", factor=0.5, patience=5, verbose=False
        )

    def train(self, train_loader, val_loader=None, epochs=100, verbose=True):
        """
        Train model với early stopping.

        Returns
        -------
        history : dict with lists of train_loss, val_loss per epoch
        """
        best_val_loss = float("inf")
        patience_counter = 0
        best_state = None
        history = {"train_loss": [], "val_loss": []}

        for epoch in range(epochs):
            # Train phase
            self.model.train()
            train_losses = []
            for batch in train_loader:
                X, y_fcf, y_rir = [b.to(self.device) for b in batch]
                self.optimizer.zero_grad()
                fcf_pred, rir_pred = self.model(X)
                loss = self.criterion(fcf_pred, y_fcf, rir_pred, y_rir)
                loss.backward()
                self.optimizer.step()
                train_losses.append(loss.item())

            avg_train = np.mean(train_losses)
            history["train_loss"].append(avg_train)

            # Validation phase
            if val_loader is not None:
                avg_val = self._evaluate(val_loader)
                history["val_loss"].append(avg_val)
                self.scheduler.step(avg_val)

                if avg_val < best_val_loss:
                    best_val_loss = avg_val
                    patience_counter = 0
                    best_state = {
                        k: v.cpu().clone() for k, v in self.model.state_dict().items()
                    }
                else:
                    patience_counter += 1

                if verbose and (epoch + 1) % 10 == 0:
                    print(
                        f"  Epoch {epoch + 1:3d}: train={avg_train:.4f} "
                        f"val={avg_val:.4f} (best={best_val_loss:.4f})"
                    )

                if patience_counter >= self.patience:
                    if verbose:
                        print(f"  Early stopping at epoch {epoch + 1}")
                    break

        # Restore best model
        if best_state is not None:
            self.model.load_state_dict(best_state)

        return history

    def _evaluate(self, loader):
        """Evaluate loss on a data loader."""
        self.model.eval()
        losses = []
        with torch.no_grad():
            for batch in loader:
                X, y_fcf, y_rir = [b.to(self.device) for b in batch]
                fcf_pred, rir_pred = self.model(X)
                loss = self.criterion(fcf_pred, y_fcf, rir_pred, y_rir)
                losses.append(loss.item())
        return np.mean(losses)

    def predict(self, loader):
        """
        Predict FCF and RIR on a data loader.

        Returns
        -------
        fcf_preds, rir_preds : ndarray
        """
        self.model.eval()
        all_fcf, all_rir = [], []
        with torch.no_grad():
            for batch in loader:
                X = batch[0].to(self.device)
                fcf_pred, rir_pred = self.model(X)
                all_fcf.append(fcf_pred.cpu().numpy())
                all_rir.append(rir_pred.cpu().numpy())
        return np.concatenate(all_fcf).flatten(), np.concatenate(all_rir).flatten()


# ══════════════════════════════════════════════════════════════════════════════
# LOSO-CV Runner for Dual-Head Models
# ══════════════════════════════════════════════════════════════════════════════
def run_dual_head_loso(
    model_cls,
    model_kwargs,
    feat_cols,
    df,
    lambda_fcf=0.7,
    lr=1e-3,
    epochs=100,
    batch_size=64,
    patience=10,
    window=None,
    verbose=False,
):
    """
    LOSO-CV cho dual-head models.

    Parameters
    ----------
    model_cls : class (DualHeadMLP or DualHeadCNNGRU)
    model_kwargs : dict
        Kwargs cho model constructor (input_dim auto-filled)
    feat_cols : list of str
    df : pd.DataFrame
    lambda_fcf : float
    lr : float
    epochs : int
    batch_size : int
    patience : int
    window : int or None
        Nếu None → per-rep mode (Model 4A)
        Nếu int → sequence mode (Model 4B)
    verbose : bool

    Returns
    -------
    pd.DataFrame with columns: test_subject, rmse_fcf, mae_fcf, rmse_rir, mae_rir,
                                mae_rir_near_failure
    """
    from sklearn.metrics import mean_squared_error, mean_absolute_error

    subjects = sorted(df["subject"].unique())
    results = []

    for test_subj in subjects:
        train_df = df[df["subject"] != test_subj].copy()
        test_df = df[df["subject"] == test_subj].copy()

        if window is not None:
            # Sequence mode (Model 4B)
            X_tr, y_fcf_tr, y_rir_tr, _ = create_sequences(train_df, feat_cols, window)
            X_te, y_fcf_te, y_rir_te, meta_te = create_sequences(
                test_df, feat_cols, window
            )
            train_ds = SequenceDataset(X_tr, y_fcf_tr, y_rir_tr)
            test_ds = SequenceDataset(X_te, y_fcf_te, y_rir_te)
            kwargs = {
                **model_kwargs,
                "input_dim": len(feat_cols),
                "window_size": window,
            }
        else:
            # Per-rep mode (Model 4A)
            X_tr = train_df[feat_cols].values
            y_fcf_tr = train_df["FCF"].values
            y_rir_tr = train_df["RIR_clipped"].values
            X_te = test_df[feat_cols].values
            y_fcf_te = test_df["FCF"].values
            y_rir_te = test_df["RIR_clipped"].values
            train_ds = PerRepDataset(X_tr, y_fcf_tr, y_rir_tr)
            test_ds = PerRepDataset(X_te, y_fcf_te, y_rir_te)
            kwargs = {**model_kwargs, "input_dim": len(feat_cols)}

        train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
        test_loader = DataLoader(test_ds, batch_size=batch_size, shuffle=False)

        # Create fresh model per fold
        model = model_cls(**kwargs)
        trainer = DualHeadTrainer(
            model, lambda_fcf=lambda_fcf, lr=lr, patience=patience
        )
        trainer.train(
            train_loader, val_loader=test_loader, epochs=epochs, verbose=verbose
        )

        # Predict
        fcf_pred, rir_pred = trainer.predict(test_loader)

        # Clip predictions
        fcf_pred = np.clip(fcf_pred, 0, 1)
        rir_pred = np.clip(rir_pred, 0, 10)

        # FCF metrics (percentage)
        rmse_fcf = np.sqrt(mean_squared_error(y_fcf_te, fcf_pred)) * 100
        mae_fcf = mean_absolute_error(y_fcf_te, fcf_pred) * 100

        # RIR metrics (reps)
        rmse_rir = np.sqrt(mean_squared_error(y_rir_te, rir_pred))
        mae_rir = mean_absolute_error(y_rir_te, rir_pred)

        # RIR near-failure (RIR < 10)
        nf_mask = y_rir_te < 10
        if nf_mask.sum() > 0:
            mae_rir_nf = mean_absolute_error(y_rir_te[nf_mask], rir_pred[nf_mask])
        else:
            mae_rir_nf = float("nan")

        result = {
            "test_subject": test_subj,
            "rmse_fcf": rmse_fcf,
            "mae_fcf": mae_fcf,
            "rmse_rir": rmse_rir,
            "mae_rir": mae_rir,
            "mae_rir_near_failure": mae_rir_nf,
        }
        results.append(result)

        if verbose:
            print(
                f"  Subject {test_subj}: FCF RMSE={rmse_fcf:.2f}%, "
                f"RIR MAE(near-fail)={mae_rir_nf:.2f} reps"
            )

    return pd.DataFrame(results)


if __name__ == "__main__":
    # Quick architecture check
    print("=== Model 4A: DualHeadMLP ===")
    mlp = DualHeadMLP(input_dim=13, hidden_dim=32)
    print(f"  Parameters: {mlp.count_params()}")
    x = torch.randn(4, 13)
    fcf, rir = mlp(x)
    print(f"  FCF output shape: {fcf.shape}, range: [{fcf.min():.3f}, {fcf.max():.3f}]")
    print(f"  RIR output shape: {rir.shape}, range: [{rir.min():.3f}, {rir.max():.3f}]")

    print("\n=== Model 4B: DualHeadCNNGRU ===")
    cnn_gru = DualHeadCNNGRU(input_dim=13, window_size=5, conv_dim=32, gru_dim=16)
    print(f"  Parameters: {cnn_gru.count_params()}")
    x_seq = torch.randn(4, 5, 13)
    fcf, rir = cnn_gru(x_seq)
    print(f"  FCF output shape: {fcf.shape}, range: [{fcf.min():.3f}, {fcf.max():.3f}]")
    print(f"  RIR output shape: {rir.shape}, range: [{rir.min():.3f}, {rir.max():.3f}]")

    print("\n=== DualHeadLoss ===")
    criterion = DualHeadLoss(lambda_fcf=0.7)
    loss = criterion(fcf, torch.rand_like(fcf), rir, torch.rand_like(rir) * 10)
    print(f"  Combined loss: {loss.item():.4f}")
