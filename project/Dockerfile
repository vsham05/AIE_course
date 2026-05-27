FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY artifacts/bert_bird_finetuned/checkpoint-6188 ./artifacts/bert_bird_finetuned/checkpoint-6188

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

CMD ["uvicorn", "src.services.main:app", "--host", "0.0.0.0", "--port", "8000"]