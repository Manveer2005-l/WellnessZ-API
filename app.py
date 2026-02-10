from flask import Flask, request, jsonify
import pandas as pd
from wellnessz_runtime import predict_clients, generate_explanation
import os

from dotenv import load_dotenv
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, ".env")
load_dotenv(ENV_PATH)

app = Flask(__name__)


API_KEY = os.getenv("WELLNESSZ_API_KEY", "dev-key")

print("DEBUG → WELLNESSZ_API_KEY =", API_KEY)


# ---------- Health check ----------
@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


# ---------- Single client prediction ----------
@app.route("/predict", methods=["POST"])
def predict_single_client():

    # --- simple auth (enough for now)
    auth = request.headers.get("Authorization")
    
    if auth != f"Bearer {API_KEY}":
        return jsonify({"error": "Unauthorized"}), 401

    

    print("RAW BODY:", request.data)
    data = request.get_json(force=True)
    print("PARSED JSON:", data)

    if "metrics" not in data:
        return jsonify({"error": "metrics missing"}), 4
    # build dataframe expected by your engine
    df = pd.DataFrame([data["metrics"]])
    df["client_id"] = data.get("client_id")

    df_out = predict_clients(df)
    row = df_out.iloc[0]

    explanation = generate_explanation(row)

    return jsonify({
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
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
