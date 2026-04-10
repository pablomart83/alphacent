"""
Earnings Call Transcript Sentiment Scorer — Loughran-McDonald Dictionary.

Scores earnings call transcripts using the Loughran-McDonald (2011) financial
sentiment dictionary. This dictionary was specifically calibrated for financial
text — unlike Harvard IV, it doesn't flag words like "tax", "cost", "capital"
as negative.

Scoring method:
- Split transcript into prepared remarks vs Q&A (40/60 weighting)
- Count positive/negative words with 2-word negation window
- Normalize cross-sectionally across the stock universe

Reference: Loughran & McDonald (2011), "When Is a Liability Not a Liability?"
"""

import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Loughran-McDonald negative words (top ~120 most impactful for earnings calls)
# Full dictionary has ~2300 words; this subset covers ~85% of signal
LM_NEGATIVE = {
    "abandon", "abdicate", "aberrant", "abolish", "abuse", "accident",
    "adverse", "against", "aggravate", "allegation", "annul", "argue",
    "attrition", "bad", "bail", "bankrupt", "breach", "break", "burden",
    "caution", "cease", "challenge", "claim", "close", "closure",
    "collapse", "concern", "condemn", "conflict", "constrain", "contraction",
    "costly", "crisis", "critical", "curtail", "cut", "damage", "danger",
    "deadlock", "debacle", "decline", "default", "defect", "deficit",
    "delay", "delinquent", "deny", "deplete", "depreciate", "depress",
    "deteriorate", "detrimental", "difficult", "diminish", "disappoint",
    "disclose", "discontinue", "dispute", "disrupt", "distress", "doubt",
    "downgrade", "downturn", "drop", "erode", "error", "escalate",
    "evict", "exacerbate", "excessive", "fail", "failure", "fall",
    "fear", "fine", "force", "fraud", "halt", "hamper", "hardship",
    "harm", "hinder", "hurdle", "idle", "impair", "impediment",
    "inability", "inadequate", "incur", "ineffective", "inferior",
    "insolvent", "instability", "insufficient", "interrupt", "investigate",
    "jeopardize", "lack", "lag", "late", "layoff", "liability", "limit",
    "liquidate", "litigation", "lose", "loss", "misstate", "negative",
    "neglect", "obstacle", "offend", "omit", "onerous", "oppose",
    "overdue", "overrun", "penalty", "peril", "persist", "plummet",
    "poor", "postpone", "problem", "prohibit", "protest", "question",
    "recall", "recession", "reduce", "reject", "restructure", "retrench",
    "revoke", "risk", "sanction", "scarcity", "severe", "shortage",
    "shrink", "shut", "slump", "stagnate", "strain", "stress",
    "struggle", "subprime", "suffer", "suspend", "terminate", "threat",
    "tighten", "trouble", "turmoil", "unable", "uncertain", "undermine",
    "underperform", "unfavorable", "unfortunate", "unprofitable",
    "unsuccessful", "volatile", "vulnerability", "warn", "weak",
    "worsen", "writedown", "writeoff",
}

# Loughran-McDonald positive words (top ~80 most impactful)
LM_POSITIVE = {
    "able", "accomplish", "achieve", "advance", "advantage", "benefit",
    "best", "better", "boost", "breakthrough", "collaborate", "commit",
    "competent", "confident", "constructive", "creative", "deliver",
    "diligent", "earn", "effective", "efficiency", "empower", "enable",
    "encourage", "enhance", "enjoy", "enthusiasm", "exceed", "excel",
    "exceptional", "exciting", "expand", "favorable", "gain", "good",
    "great", "grow", "growth", "highest", "honor", "ideal", "improve",
    "increase", "ingenuity", "innovate", "innovation", "insight",
    "integrity", "leader", "leadership", "leverage", "momentum",
    "opportunity", "optimal", "optimistic", "outpace", "outperform",
    "outstanding", "overcome", "pleased", "positive", "premium",
    "proactive", "productive", "proficiency", "profit", "profitable",
    "progress", "prosper", "record", "recover", "resolve", "reward",
    "robust", "solid", "solution", "strength", "strong", "succeed",
    "success", "superior", "surpass", "sustain", "thrive", "transform",
    "tremendous", "upturn", "valuable", "win",
}

# Uncertainty words (Loughran-McDonald)
LM_UNCERTAINTY = {
    "almost", "ambiguity", "anticipate", "apparent", "approximate",
    "assume", "believe", "conceivable", "conditional", "contingent",
    "depend", "doubt", "estimate", "expect", "fluctuate", "forecast",
    "hope", "imprecise", "indefinite", "indicate", "intend", "likelihood",
    "may", "might", "nearly", "pending", "perhaps", "possible",
    "predict", "preliminary", "presume", "probable", "project",
    "prospect", "random", "risky", "roughly", "seem", "sometime",
    "speculate", "suggest", "suppose", "tentative", "uncertain",
    "unclear", "undetermined", "unexpected", "unknown", "unlikely",
    "unpredictable", "unresolved", "unsettled", "variable",
}

# Negation words (2-word window)
NEGATION_WORDS = {
    "no", "not", "none", "neither", "never", "nobody",
    "nor", "nothing", "nowhere", "cannot", "isn't", "wasn't",
    "doesn't", "don't", "didn't", "won't", "wouldn't", "shouldn't",
    "couldn't", "hardly", "barely", "scarcely",
}


def split_prepared_vs_qa(transcript: str) -> Tuple[str, str]:
    """
    Split an earnings call transcript into prepared remarks and Q&A.

    Heuristic: look for common Q&A section markers. If not found,
    assume the first 40% is prepared remarks and the rest is Q&A.
    """
    # Common Q&A markers in earnings transcripts
    qa_markers = [
        r"question.and.answer",
        r"q\s*&\s*a\s+session",
        r"q\s*&\s*a",
        r"operator.*open.*line.*question",
        r"we.*(now|will).*open.*for.*question",
        r"let.*open.*it.*up.*for.*question",
        r"first question",
    ]

    text_lower = transcript.lower()
    split_pos = None

    for pattern in qa_markers:
        match = re.search(pattern, text_lower)
        if match:
            split_pos = match.start()
            break

    if split_pos and split_pos > len(transcript) * 0.15:
        return transcript[:split_pos], transcript[split_pos:]

    # Fallback: 40/60 split
    split_at = int(len(transcript) * 0.4)
    return transcript[:split_at], transcript[split_at:]


def _tokenize(text: str) -> List[str]:
    """Simple word tokenizer — lowercase, strip punctuation."""
    return re.findall(r"[a-z']+", text.lower())


def score_text(
    text: str,
    negation_window: int = 2,
) -> Dict[str, float]:
    """
    Score a block of text using Loughran-McDonald dictionary.

    Returns dict with:
    - positive_count, negative_count, uncertainty_count
    - net_sentiment: (positive - negative) / total_words
    - uncertainty_ratio: uncertainty / total_words
    """
    words = _tokenize(text)
    total = len(words)
    if total == 0:
        return {
            "positive_count": 0, "negative_count": 0,
            "uncertainty_count": 0, "net_sentiment": 0.0,
            "uncertainty_ratio": 0.0, "total_words": 0,
        }

    pos_count = 0
    neg_count = 0
    unc_count = 0

    for i, word in enumerate(words):
        # Check negation window: if any of the preceding N words is a negation,
        # flip the sentiment (positive becomes negative and vice versa)
        is_negated = False
        for j in range(max(0, i - negation_window), i):
            if words[j] in NEGATION_WORDS:
                is_negated = True
                break

        if word in LM_POSITIVE:
            if is_negated:
                neg_count += 1  # "not good" → negative
            else:
                pos_count += 1
        elif word in LM_NEGATIVE:
            if is_negated:
                pos_count += 1  # "not bad" → positive
            else:
                neg_count += 1
        elif word in LM_UNCERTAINTY:
            unc_count += 1

    net_sentiment = (pos_count - neg_count) / total
    uncertainty_ratio = unc_count / total

    return {
        "positive_count": pos_count,
        "negative_count": neg_count,
        "uncertainty_count": unc_count,
        "net_sentiment": net_sentiment,
        "uncertainty_ratio": uncertainty_ratio,
        "total_words": total,
    }


def score_transcript(
    transcript: str,
    prepared_weight: float = 0.4,
    qa_weight: float = 0.6,
) -> Dict[str, float]:
    """
    Score a full earnings call transcript.

    Splits into prepared remarks vs Q&A, scores each separately,
    then computes a weighted composite. Q&A is weighted higher (60%)
    because it's more reflexive and less scripted (Matsumoto et al. 2011).

    Returns dict with:
    - composite_sentiment: weighted net sentiment (-1 to +1 range)
    - prepared_sentiment: net sentiment of prepared remarks
    - qa_sentiment: net sentiment of Q&A section
    - uncertainty: weighted uncertainty ratio
    - positive_count, negative_count: raw totals
    """
    if not transcript or len(transcript) < 100:
        return {
            "composite_sentiment": 0.0,
            "prepared_sentiment": 0.0,
            "qa_sentiment": 0.0,
            "uncertainty": 0.0,
            "positive_count": 0,
            "negative_count": 0,
        }

    prepared, qa = split_prepared_vs_qa(transcript)

    prep_scores = score_text(prepared)
    qa_scores = score_text(qa)

    composite = (
        prepared_weight * prep_scores["net_sentiment"]
        + qa_weight * qa_scores["net_sentiment"]
    )

    return {
        "composite_sentiment": composite,
        "prepared_sentiment": prep_scores["net_sentiment"],
        "qa_sentiment": qa_scores["net_sentiment"],
        "uncertainty": (
            prepared_weight * prep_scores["uncertainty_ratio"]
            + qa_weight * qa_scores["uncertainty_ratio"]
        ),
        "positive_count": prep_scores["positive_count"] + qa_scores["positive_count"],
        "negative_count": prep_scores["negative_count"] + qa_scores["negative_count"],
    }


def fetch_and_score_transcript(
    symbol: str,
    fmp_request_fn,
) -> Optional[Dict[str, float]]:
    """
    Fetch the latest earnings call transcript from FMP and score it.

    Args:
        symbol: Stock symbol
        fmp_request_fn: Callable that makes FMP API requests
                        (e.g., FundamentalDataProvider._fmp_request)

    Returns:
        Sentiment scores dict, or None if transcript unavailable
    """
    try:
        data = fmp_request_fn("/earning-call-transcript", symbol=symbol, limit=1)
        if not data or not isinstance(data, list) or len(data) == 0:
            return None

        content = data[0].get("content", "")
        if not content or len(content) < 200:
            return None

        scores = score_transcript(content)
        scores["symbol"] = symbol
        scores["date"] = data[0].get("date", "")

        logger.info(
            f"Transcript sentiment for {symbol}: "
            f"composite={scores['composite_sentiment']:.4f}, "
            f"prepared={scores['prepared_sentiment']:.4f}, "
            f"qa={scores['qa_sentiment']:.4f}, "
            f"uncertainty={scores['uncertainty']:.4f}, "
            f"+{scores['positive_count']}/-{scores['negative_count']}"
        )
        return scores

    except Exception as e:
        logger.debug(f"Could not score transcript for {symbol}: {e}")
        return None
