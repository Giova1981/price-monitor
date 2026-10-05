import json
import os
import requests

URL = (
    "https://cashback.spesasicura.com/product/details/1843"
)

api_key = os.environ["TINYFISH_API_KEY"]

response = requests.post(
    "https://api.fetch.tinyfish.ai",
    headers={
        "X-API-Key": api_key,
        "Content-Type": "application/json"
    },
    json={
        "urls": [URL],
        "format": "html",
        "ttl": 0
    },
    timeout=120
)

response.raise_for_status()

data = response.json()

print("===== RISPOSTA TINYFISH JSON =====")
print(json.dumps(data, indent=2, ensure_ascii=False))
