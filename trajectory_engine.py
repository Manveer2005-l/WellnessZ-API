import pandas as pd
import numpy as np
from wellnessz_runtime import predict_clients


def predict_trajectory(df_visits):

    df_visits = df_visits.sort_values("date")

    baseline = predict_clients(df_visits)

    first = baseline.iloc[0]
    last = baseline.iloc[-1]

    hd_delta = last.health_distance - first.health_distance
    diab_delta = last.pred_diab - first.pred_diab
    bp_delta = last.pred_bp - first.pred_bp
    lip_delta = last.pred_lip - first.pred_lip

    effect_size = -(hd_delta + diab_delta + bp_delta + lip_delta)

    return {
        "effect_size": float(effect_size),
        "trajectory": "Improvement" if effect_size > 0 else "Decline",
        "visits": len(df_visits)
    }