from flask import Flask, request, jsonify
import pandas as pd
import requests
import os
from trajectory_engine import predict_trajectory
from wellnessz_runtime import predict_clients, generate_explanation
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# ---- ENV ----
API_KEY = os.getenv("WELLNESSZ_API_KEY", "dev-key")

DATA_MODE = os.getenv("DATA_MODE", "NONE")  # NONE | REMOTE
CLIENT_API_BASE_URL = os.getenv("CLIENT_API_BASE_URL")
CLIENT_API_KEY = os.getenv("CLIENT_API_KEY")


# ---------- helpers ----------

import time
import requests

def fetch_client_metrics(client_id: str) -> dict:
    """
    Fetch client metrics from external backend
    """

    if DATA_MODE != "REMOTE":
        raise RuntimeError("REMOTE data mode not enabled")

    if not CLIENT_API_BASE_URL:
        raise RuntimeError("CLIENT_API_BASE_URL not set")

    url = f"{CLIENT_API_BASE_URL}/clients/{client_id}"

    headers = {
        "Authorization": f"Bearer {CLIENT_API_KEY}",
        "Content-Type": "application/json"
    }

    for attempt in range(3):

        try:
            resp = requests.get(url, headers=headers, timeout=30)

            if resp.status_code == 200:
                data = resp.json()
                data.setdefault("age", 1)
                data.setdefault("sex", 1)
                return data

            if resp.status_code == 429:
                time.sleep(2)
                continue

            raise RuntimeError(f"Client fetch failed ({resp.status_code})")

        except requests.exceptions.ReadTimeout:
            print("Backend timeout, retrying...")
            time.sleep(3)

raise RuntimeError("Backend unreachable after retries")
    # After retries
    
# ---------- engine ----------

def wellnessz_engine(df):

    baseline_df = predict_clients(df)
    row = baseline_df.iloc[-1]

    response = _format_response(row)

    # If multiple visits → add trajectory
    if len(df) >= 2:
        try:
            trajectory = predict_trajectory(df)
            response["trajectory"] = trajectory
        except Exception as e:
            response["trajectory_error"] = str(e)

    return response


# ---------- routes ----------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/predict", methods=["POST"])
def predict_manual():

    auth = request.headers.get("Authorization")
    if auth != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    payload = request.get_json(force=True)

    if "metrics" not in payload:
        return jsonify({"error": "metrics missing"}), 400

    metrics = payload["metrics"]

    metrics.setdefault("age", 1)
    metrics.setdefault("sex", 1)

    df = pd.DataFrame([metrics])
    df["client_id"] = payload.get("client_id", "MANUAL")

    result = wellnessz_engine(df)

@app.route("/predict/by-id", methods=["POST"])
def predict_by_id():

    auth = request.headers.get("Authorization")
    if auth != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()

    if not data or "client_id" not in data:
        return jsonify({"error": "client_id missing"}), 400

    client_id = data["client_id"]

    try:
        # fetch metrics from backend
        metrics = fetch_client_metrics(client_id)

        # if backend returns visits history
        if "visits" in metrics:
            df = pd.DataFrame(metrics["visits"])
        else:
            df = pd.DataFrame([metrics])

        df["client_id"] = client_id

        result = wellnessz_engine(df)

        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


# ---------- formatter ----------

def _format_response(row):

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)