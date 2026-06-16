"""
Learned GNN baseline vs. rule-based WCC under adversarial evasion (B6).

Question: does a *learned* graph detector resist FullEvasion better than the
rule-based WCC the paper studies? We implement a 2-layer GCN (Kipf & Welling)
from scratch in PyTorch (no torch-geometric dependency) for node-level fraud
classification, train it on clean graphs, and evaluate fraud-USER recall under
FullEvasion across budgets — alongside WCC's user-level recall for an apples-to-
apples comparison.

Hypothesis: the GCN relies on the same shared-infrastructure structure WCC does
(ring users connect to high-degree shared infra nodes). FullEvasion removes that
structure, so we expect the GCN to degrade similarly — i.e. the vulnerability is
detector-agnostic and structural, reinforcing the paper's conclusion. We let the
data decide.
"""

import random
from pathlib import Path
import csv

import torch
import torch.nn as nn
import torch.nn.functional as F

from simulate import Scenario
from attacks import FullEvasion

RESULTS_DIR = Path(__file__).parent / "results"
NTYPES = ["User", "Merchant", "Device", "IP"]


def build_tensors(transactions, fraud_users):
    """Return (X features, A_hat normalized adj, labels, user_mask, node_ids)."""
    import networkx as nx

    G = nx.Graph()
    amount = {}
    for tx in transactions:
        for n, t in [
            (tx.user_id, "User"),
            (tx.merchant_id, "Merchant"),
            (tx.device_id, "Device"),
            (tx.ip_address, "IP"),
        ]:
            G.add_node(n, ntype=t)
        G.add_edge(tx.user_id, tx.merchant_id)
        G.add_edge(tx.user_id, tx.device_id)
        G.add_edge(tx.user_id, tx.ip_address)
        amount[tx.user_id] = amount.get(tx.user_id, 0.0) + tx.amount

    nodes = list(G.nodes())
    idx = {n: i for i, n in enumerate(nodes)}
    n = len(nodes)
    # Features: 4-dim node-type one-hot + degree + (normalized) amount
    X = torch.zeros(n, 6)
    for node in nodes:
        i = idx[node]
        t = G.nodes[node]["ntype"]
        X[i, NTYPES.index(t)] = 1.0
        X[i, 4] = G.degree(node)
        X[i, 5] = amount.get(node, 0.0) / 500.0
    X[:, 4] = X[:, 4] / X[:, 4].max().clamp(min=1)

    # Symmetric-normalized adjacency with self-loops
    A = torch.zeros(n, n)
    for u, v in G.edges():
        A[idx[u], idx[v]] = 1.0
        A[idx[v], idx[u]] = 1.0
    A += torch.eye(n)
    deg = A.sum(1)
    dinv = deg.pow(-0.5)
    A_hat = dinv.unsqueeze(1) * A * dinv.unsqueeze(0)

    labels = torch.zeros(n, dtype=torch.long)
    user_mask = torch.zeros(n, dtype=torch.bool)
    for node in nodes:
        if G.nodes[node]["ntype"] == "User":
            user_mask[idx[node]] = True
            if node in fraud_users:
                labels[idx[node]] = 1
    return X, A_hat, labels, user_mask


class GCN(nn.Module):
    def __init__(self, in_dim=6, hid=16, out=2):
        super().__init__()
        self.w1 = nn.Linear(in_dim, hid)
        self.w2 = nn.Linear(hid, out)

    def forward(self, X, A_hat):
        h = F.relu(self.w1(A_hat @ X))
        return self.w2(A_hat @ h)


def train_gcn(seed=0, epochs=200):
    torch.manual_seed(seed)
    sc = Scenario(n_benign_users=30, seed=seed)
    fraud = {u for r in sc.ground_truth for u in r.users}
    X, A_hat, y, mask = build_tensors(sc.transactions, fraud)
    model = GCN()
    opt = torch.optim.Adam(model.parameters(), lr=0.01, weight_decay=5e-4)
    # class weight: fraud (50) vs benign (30) users -> mild balance
    w = torch.tensor([1.0, 1.0])
    for _ in range(epochs):
        model.train()
        opt.zero_grad()
        out = model(X, A_hat)
        loss = F.cross_entropy(out[mask], y[mask], weight=w)
        loss.backward()
        opt.step()
    return model


def eval_recall(model, transactions, fraud_users):
    X, A_hat, y, mask = build_tensors(transactions, fraud_users)
    model.eval()
    with torch.no_grad():
        pred = model(X, A_hat).argmax(1)
    user_pred = pred[mask]
    user_true = y[mask]
    tp = int(((user_pred == 1) & (user_true == 1)).sum())
    fn = int(((user_pred == 0) & (user_true == 1)).sum())
    fp = int(((user_pred == 1) & (user_true == 0)).sum())
    tn = int(((user_pred == 0) & (user_true == 0)).sum())
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return recall, fpr


def wcc_user_recall(scenario, transactions):
    """Fraction of fraud USERS that land in a flagged WCC component."""
    g = scenario.build_graph(transactions)
    detected_users = (
        set().union(*g.detect_rings_wcc()) if g.detect_rings_wcc() else set()
    )
    fraud = {u for r in scenario.ground_truth for u in r.users}
    return len(detected_users & fraud) / len(fraud)


def run(n_trials=15):
    print("=== B6: Learned GCN vs. rule-based WCC under FullEvasion ===")
    print("Training GCN on clean graphs (5 inits, averaged)...")
    models = [train_gcn(seed=s) for s in range(5)]

    N = 50
    budgets = [int(N * f) for f in [0, 0.2, 0.4, 0.6, 0.8, 1.0]]
    print(
        f"\n{'budget%':>8} {'GCN recall':>11} {'GCN FPR':>9} {'WCC recall(user)':>18}"
    )
    rows = []
    for B in budgets:
        gcn_r = gcn_f = wcc_r = 0.0
        for trial in range(n_trials):
            sc = Scenario(n_benign_users=30, seed=1000 + trial * 7)
            fraud = {u for r in sc.ground_truth for u in r.users}
            txs = (
                FullEvasion().apply(sc, sc.transactions, B)
                if B > 0
                else sc.transactions
            )
            # average over the 5 trained models
            rr = ff = 0.0
            for m in models:
                r, f = eval_recall(m, txs, fraud)
                rr += r
                ff += f
            gcn_r += rr / len(models)
            gcn_f += ff / len(models)
            wcc_r += wcc_user_recall(sc, txs)
        gcn_r /= n_trials
        gcn_f /= n_trials
        wcc_r /= n_trials
        print(f"{B / N:>7.0%} {gcn_r:>11.3f} {gcn_f:>9.3f} {wcc_r:>18.3f}")
        rows.append(
            {
                "budget_pct": round(B / N, 3),
                "gcn_recall": round(gcn_r, 4),
                "gcn_fpr": round(gcn_f, 4),
                "wcc_user_recall": round(wcc_r, 4),
            }
        )
    return rows


def make_figure(rows):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    x = [100 * r["budget_pct"] for r in rows]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(
        x,
        [r["gcn_recall"] for r in rows],
        "o-",
        label="GCN (learned) fraud-user recall",
    )
    ax.plot(
        x,
        [r["wcc_user_recall"] for r in rows],
        "s-",
        label="WCC (rule-based) fraud-user recall",
    )
    ax.set_xlabel("Adversarial budget (% fully evaded)")
    ax.set_ylabel("Fraud-user recall")
    ax.set_title("Learned GCN vs. rule-based WCC under FullEvasion")
    ax.set_ylim(-0.02, 1.05)
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    out = RESULTS_DIR / "gnn_vs_wcc.png"
    RESULTS_DIR.mkdir(exist_ok=True)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    print(f"  Saved figure -> {out}")


def save_csv(rows, path):
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    rows = run()
    save_csv(rows, RESULTS_DIR / "gnn_vs_wcc.csv")
    make_figure(rows)
