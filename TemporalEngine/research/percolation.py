"""
Closed-form coverage model for WCC fraud-ring detection under full evasion.

THEORY
------
A ground-truth ring has k users. Detection matches a recovered component to the
ring by user-only IoU (Jaccard) with threshold theta (see simulate.evaluate_detection).
Under FullEvasion, an attacked user is severed from all shared infrastructure and
leaves the ring's connected component; the remaining r = k - x users stay mutually
connected through the still-shared infrastructure. The recovered component's user
set is therefore a subset of the ring, so

        IoU = r / k = (k - x) / k.

The ring is detected iff IoU >= theta, i.e.

        r >= ceil(theta * k)   <=>   x <= k - ceil(theta * k).

Let m = k - ceil(theta * k) be the per-ring evasion tolerance (max users that may
be evaded while still detected). The adversary spends a global budget B by choosing
B of the N total fraud users uniformly at random. The number x of a given ring's k
users that fall in the budget is Hypergeometric(N, k, B), so the EXPECTED RECALL
(fraction of rings detected) is the hypergeometric tail

        Recall(B) = P[ Hypergeom(N, k, B) <= m ]
                  = sum_{x=0}^{m} C(k, x) C(N-k, B-x) / C(N, B).

This is a parameter-free prediction: given (N, k, theta) it outputs the entire
recall-vs-budget curve with NO fitting. Compare to results/adversarial.csv.
"""

from math import comb, ceil
from pathlib import Path
import csv

RESULTS_DIR = Path(__file__).parent / "results"


def evasion_tolerance(k: int, theta: float) -> int:
    """Max users that may be fully evaded while the ring is still detected."""
    return k - ceil(theta * k)


def predicted_recall(B: int, N: int, k: int, theta: float = 0.5) -> float:
    """Closed-form expected recall under FullEvasion at global budget B."""
    m = evasion_tolerance(k, theta)
    if m < 0:
        return 0.0
    total = comb(N, B)
    p = 0.0
    for x in range(0, m + 1):
        if 0 <= B - x <= N - k:
            p += comb(k, x) * comb(N - k, B - x) / total
    return p


def recall_curve(N: int, k: int, theta: float = 0.5, step: int = 1):
    return [(B, predicted_recall(B, N, k, theta)) for B in range(0, N + 1, step)]


def predicted_recall_mixed(ring_sizes, N: int, B: int, theta: float = 0.5) -> float:
    """
    Generalized coverage model for a population of rings with HETEROGENEOUS sizes
    (the realistic case). Expected recall = mean over rings of the per-ring
    survival probability under a global budget B spread over N total fraud users:

        Recall = (1/R) * sum_r P[ Hypergeom(N, k_r, B) <= m_r ],  m_r = k_r-ceil(theta*k_r)

    This is the form needed to apply the theory to a real dataset, where ring
    sizes come from the data rather than a fixed k.
    """
    if not ring_sizes:
        return 0.0
    total = 0.0
    for k in ring_sizes:
        m = k - ceil(theta * k)
        total += sum(
            comb(k, x) * comb(N - k, B - x) / comb(N, B)
            for x in range(0, m + 1)
            if 0 <= B - x <= N - k
        )
    return total / len(ring_sizes)


def critical_budget_fraction(k: int, theta: float = 0.5) -> float:
    """
    Budget fraction at which expected per-ring evasion equals the tolerance,
    i.e. the centre of the transition: E[x] = B/N * k = m  =>  B/N = m/k.
    """
    return evasion_tolerance(k, theta) / k


def validate_against_csv(N: int = 50, k: int = 5, theta: float = 0.5) -> None:
    """Print predicted vs measured recall for the full_evasion rows of adversarial.csv."""
    path = RESULTS_DIR / "adversarial.csv"
    print(
        f"Coverage model:  N={N}, k={k}, theta={theta}, "
        f"tolerance m={evasion_tolerance(k, theta)}, "
        f"critical budget ~{critical_budget_fraction(k, theta):.0%}"
    )
    print("-" * 60)
    print(
        f"{'budget':>6} {'budget%':>8} {'predicted':>10} {'measured':>10} {'abs.err':>8}"
    )
    if not path.exists():
        print(f"(run evaluate.py first to generate {path})")
        return
    with open(path) as f:
        rows = [r for r in csv.DictReader(f) if r["strategy"] == "full_evasion"]
    # include the baseline (budget 0) as the anchor
    print(
        f"{0:>6} {0.0:>7.0%} {predicted_recall(0, N, k, theta):>10.3f} "
        f"{1.000:>10.3f} {abs(predicted_recall(0, N, k, theta) - 1.0):>8.3f}"
    )
    max_err = 0.0
    for r in rows:
        B = int(r["budget"])
        meas = float(r["recall"])
        pred = predicted_recall(B, N, k, theta)
        err = abs(pred - meas)
        max_err = max(max_err, err)
        print(f"{B:>6} {B / N:>7.0%} {pred:>10.3f} {meas:>10.3f} {err:>8.3f}")
    print("-" * 60)
    print(f"max abs error across all budgets: {max_err:.3f}")


def make_figure(N: int = 50, k: int = 5, theta: float = 0.5) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not available; skipping figure")
        return

    curve = recall_curve(N, k, theta)
    xs = [100 * B / N for B, _ in curve]
    ys = [r for _, r in curve]

    measured = []
    path = RESULTS_DIR / "adversarial.csv"
    if path.exists():
        with open(path) as f:
            for r in csv.DictReader(f):
                if r["strategy"] == "full_evasion":
                    measured.append((100 * int(r["budget"]) / N, float(r["recall"])))
        measured = [(0.0, 1.0)] + measured

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, "-", lw=2, label=f"Coverage model (k={k}, θ={theta}, no fit)")
    if measured:
        ax.plot(
            [x for x, _ in measured],
            [y for _, y in measured],
            "o",
            ms=7,
            label="Measured (30 MC trials)",
        )
    ax.axvline(
        100 * critical_budget_fraction(k, theta),
        ls="--",
        c="grey",
        lw=1,
        label=f"Predicted transition (~{critical_budget_fraction(k, theta):.0%})",
    )
    ax.set_xlabel("Adversarial budget (% of ring members fully evaded)")
    ax.set_ylabel("Ring-detection recall")
    ax.set_title("Full evasion: closed-form coverage model vs. measurement")
    ax.set_ylim(-0.02, 1.05)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    out = RESULTS_DIR / "percolation_fit.png"
    RESULTS_DIR.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"  Saved figure -> {out}")


if __name__ == "__main__":
    validate_against_csv()
    make_figure()
