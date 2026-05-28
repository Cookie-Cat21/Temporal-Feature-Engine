# arXiv Submission Metadata

For: https://arxiv.org/submit

---

## Title

Adversarial Robustness and Privacy-Utility Tradeoffs in Real-Time Graph-Based Fraud Ring Detection

## Authors

Ovindu Karunaratne

## Primary subject

cs.CR (Cryptography and Security)

## Secondary subjects

cs.LG (Machine Learning), cs.DB (Databases)

---

## Abstract (≈200 words — paste into the arXiv abstract field)

Weakly Connected Component (WCC) graph analysis is the dominant technique
for real-time fraud ring detection in production streaming pipelines. Prior
adversarial work on community detection targets learned models over
single-relation static social graphs; the rule-based, multi-relational WCC
detectors actually deployed in financial fraud systems remain largely
unstudied. We introduce TemporalEngine, a production-grade fraud detection
platform built on Apache Flink, Memgraph, and LangGraph, and use it as an
experimental testbed for two questions. First, how does WCC ring detection
degrade under a white-box adversary that acts transaction-by-transaction
across three independent connection channels (devices, IPs, merchants)?
Second, what is the privacy-utility tradeoff when Laplace differential
privacy is applied to the co-located velocity detector?

Across 30 Monte Carlo trials per configuration, we identify a multi-channel
redundancy effect absent from prior single-relation analyses: severing any
single channel never reduces recall, even at 100% adversarial budget. Only
simultaneous evasion of all three channels degrades detection, with a sharp
phase transition between 60–80% budget. For the velocity detector under
Laplace noise, we identify ε≈5 as the practical operating point (TPR=1.0,
FPR=0.027). Code, simulation harness, and results CSVs are open-sourced.

---

## Comments field (optional, shown on arXiv abstract page)

12 pages, 3 tables. Code and reproducibility artifacts at
https://github.com/Cookie-Cat21/Temporal-Feature-Engine

---

## ACM categories (if asked)

- Security and privacy → Intrusion/anomaly detection and malware mitigation
- Information systems → Data stream mining
- Computing methodologies → Adversarial learning

---

## License recommendation

CC BY 4.0 — allows reuse with attribution, standard for ML/security
preprints, no submission cost.

---

## Pre-submission checklist

- [ ] Compile paper.tex locally with pdflatex + bibtex + pdflatex + pdflatex
- [ ] Verify all 12 citations render (run audit_cites.py)
- [ ] Confirm GitHub repo is public and the README points to research/
- [ ] Replace email in paper.tex \author block if you want a different one
- [ ] Upload paper.tex + refs.bib as a single .zip or .tar.gz to arXiv
- [ ] Pick the moderation track: cs.CR moderators are responsive within 1–3
      business days for first-time submitters

## Strategic notes

- arXiv first, conference second. KDD deadline is typically February;
  ACM SIGMOD May; IEEE S&P early summer. Posting on arXiv first
  establishes priority date and is allowed by all three venues.
- For your first submission you'll need an endorsement from another
  cs.CR author who has posted recently. If you don't have a contact,
  the autoendorsement system kicks in after your first paper is
  accepted in another category, OR you can email moderators.
- Once posted, the paper gets a permanent arXiv ID like 2605.NNNNN.
  Add this ID to the GitHub README and to refs.bib for future citing.
