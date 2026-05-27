"""
Differential Privacy experiment for TemporalEngine velocity detection.

Replicates the VelocityDetector logic from processor.py and wraps it with
calibrated Laplace noise. Measures the privacy-utility tradeoff:
  - Privacy:  epsilon (lower = more private)
  - Utility:  fraction of HIGH-velocity users still correctly flagged

The Laplace mechanism adds noise ~ Lap(sensitivity / epsilon) to the two
velocity statistics: tx_count_5m and tx_sum_5m.

Global sensitivity:
  - count: 1  (adding/removing one user changes count by at most 1)
  - sum:   MAX_AMOUNT  (adding/removing one transaction changes sum by at most max_amount)
"""
import random
import math
from dataclasses import dataclass
from typing import List, Dict, Tuple


# Mirrors VelocityDetector thresholds in processor.py
COUNT_THRESHOLD = 5
SUM_THRESHOLD   = 1000.0
MAX_AMOUNT      = 500.0   # matches producer.py range


@dataclass
class UserWindow:
    """Simulates one user's 5-minute transaction window."""
    user_id: str
    tx_count: int
    tx_sum: float

    @property
    def true_label(self) -> str:
        return "HIGH" if (self.tx_count > COUNT_THRESHOLD or self.tx_sum > SUM_THRESHOLD) else "NORMAL"


def laplace_noise(sensitivity: float, epsilon: float) -> float:
    """Sample from Lap(sensitivity / epsilon) using the inverse CDF method."""
    b = sensitivity / epsilon
    u = random.uniform(-0.5, 0.5)
    return -b * math.copysign(1, u) * math.log(1 - 2 * abs(u))


def noisy_velocity_flag(window: UserWindow, epsilon: float) -> str:
    """Apply DP noise to both velocity statistics and re-evaluate the flag."""
    noisy_count = window.tx_count + laplace_noise(sensitivity=1.0,        epsilon=epsilon)
    noisy_sum   = window.tx_sum   + laplace_noise(sensitivity=MAX_AMOUNT,  epsilon=epsilon)
    return "HIGH" if (noisy_count > COUNT_THRESHOLD or noisy_sum > SUM_THRESHOLD) else "NORMAL"


def generate_windows(
    n_high: int = 200,
    n_normal: int = 200,
    seed: int = 42,
) -> List[UserWindow]:
    """
    Generate synthetic user windows with known true labels for evaluation.
    HIGH windows are clearly above threshold; NORMAL windows are below.
    """
    random.seed(seed)
    windows = []

    for i in range(n_high):
        # Deliberately above threshold to make them unambiguous ground truth
        count = random.randint(COUNT_THRESHOLD + 1, COUNT_THRESHOLD + 10)
        total = round(random.uniform(SUM_THRESHOLD + 50, SUM_THRESHOLD + 500), 2)
        windows.append(UserWindow(f"high_u{i}", count, total))

    for i in range(n_normal):
        count = random.randint(1, COUNT_THRESHOLD - 1)
        total = round(random.uniform(10, SUM_THRESHOLD - 50), 2)
        windows.append(UserWindow(f"normal_u{i}", count, total))

    return windows


def run_dp_experiment(
    epsilon_values: List[float] = None,
    n_trials: int = 50,
    n_high: int = 200,
    n_normal: int = 200,
    seed: int = 42,
) -> List[Dict]:
    """
    For each epsilon, run n_trials noisy evaluations and average the metrics.

    Returns list of dicts with keys:
      epsilon, tpr (true positive rate), fpr (false positive rate),
      fnr (false negative rate), accuracy
    """
    if epsilon_values is None:
        epsilon_values = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 50.0]

    windows = generate_windows(n_high=n_high, n_normal=n_normal, seed=seed)
    results = []

    for eps in epsilon_values:
        tp_acc = fp_acc = fn_acc = tn_acc = 0

        for _ in range(n_trials):
            for w in windows:
                predicted = noisy_velocity_flag(w, eps)
                true      = w.true_label
                if true == "HIGH"   and predicted == "HIGH":   tp_acc += 1
                elif true == "HIGH" and predicted == "NORMAL": fn_acc += 1
                elif true == "NORMAL" and predicted == "HIGH": fp_acc += 1
                else:                                          tn_acc += 1

        total = n_trials * len(windows)
        tpr  = tp_acc / (tp_acc + fn_acc) if (tp_acc + fn_acc) > 0 else 0.0
        fpr  = fp_acc / (fp_acc + tn_acc) if (fp_acc + tn_acc) > 0 else 0.0
        fnr  = fn_acc / (fn_acc + tp_acc) if (fn_acc + tp_acc) > 0 else 0.0
        acc  = (tp_acc + tn_acc) / total

        results.append({
            "epsilon": eps,
            "tpr": round(tpr, 4),
            "fpr": round(fpr, 4),
            "fnr": round(fnr, 4),
            "accuracy": round(acc, 4),
        })

    return results
