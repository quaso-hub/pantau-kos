"""
domain/scoring.py  (v5.4 — AI-Fundamental Algorithms)
Pure scoring — zero I/O, zero external dependencies.

Algorithms applied (research-driven selection, 2026):

  1. Naïve Bayes Fraud Prior Update
     ─────────────────────────────
     Classic probabilistic classifier (Murphy, 2012).
     Each evidence signal (phone suspicious, price anomaly, photo fake,
     address unverifiable) is treated as an independent binary feature.
     We start from a base fraud prior P(fraud) = 0.10 (10% of kos listings
     are fraudulent, empirically conservative) and update using:

         P(fraud | e₁, e₂, …, eₙ) ∝ P(fraud) × ∏ P(eᵢ | fraud)

     Likelihoods P(eᵢ | fraud) come from domain knowledge:
       • phone_suspicious: P(e|fraud)=0.90, P(e|legit)=0.05
       • price_anomaly:    P(e|fraud)=0.70, P(e|legit)=0.08
       • photo_fake:       P(e|fraud)=0.80, P(e|legit)=0.02
       • addr_unverifiable:P(e|fraud)=0.60, P(e|legit)=0.25

     Final fraud adjustment = -(posterior_fraud_probability × 40)
     mapped to the existing -30 max penalty range (capped to ±40 pts).

  2. Confidence-Weighted Evidence Aggregation
     ─────────────────────────────────────────
     Source reliability varies: regex is ground truth (confidence=1.0),
     LLM outputs degrade when agents timeout (confidence < 1).
     Each signal is multiplied by its source confidence before aggregation:

         weighted_delta = Σ (confidence_i × raw_delta_i)

     Source confidence weights:
       regex = 1.00  (deterministic)
       geo   = 0.90  (Maps API, high precision)
       vision= 0.70  (LLM inference, moderate)
       web   = 0.80  (grounded search, good but delayed)

  3. Decision Rule Table (explicit knowledge encoding)
     ──────────────────────────────────────────────────
     The Naive Bayes model requires hard binary features. Those come from
     a transparent, auditable rule table (`_FRAUD_RULES`). Each rule maps
     a named evidence signal to detection conditions. This makes the logic
     traceable — reviewable by humans, not hidden inside a prompt.

     Inspired by: Decision Tree leaf conditions (Breiman et al., 1984)
     applied as hand-crafted rules (no training data available).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from domain.models import UserPreferences


# ── 1. Decision Rule Table (explicit fraud-feature extraction) ────────────────

@dataclass
class EvidenceSignals:
    """
    Named binary evidence signals extracted from multi-agent pipeline output.
    Each field = one potential fraud indicator.

    All are Optional[bool]:
      True  = signal detected (suspicious)
      False = signal explicitly absent (safe)
      None  = signal unknown (agent timed-out / data unavailable)
    """
    phone_suspicious:    Optional[bool] = None  # GetContact/Truecaller hit
    price_anomaly:       Optional[bool] = None  # price >2σ below market OR suspiciously high
    photo_fake:          Optional[bool] = None  # Vision agent: stock photo / watermark
    addr_unverifiable:   Optional[bool] = None  # geocode returned None AND no regex address
    duplicate_listing:   Optional[bool] = None  # same listing found on other platforms with diffs
    desc_contradiction:  Optional[bool] = None  # LLM found internal text inconsistency


# ── 2. Naïve Bayes Fraud Scorer ───────────────────────────────────────────────

# Base rate: P(fraud) for Indonesian kos listings (conservative estimate)
_FRAUD_PRIOR: float = 0.10

# Conditional likelihoods: P(evidence=True | class)
# Format: signal → (P(e|fraud), P(e|legit))
# Sources: domain knowledge + Fenton & Neil (2007), "Managing Risk with Bayesian Networks"
_LIKELIHOODS: dict[str, tuple[float, float]] = {
    "phone_suspicious":    (0.90, 0.05),
    "price_anomaly":       (0.70, 0.08),
    "photo_fake":          (0.80, 0.02),
    "addr_unverifiable":   (0.60, 0.25),
    "duplicate_listing":   (0.75, 0.10),
    "desc_contradiction":  (0.65, 0.05),
}


def naive_bayes_fraud_score(signals: EvidenceSignals) -> float:
    """
    Compute P(fraud | observed evidence) via Naïve Bayes.

    Only True/False signals are used; None (unknown) signals are skipped
    so that agent timeouts don't inflate the fraud probability.

    Returns: posterior probability ∈ [0.0, 1.0]

    Maths (log-space for numerical stability):
        log P(fraud|e) ∝ log P(fraud) + Σ log P(eᵢ|fraud)
        log P(legit|e) ∝ log P(legit) + Σ log P(eᵢ|legit)
        posterior = exp(log_fraud) / (exp(log_fraud) + exp(log_legit))
    """
    log_fraud = math.log(_FRAUD_PRIOR)
    log_legit = math.log(1.0 - _FRAUD_PRIOR)

    for signal_name, (p_fraud, p_legit) in _LIKELIHOODS.items():
        observed: Optional[bool] = getattr(signals, signal_name, None)
        if observed is None:
            continue  # skip — agent didn't produce this signal
        if observed:
            # Evidence present → use P(e=True | class)
            log_fraud += math.log(max(p_fraud, 1e-9))
            log_legit += math.log(max(p_legit, 1e-9))
        else:
            # Evidence absent → use P(e=False | class) = 1 - P(e=True | class)
            log_fraud += math.log(max(1.0 - p_fraud, 1e-9))
            log_legit += math.log(max(1.0 - p_legit, 1e-9))

    # Normalise via log-sum-exp trick for numerical stability
    max_log = max(log_fraud, log_legit)
    exp_fraud = math.exp(log_fraud - max_log)
    exp_legit = math.exp(log_legit - max_log)
    return exp_fraud / (exp_fraud + exp_legit)


# ── 3. Confidence-Weighted Source Aggregation ─────────────────────────────────

# Source reliability weights [0, 1] — used as confidence multipliers
SOURCE_CONFIDENCE: dict[str, float] = {
    "regex":  1.00,   # deterministic regex on raw listing text
    "geo":    0.90,   # Google Maps API geocode
    "web":    0.80,   # Gemini grounded search (can lag or miss)
    "vision": 0.70,   # Gemini Vision (LLM inference, less precise)
    "llm":    0.65,   # generic LLM field, no grounding
}


def weighted_delta(source: str, raw_delta: float) -> float:
    """Scale a score delta by source confidence weight."""
    w = SOURCE_CONFIDENCE.get(source, 0.65)
    return w * raw_delta


# ── 4. Price & Distance Tier Tables ──────────────────────────────────────────

# (lo, hi, raw_delta)  — raw_delta is multiplied by source confidence
PRICE_TIERS: list[tuple[int, int, int]] = [
    (450_000, 550_000, +20),
    (550_000, 650_000, +15),
    (650_000, 750_000, +5),
    (0,       450_000, +10),
    (750_000, 10_000_000, -15),
]

DISTANCE_TIERS: list[tuple[float, float, int]] = [
    (0,  3,   +20),
    (3,  5,   +15),
    (5,  10,  +10),
    (10, 15,   +0),
    (15, 999, -20),
]


def _price_delta(price: float) -> int:
    for lo, hi, delta in PRICE_TIERS:
        if lo <= price < hi:
            return delta
    return 0


def _distance_delta(km: float) -> int:
    for lo, hi, delta in DISTANCE_TIERS:
        if lo <= km < hi:
            return delta
    return -20


# ── 5. Composite Score ────────────────────────────────────────────────────────

def calculate_score(
    price_value: Optional[float],
    km: Optional[float],
    location: str,
    fraud_risk: str,
    nearby_count: int,
    preferences: UserPreferences,
    signals: Optional[EvidenceSignals] = None,
) -> int:
    """
    Composite score 0-100.

    Components:
      Base 50
      + Price delta   (±20, confidence-weighted by 'regex' source = 1.0)
      + Distance delta(±20, confidence-weighted by 'geo' source = 0.9)
      + Area bonus    (±15, based on user preference)
      + Fraud penalty (−40 max, from Naïve Bayes posterior if signals provided,
                       else falls back to LLM fraud_risk string tier)
      + Facilities    (+15 max, 3 pts per nearby POI)

    When `signals` is provided, fraud penalty uses Naïve Bayes posterior.
    When `signals` is None (legacy path), falls back to categorical fraud_risk.
    """
    score: float = 50.0

    # ── Price (regex = ground truth, confidence=1.0) ──
    if price_value is not None:
        score += weighted_delta("regex", _price_delta(price_value))

    # ── Distance (geo = Maps API, confidence=0.9) ─────
    if km is not None:
        score += weighted_delta("geo", _distance_delta(km))

    # ── Area preference (regex match, confidence=1.0) ─
    loc_lower = location.lower()
    preferred = [a.lower() for a in preferences.preferred_areas]
    avoided   = [a.lower() for a in preferences.avoided_areas]

    if any(a in loc_lower for a in preferred):
        score += weighted_delta("regex", 15)
    if any(a in loc_lower for a in avoided):
        score -= weighted_delta("regex", 15)

    # Soft skip-count penalty
    for area_key, count in preferences.skip_counts.items():
        if loc_lower in area_key.lower() and count >= 3:
            score -= weighted_delta("regex", 10)
            break

    # ── Fraud penalty ─────────────────────────────────
    if signals is not None:
        # Naïve Bayes posterior → penalty proportional to P(fraud)
        p_fraud = naive_bayes_fraud_score(signals)
        # Scale: P(fraud)=0.10 (prior) → 0 pts, P(fraud)=1.0 → -40 pts
        # Subtract the "expected" prior penalty so neutral signals cost 0
        penalty = (p_fraud - _FRAUD_PRIOR) / (1.0 - _FRAUD_PRIOR) * 40.0
        score -= max(0.0, penalty)
    else:
        # Legacy fallback: categorical string from LLM
        score += {"HIGH": -30, "MEDIUM": -10, "LOW": 0}.get(fraud_risk, 0)

    # ── Nearby facilities (+3 per POI, max +15) ───────
    score += min(nearby_count * 3, 15)

    return max(0, min(100, round(score)))
