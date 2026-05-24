# test_schema.py
import requests
from pydantic import BaseModel, Field

class SimpleTest(BaseModel):
    result: str = Field(..., description="Простой строковый ответ")

# Минимальная схема
schema = SimpleTest.model_json_schema()
print("📄 Отправляемая схема:")
print(schema)

prompt = "Верни один слово: успех"

resp = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "qwen3:1.7b",
        "prompt": prompt,
        "format": schema,
        "stream": False,
        "temperature": 0.0,
        "options": {"num_ctx": 2048, "num_thread": 6}
    },
    timeout=30
)

print(f"\n📡 Статус: {resp.status_code}")
if resp.status_code == 200:
    print(f"✅ Ответ: {resp.json()['response']}")
else:
    print(f"❌ Ошибка: {resp.text}")