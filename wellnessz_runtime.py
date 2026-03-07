# IMPROVEMENT: Added type hints and logging
import numpy as np
import pandas as pd
import joblib
import os
import logging
from typing import Dict, Callable
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# IMPROVEMENT: Added logging configuration
logger = logging.getLogger(__name__)

# --- Load models
logger.info("Loading ML models...")
proxy_scaler = joblib.load("models/proxy_scaler.joblib")
proxy_model  = joblib.load("models/proxy_model.joblib")
risk_diab    = joblib.load("models/risk_diab.joblib")
risk_bp      = joblib.load("models/risk_bp.joblib")
risk_lip     = joblib.load("models/risk_lip.joblib")
z_star       = np.load("models/z_star.npy")
Z_KEEP       = joblib.load("models/Z_KEEP.joblib")
logger.info("ML models loaded successfully")


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are WellnessZ — an intelligent, calm, premium digital health coach.
You explain physiological results clearly and motivate practical action.
You never mention models or data science.
"""

def predict_clients(df_client: pd.DataFrame) -> pd.DataFrame:
    """IMPROVEMENT: Added type hints and comprehensive logging."""
    logger.debug(f"Processing {len(df_client)} client record(s)")
    df = df_client.copy()

    if "age" not in df.columns:
        logger.debug("Age column missing, using default value 30")
        df["age"] = 30
    if "sex" not in df.columns:
        logger.debug("Sex column missing, using default value 1")
        df["sex"] = 1

    CLIENT_PROXY_MAP: Dict[str, str] = {
        "bmi": "BMXBMI",
        "hm_visceral_fat": "BMDAVSAD",
        "hm_muscle": "BMXARMC",
        "hm_rm": "MGDCGSZ",
        "age": "RIDAGEYR",
        "sex": "RIAGENDR"
    }

    for k in CLIENT_PROXY_MAP.keys():
        if k not in df.columns:
            logger.debug(f"Column {k} missing, initializing to 0")
            df[k] = 0

    X = df[list(CLIENT_PROXY_MAP.keys())].rename(columns=CLIENT_PROXY_MAP)

    # IMPROVEMENT: Added logging for data preprocessing
    logger.debug("Cleaning and standardizing feature values")
    for col in X.columns:
        X[col] = (
            X[col].astype(str)
            .str.replace("%", "", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip()
        )

    X = X.apply(pd.to_numeric, errors="coerce")
    X["MGDCGSZ"] = np.log1p(X["MGDCGSZ"].clip(lower=0))

    valid = X.notna().all(axis=1)
    n_invalid = (~valid).sum()
    if n_invalid > 0:
        logger.warning(f"{n_invalid} record(s) had invalid/missing values and were excluded")
    
    X_clean = X.loc[valid]

    if len(X_clean) == 0:
        logger.error("No valid records to process after cleaning")
        raise ValueError("No valid records found in input data")

    logger.debug(f"Running proxy model on {len(X_clean)} records")
    Z_masked = proxy_model.predict(proxy_scaler.transform(X_clean))

    Z_CONF = np.array([1.0, 0.8, 0.8, 0.5])
    health_distance = np.linalg.norm((Z_masked - z_star[Z_KEEP]) * Z_CONF, axis=1)

    Z_full = np.zeros((Z_masked.shape[0], 8))
    Z_full[:, Z_KEEP] = Z_masked

    logger.debug("Running risk prediction models")
    pred_diab = risk_diab.predict_proba(Z_full)[:,1]
    pred_bp   = risk_bp.predict_proba(Z_full)[:,1]
    pred_lip  = risk_lip.predict_proba(Z_full)[:,1]

    out = pd.DataFrame({
        "client_id": df.loc[valid, "client_id"],
        "health_distance": health_distance,
        "pred_diab": pred_diab,
        "pred_bp": pred_bp,
        "pred_lip": pred_lip
    })

    # IMPROVEMENT: Added type hints to nested functions
    def focus(i: int) -> str:
        """Determine primary coaching focus based on risk scores."""
        if pred_diab[i] > 0.4: return "metabolic_reset"
        if pred_lip[i] > 0.4:  return "lipid_optimization"
        if health_distance[i] > 2.5: return "fat_loss"
        return "muscle_building"

    def triage(i: int) -> str:
        """Determine required coaching level."""
        if pred_diab[i] > 0.7 or pred_bp[i] > 0.7 or pred_lip[i] > 0.8:
            return "COACH_REQUIRED"
        if health_distance[i] < 1.5:
            return "AUTO"
        return "HYBRID_MONITOR"

    logger.debug("Calculating coaching focus and triage levels")
    out["control_focus"] = [focus(i) for i in range(len(out))]
    out["triage"] = [triage(i) for i in range(len(out))]

    logger.info(f"Predictions completed for {len(out)} client(s)")
    return out.reset_index(drop=True)


def generate_explanation(row: pd.Series) -> str:
    """IMPROVEMENT: Added type hints and error logging.
    
    Generate AI-powered health explanation using OpenAI API.
    """
    prompt = f"""
Client profile:

Health distance: {row.health_distance:.2f}
Diabetes risk: {row.pred_diab:.3f}
BP risk: {row.pred_bp:.3f}
Lipid risk: {row.pred_lip:.3f}
Primary focus: {row.control_focus}
Coaching level: {row.triage}
"""

    try:
        logger.debug(f"Generating explanation for client {row.client_id}")
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            timeout=15
        )
        explanation = resp.choices[0].message.content
        logger.info(f"Explanation generated successfully for {row.client_id}")
        return explanation
    except Exception as e:
        logger.error(f"OpenAI API error for client {row.client_id}: {str(e)}")
        return "Explanation temporarily unavailable. Core health metrics and recommendations are still valid."
    
