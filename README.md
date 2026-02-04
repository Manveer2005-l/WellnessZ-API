#How to run locally

git clone https://github.com/Manveer2005-l/WellnessZ-API.git
cd WellnessZ-API
pip install -r requirements.txt
python app.py


Server runs at: http://127.0.0.1:5000

#Test single client

curl -X POST http://127.0.0.1:5000/explain \
-H "Content-Type: application/json" \
-d "{\"bmi\":28,\"hm_visceral_fat\":15,\"hm_muscle\":30,\"hm_rm\":800,\"age\":35,\"sex\":1,\"client_id\":\"test123\"}"

#Test CSV upload

curl -X POST http://127.0.0.1:5000/analyze -F "file=@clients.csv"
