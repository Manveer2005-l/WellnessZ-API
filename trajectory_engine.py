# IMPROVEMENT: Added type hints and logging
import pandas as pd
import numpy as np
import logging
from typing import Dict, Any
from wellnessz_runtime import predict_clients

logger = logging.getLogger(__name__)


def predict_trajectory(df_visits: pd.DataFrame) -> Dict[str, Any]:
    """IMPROVEMENT: Added type hints and logging.
    
    Calculate health trajectory across multiple client visits.
    The current rule considers only the change in ``health_distance``:
    - a decrease in ``health_distance`` (moving closer to the ideal) is an
      improvement, regardless of individual risk probabilities.
    - an increase in ``health_distance`` results in a "Decline" trajectory.
    Positive ``effect_size`` corresponds to an improvement.
    If the input contains a "date" column it is used for sorting; otherwise
    the original order is preserved and a warning is logged.
    """
    logger.debug(f"Calculating trajectory for {len(df_visits)} visits")

    if "date" in df_visits.columns:
        df_visits = df_visits.sort_values("date")
    else:
        logger.warning("No 'date' column present; using provided order for trajectory")

    baseline = predict_clients(df_visits)

    first = baseline.iloc[0]
    last = baseline.iloc[-1]

    # compute change in health_distance only (magnitude reduction is improvement)
    hd_delta = last.health_distance - first.health_distance

    # effect size positive when distance decreases (improvement)
    effect_size = -hd_delta
    trajectory = "Improvement" if effect_size > 0 else "Decline"

    logger.info(
        f"Trajectory: {trajectory} (hd_delta={hd_delta:.3f}, effect_size={effect_size:.3f})"
    )

    return {
        "effect_size": float(effect_size),
        "trajectory": trajectory,
        "visits": len(df_visits)
    }