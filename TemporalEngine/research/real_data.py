"""
B7 (part 2): apply the coverage theorem to a REAL dataset (drop-in loader).

Public fraud-graph datasets do not all expose the paper's exact channels
(Device/IP/Merchant), so this loader is channel-agnostic: it ingests any
bipartite "user <-> shared-entity" edge list, builds the connectivity graph,
treats connected components of fraud users as rings, applies node-removal
("full evasion") at a range of budgets, and compares measured recall against the
GENERALIZED coverage model (percolation.predicted_recall_mixed) using the ring
sizes found IN THE DATA.

------------------------------------------------------------------------------
HOW TO OBTAIN A REAL DATASET (then point --csv at it)
------------------------------------------------------------------------------
1. IBM AMLSim / "AMLworld" (synthetic-but-realistic AML transactions)
   https://github.com/IBM/AMLSim  (generator) or Kaggle "ibm-transactions-for-
   anti-money-laundering-aml". Map: account_id -> user_id; each shared
   counterparty / bank / device-like attribute -> an entity row
   (entity_id, entity_type). Label SAR/illicit accounts is_fraud=1.

2. Elliptic2 (2024 Bitcoin AML subgraphs)
   https://arxiv.org/abs/2410.08394 / elliptic.co dataset page. Map: address/
   transaction nodes -> user_id; co-occurrence in a labeled subgraph -> entity.
   Illicit-labeled -> is_fraud=1.

3. Any internal transaction log: emit one row per (user, shared-entity) link.

------------------------------------------------------------------------------
EXPECTED CSV SCHEMAS (either is accepted; auto-detected by header)
------------------------------------------------------------------------------
A) Multi-relational transaction rows (same as the synthetic harness):
     user_id, merchant_id, device_id, ip_address, amount, is_fraud[, ring_id]

B) Generic bipartite edge list (recommended for real data):
     user_id, entity_id, entity_type, is_fraud
   (one row per shared-entity link; entity_type is free text e.g. account/bank/ip)

Usage:
  python real_data.py --demo                 # writes + runs a demo CSV (no download)
  python real_data.py --csv path/to/data.csv [--theta 0.5] [--trials 20]
"""
import argparse
import csv
import random
from pathlib import Path

import networkx as nx

from percolation import predicted_recall_mixed

RESULTS_DIR = Path(__file__).parent / "results"


def load_edges(path):
    """Return (edges, fraud_users) from either accepted schema. edges: (user, entity)."""
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        cols = set(reader.fieldnames or [])
        edges, fraud = [], set()
        if {"user_id", "entity_id"} <= cols:                       # schema B
            for r in reader:
                u, e = r["user_id"], f"{r.get('entity_type','e')}:{r['entity_id']}"
                edges.append((u, e))
                if str(r.get("is_fraud", "0")) in ("1", "True", "true"):
                    fraud.add(u)
        elif "user_id" in cols:                                    # schema A
            for r in reader:
                u = r["user_id"]
                for ch in ("merchant_id", "device_id", "ip_address"):
                    if r.get(ch):
                        edges.append((u, f"{ch}:{r[ch]}"))
                if str(r.get("is_fraud", "0")) in ("1", "True", "true"):
                    fraud.add(u)
        else:
            raise ValueError(f"Unrecognized columns: {cols}")
    return edges, fraud


def build_graph(edges):
    G = nx.Graph()
    for u, e in edges:
        G.add_node(u, kind="user")
        G.add_node(e, kind="entity")
        G.add_edge(u, e)
    return G


def ground_truth_rings(G, fraud_users, min_users=3):
    """Connected components containing >= min_users fraud users -> ring user-sets."""
    rings = []
    for comp in nx.connected_components(G):
        users = {n for n in comp if G.nodes[n].get("kind") == "user" and n in fraud_users}
        if len(users) >= min_users:
            rings.append(users)
    return rings


def detect_rings(G, min_component=4):
    """Baseline WCC: components above size threshold, reduced to their user nodes."""
    out = []
    for comp in nx.connected_components(G):
        if len(comp) > min_component:
            users = {n for n in comp if G.nodes[n].get("kind") == "user"}
            if len(users) >= 2:
                out.append(users)
    return out


def iou_recall(detected, gt, theta):
    matched = set()
    tp = 0
    for d in detected:
        for i, g in enumerate(gt):
            if i in matched:
                continue
            if g and len(d & g) / len(d | g) >= theta:
                tp += 1; matched.add(i); break
    return tp / len(gt) if gt else 0.0


def full_evasion(edges, fraud_users, targets):
    """Rewire every edge of a targeted user to unique entities (severs all channels)."""
    out = []
    c = 0
    for u, e in edges:
        if u in targets:
            out.append((u, f"__evaded_{c}")); c += 1
        else:
            out.append((u, e))
    return out


def run(path, theta=0.5, n_trials=20):
    edges, fraud = load_edges(path)
    G0 = build_graph(edges)
    gt = ground_truth_rings(G0, fraud)
    ring_sizes = [len(r) for r in gt]
    N = sum(ring_sizes)
    fraud_in_rings = set().union(*gt) if gt else set()
    print(f"Loaded {path}: {G0.number_of_nodes()} nodes, {len(fraud)} fraud users, "
          f"{len(gt)} rings (sizes {min(ring_sizes)}-{max(ring_sizes)}, N={N})")
    print(f"{'budget%':>8} {'measured':>10} {'mixed-model':>12} {'abs.err':>8}")
    rows = []
    fraud_list = sorted(fraud_in_rings)
    for f in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0]:
        B = int(f * N)
        meas = 0.0
        for trial in range(n_trials):
            rnd = random.Random(trial * 137)
            targets = set(rnd.sample(fraud_list, B)) if B > 0 else set()
            G = build_graph(full_evasion(edges, fraud, targets))
            meas += iou_recall(detect_rings(G), gt, theta)
        meas /= n_trials
        pred = predicted_recall_mixed(ring_sizes, N, B, theta)
        print(f"{f:>7.0%} {meas:>10.3f} {pred:>12.3f} {abs(meas-pred):>8.3f}")
        rows.append({"budget_pct": f, "measured": round(meas, 4),
                     "mixed_model": round(pred, 4)})
    return rows


def write_demo_csv(path):
    """Emit a schema-B demo CSV from the realistic generator (no download needed)."""
    from realistic import RealisticScenario
    sc = RealisticScenario(seed=7)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "entity_id", "entity_type", "is_fraud"])
        for tx in sc.transactions:
            isf = 1 if tx.is_fraud else 0
            w.writerow([tx.user_id, tx.merchant_id, "merchant", isf])
            w.writerow([tx.user_id, tx.device_id, "device", isf])
            w.writerow([tx.user_id, tx.ip_address, "ip", isf])
    print(f"  Wrote demo dataset -> {path}")


def save_csv(rows, path):
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    print(f"  Saved -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", type=str, default=None)
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--theta", type=float, default=0.5)
    ap.add_argument("--trials", type=int, default=20)
    args = ap.parse_args()

    print("=== B7.2: coverage theorem on a loaded dataset ===")
    path = args.csv
    if args.demo or not path:
        path = RESULTS_DIR / "demo_dataset.csv"
        RESULTS_DIR.mkdir(exist_ok=True)
        write_demo_csv(path)
    rows = run(path, theta=args.theta, n_trials=args.trials)
    save_csv(rows, RESULTS_DIR / "real_data_validation.csv")
