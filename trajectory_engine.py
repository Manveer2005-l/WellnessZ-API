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
    Positive effect_size indicates health improvement.
    """
    logger.debug(f"Calculating trajectory for {len(df_visits)} visits")
    
    df_visits = df_visits.sort_values("date")

    baseline = predict_clients(df_visits)

    first = baseline.iloc[0]
    last = baseline.iloc[-1]

    hd_delta = last.health_distance - first.health_distance
    diab_delta = last.pred_diab - first.pred_diab
    bp_delta = last.pred_bp - first.pred_bp
    lip_delta = last.pred_lip - first.pred_lip

    effect_size = -(hd_delta + diab_delta + bp_delta + lip_delta)
    trajectory = "Improvement" if effect_size > 0 else "Decline"
    
    logger.info(f"Trajectory: {trajectory} (effect_size={effect_size:.3f})")

    return {
        "effect_size": float(effect_size),
        "trajectory": trajectory,
        "visits": len(df_visits)
    }