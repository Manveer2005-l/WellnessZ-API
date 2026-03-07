#How to run locally

git clone https://github.com/Manveer2005-l/WellnessZ-API.git
cd WellnessZ-API
pip install -r requirements.txt
python app.py


Server runs at: http://127.0.0.1:5000

#IMPROVEMENT: Added /health endpoint for monitoring

curl -X GET http://127.0.0.1:5000/health

#Test single client prediction

curl -X POST http://127.0.0.1:5000/predict \
-H "Authorization: Bearer wellnessz-secret" \
-H "Content-Type: application/json" \
-d '{"client_id":"test123","metrics":{"bmi":28,"hm_visceral_fat":15,"hm_muscle":30,"hm_rm":800,"age":35,"sex":1}}'

#IMPROVEMENT: Batch CSV upload for multiple clients

curl -X POST http://127.0.0.1:5000/analyze -F "file=@clients.csv"

Required CSV columns: client_id, bmi, hm_visceral_fat, hm_muscle, hm_rm, age, sex
