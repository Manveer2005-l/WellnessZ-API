# IMPROVEMENT: Added logging and Pydantic for input validation
from flask import Flask, request, jsonify
import pandas as pd
import requests
import os
import time
import logging
from typing import Dict, List, Union, Any, Optional
from pydantic import BaseModel, ValidationError, field_validator
from trajectory_engine import predict_trajectory
from wellnessz_runtime import predict_clients, generate_explanation
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# IMPROVEMENT: Added logging configuration
logging.basicConfig(
    level=logging.DEBUG,  # temporarily verbose for debugging
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# IMPROVEMENT: Pydantic models for input validation
class MetricsSchema(BaseModel):
    """Validates individual health metrics from client.

    Added optional `date` field so that trajectory requests can pass a
    timestamp with each visit. The field is stored as a string in ISO
    format and not further transformed by Pydantic.
    """
    bmi: float
    hm_visceral_fat: float
    hm_muscle: float
    hm_rm: float
    age: int
    sex: int
    date: Optional[str] = None  # ISO date string (YYYY-MM-DD)
    
    @field_validator('hm_visceral_fat', 'hm_muscle', 'hm_rm', 'bmi')
    @classmethod
    def validate_positive(cls, v):
        if v < 0:
            raise ValueError('Metric values cannot be negative')
        return v
    
    @field_validator('age')
    @classmethod
    def validate_age(cls, v):
        if not (0 < v < 150):
            raise ValueError('Age must be between 1 and 149')
        return v
    
    @field_validator('sex')
    @classmethod
    def validate_sex(cls, v):
        if v not in [0, 1]:
            raise ValueError('Sex must be 0 (female) or 1 (male)')
        return v


class PredictRequest(BaseModel):
    """Validates /predict endpoint request."""
    client_id: str
    metrics: Union[MetricsSchema, List[MetricsSchema]]


class PredictByIdRequest(BaseModel):
    """Validates /predict/by-id endpoint request."""
    client_id: str

# ---- ENV ----
API_KEY = os.getenv("WELLNESSZ_API_KEY", "dev-key")

DATA_MODE = os.getenv("DATA_MODE", "NONE")  # NONE | REMOTE
CLIENT_API_BASE_URL = os.getenv("CLIENT_API_BASE_URL")
CLIENT_API_KEY = os.getenv("CLIENT_API_KEY")


# ---------- helpers ----------

def fetch_client_metrics(client_id: str) -> dict:
    """
    Fetch client metrics from external backend
    
    IMPROVEMENT: Added logging for debugging and better error messages
    """

    if DATA_MODE != "REMOTE":
        logger.error("REMOTE data mode not enabled")
        raise RuntimeError("REMOTE data mode not enabled")

    if not CLIENT_API_BASE_URL:
        logger.error("CLIENT_API_BASE_URL not configured")
        raise RuntimeError("CLIENT_API_BASE_URL not set")

    url = f"{CLIENT_API_BASE_URL}/clients/{client_id}"
    logger.info(f"Fetching metrics for client: {client_id}")

    headers = {
        "Authorization": f"Bearer {CLIENT_API_KEY}",
        "Content-Type": "application/json"
    }

    for attempt in range(3):

        try:
            resp = requests.get(url, headers=headers, timeout=40)

            if resp.status_code == 200:
                data = resp.json()
                data.setdefault("age", 30)
                data.setdefault("sex", 1)
                logger.info(f"Successfully fetched metrics for {client_id}")
                return data

            if resp.status_code == 429:
                logger.warning(f"Rate limit hit (attempt {attempt + 1}/3). Retrying...")
                time.sleep(2)
                continue

            logger.error(f"Client fetch failed with status {resp.status_code}")
            raise RuntimeError(f"Client fetch failed ({resp.status_code})")

        except requests.exceptions.ReadTimeout:
            logger.warning(f"Backend timeout (attempt {attempt + 1}/3). Retrying...")
            time.sleep(3)
        except Exception as e:
            logger.error(f"Unexpected error fetching metrics: {str(e)}")

    logger.error("Backend unreachable after 3 retries")
    raise RuntimeError("Backend unreachable after retries")


# ---------- feature mapping ----------

def build_feature_row(client_id: str, metrics: Dict[str, Any]) -> Dict[str, Any]:
    """IMPROVEMENT: Added type hints and docstring.

    The incoming metrics dict may include a "date" key; this value is
    preserved so that trajectory calculations can sort by visit timestamp.
    """
    row = {
        "client_id": client_id,
        "date": metrics.get("date"),  # optional, may be None
        "bmi": metrics.get("bmi", 0),
        "hm_visceral_fat": metrics.get("hm_visceral_fat", 10),
        "hm_muscle": metrics.get("hm_muscle", 0),
        "hm_rm": metrics.get("hm_rm", 1),
        "age": metrics.get("age", 30),
        "sex": metrics.get("sex", 1)
    }
    # propagate optional date field if present
    if "date" in metrics:
        row["date"] = metrics.get("date")
    return row


# ---------- engine ----------

def wellnessz_engine(df: pd.DataFrame) -> Dict[str, Any]:
    """IMPROVEMENT: Added type hints and better error logging."""
    try:
        baseline_df = predict_clients(df)
        row = baseline_df.iloc[-1]
        logger.info(f"Predictions completed for {len(df)} record(s)")

        response = _format_response(row)

        if len(df) >= 2:
            # DEBUG: inspect DataFrame prior to trajectory call
            logger.debug(f"DF columns before trajectory: {df.columns.tolist()}")
            logger.debug(f"DF head before trajectory:\n{df.head()}" )
            logger.debug(df)
            try:
                trajectory = predict_trajectory(df)
                response["trajectory"] = trajectory
                logger.info("Trajectory analysis completed")
            except Exception as e:
                logger.error(f"Trajectory calculation failed: {str(e)}")
                response["trajectory_error"] = str(e)

        return response
    except Exception as e:
        logger.error(f"Engine processing failed: {str(e)}")
        raise


# ---------- routes ----------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/predict", methods=["POST"])
def predict_manual():
    """IMPROVEMENT: Removed duplicate code, added validation and logging."""
    try:
        auth = request.headers.get("Authorization")
        if auth != f"Bearer {API_KEY}":
            logger.warning("Unauthorized prediction request")
            return jsonify({"error": "Unauthorized"}), 401

        payload = request.get_json(force=True)

        if "metrics" not in payload:
            logger.warning("Prediction request missing metrics field")
            return jsonify({"error": "metrics missing"}), 400

        # IMPROVEMENT: Added Pydantic validation
        try:
            validated = PredictRequest(**payload)
        except ValidationError as e:
            logger.warning(f"Validation error: {e.json()}")
            return jsonify({"error": "Invalid metrics", "details": e.errors()}), 422

        metrics = validated.metrics
        client_id = validated.client_id

        # IMPROVEMENT: Removed duplicate row-building logic
        rows = []
        if isinstance(metrics, list):
            for m in metrics:
                rows.append(build_feature_row(client_id, m.dict()))
        else:
            rows.append(build_feature_row(client_id, metrics.dict()))

        df = pd.DataFrame(rows)
        logger.info(f"Processing prediction for client {client_id} with {len(df)} record(s)")

        result = wellnessz_engine(df)
        return jsonify(result)

    except Exception as e:
        logger.error(f"Prediction endpoint error: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


@app.route("/predict/by-id", methods=["POST"])
def predict_by_id():
    """IMPROVEMENT: Added validation and better error logging."""
    try:
        auth = request.headers.get("Authorization")
        if auth != f"Bearer {API_KEY}":
            logger.warning("Unauthorized predict-by-id request")
            return jsonify({"error": "Unauthorized"}), 401

        data = request.get_json()

        # IMPROVEMENT: Added Pydantic validation
        try:
            validated = PredictByIdRequest(**data)
        except ValidationError as e:
            logger.warning(f"Validation error: {e.json()}")
            return jsonify({"error": "Invalid request", "details": e.errors()}), 422

        client_id = validated.client_id
        logger.info(f"Fetching prediction for client_id: {client_id}")

        metrics = fetch_client_metrics(client_id)

        rows = []
        if "visits" in metrics:
            for v in metrics["visits"]:
                rows.append(build_feature_row(client_id, v))
        else:
            rows.append(build_feature_row(client_id, metrics))

        df = pd.DataFrame(rows)
        result = wellnessz_engine(df)
        return jsonify(result)

    except RuntimeError as e:
        logger.error(f"Backend unavailable: {str(e)}")
        return jsonify({
            "error": "Backend unavailable",
            "details": str(e)
        }), 503
    except Exception as e:
        logger.error(f"Predict-by-id endpoint error: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# ---------- formatter ----------

def _format_response(row: Any) -> Dict[str, Any]:
    """IMPROVEMENT: Added type hints."""
    explanation = generate_explanation(row)

    return {
        "client_id": row.client_id,
        "triage": row.triage,
        "control_focus": row.control_focus,
        "health_distance": float(row.health_distance),
        "risks": {
            "diabetes": float(row.pred_diab),
            "blood_pressure": float(row.pred_bp),
            "lipids": float(row.pred_lip)
        },
        "explanation": explanation
    }

@app.route("/")
def home():
    return jsonify({"message": "WellnessZ API is live"})

# IMPROVEMENT: Added /analyze endpoint for CSV batch processing
@app.route("/analyze", methods=["POST"])
def analyze_csv():
    """Batch analysis of multiple clients from CSV file."""
    try:
        if "file" not in request.files:
            logger.warning("CSV upload request missing file")
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if file.filename == "":
            logger.warning("Empty filename in upload")
            return jsonify({"error": "No file selected"}), 400

        if not file.filename.endswith(".csv"):
            logger.warning(f"Invalid file type: {file.filename}")
            return jsonify({"error": "Only CSV files allowed"}), 400

        try:
            df = pd.read_csv(file)
            logger.info(f"Loaded CSV with {len(df)} rows")
        except Exception as e:
            logger.error(f"CSV parsing error: {str(e)}")
            return jsonify({"error": "Invalid CSV format", "details": str(e)}), 400

        # Validate required columns
        required_cols = ["client_id", "bmi", "hm_visceral_fat", "hm_muscle", "hm_rm", "age", "sex"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            logger.warning(f"CSV missing columns: {missing}")
            return jsonify({"error": f"Missing columns: {missing}"}), 422

        results = []
        errors = []

        for idx, row in df.iterrows():
            try:
                row_dict = row.to_dict()
                # IMPROVEMENT: Use validation for individual rows
                try:
                    MetricsSchema(**{k: row_dict[k] for k in ["bmi", "hm_visceral_fat", "hm_muscle", "hm_rm", "age", "sex"]})
                except ValidationError as e:
                    errors.append({"row": idx + 1, "error": str(e)})
                    continue

                result = wellnessz_engine(pd.DataFrame([row_dict]))
                results.append(result)
            except Exception as e:
                logger.error(f"Error processing row {idx + 1}: {str(e)}")
                errors.append({"row": idx + 1, "error": str(e)})

        logger.info(f"CSV analysis complete: {len(results)} successful, {len(errors)} failed")
        return jsonify({
            "total_rows": len(df),
            "successful": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors if errors else None
        })

    except Exception as e:
        logger.error(f"CSV analysis endpoint error: {str(e)}")
        return jsonify({"error": "Internal server error", "details": str(e)}), 500


# ---------- run ----------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting WellnessZ API on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)