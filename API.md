POST /predict
Headers:
Authorization: Bearer <API_KEY>
Content-Type: application/json

Body:
{
  "client_id": "string",
  "metrics": {
    "bmi": number,
    "hm_visceral_fat": number,
    "hm_muscle": number,
    "hm_rm": number,
    "age": number,
    "sex": number
  }
}