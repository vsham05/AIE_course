#Eda-CLI(API)
Небольшое CLI-приложение для базового анализа CSV-файлов. Используется в рамках Семинара 03 курса «Инженерия ИИ».

##Требования
Python 3.11+

uv установлен в систему

Инициализация проекта
В корне проекта (S03):
```
bash
uv sync
```
Эта команда:

создаст виртуальное окружение .venv;

установит зависимости из pyproject.toml;

установит сам проект eda-cli в окружение.

Запуск CLI
Краткий обзор
bash
uv run eda-cli overview data/example.csv
Параметры:

--sep – разделитель (по умолчанию ,);

--encoding – кодировка (по умолчанию utf-8).

Полный EDA-отчёт
bash
uv run eda-cli report data/example.csv --out-dir reports
В результате в каталоге reports/ появятся:

report.md – основной отчёт в Markdown;

summary.csv – таблица по колонкам;

missing.csv – пропуски по колонкам;

correlation.csv – корреляционная матрица (если есть числовые признаки);

top_categories/*.csv – top-k категорий по строковым признакам;

hist_*.png – гистограммы числовых колонок;

missing_matrix.png – визуализация пропусков;

correlation_heatmap.png – тепловая карта корреляций.

API Сервис
Запуск API сервера
Для запуска FastAPI сервиса:

bash
uv run uvicorn api.main:app --reload
Или с использованием модуля API:

bash
uv run python -m api.main
Сервер будет доступен по адресу: http://localhost:8000

Документация API
После запуска сервера доступны:

Swagger UI: http://localhost:8000/docs

ReDoc: http://localhost:8000/redoc

OpenAPI схема: http://localhost:8000/openapi.json

Доступные эндпоинты
1. Проверка качества CSV файла
text
POST /quality-flags-from-csv
Описание: Принимает CSV-файл и возвращает флаги качества данных.

Параметры:

file (multipart/form-data): CSV файл для анализа

Пример запроса:

bash
curl -X POST "http://localhost:8000/quality-flags-from-csv" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@data/example.csv"
Пример ответа:

json
{
  "flags": {
    "too_few_rows": false,
    "too_many_columns": false,
    "max_missing_share": 0.0,
    "too_many_missing": false,
    "has_constant_columns": false,
    "has_high_cardinality_categoricals": true,
    "quality_score": 0.75
  }
}
2. Полный анализ CSV файла
text
POST /full-analysis-from-csv
Описание: Принимает CSV-файл и возвращает полный EDA отчет в JSON формате.

Параметры:

file (multipart/form-data): CSV файл для анализа

top_categories (query, optional): Количество топ-категорий для анализа (по умолчанию: 10)

Пример запроса:

bash
curl -X POST "http://localhost:8000/full-analysis-from-csv?top_categories=10" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@data/example.csv"
3. Статус сервиса
text
GET /health
Описание: Проверка работоспособности API сервиса.

Пример запроса:

bash
curl "http://localhost:8000/health"
Пример ответа:

json
{
  "status": "ok",
  "timestamp": "2024-01-15T10:30:00Z"
}
4. Информация о сервисе
text
GET /info
Описание: Возвращает информацию о версии и возможностях сервиса.

Пример запроса:

bash
curl "http://localhost:8000/info"
Пример ответа:

json
{
  "name": "eda-api-service",
  "version": "1.0.0",
  "description": "EDA (Exploratory Data Analysis) API Service для анализа CSV файлов",
  "endpoints": [
    "GET /health",
    "GET /info",
    "POST /quality-flags-from-csv",
    "POST /full-analysis-from-csv"
  ]
}
Примеры использования
Python (requests)
python
import requests

# Отправка CSV файла на анализ
url = "http://localhost:8000/quality-flags-from-csv"
files = {"file": open("data/example.csv", "rb")}
response = requests.post(url, files=files)

if response.status_code == 200:
    quality_flags = response.json()
    print(f"Качество данных: {quality_flags['flags']['quality_score']}")
else:
    print(f"Ошибка: {response.text}")
JavaScript (fetch)
javascript
const formData = new FormData();
formData.append('file', fileInput.files[0]);

fetch('http://localhost:8000/quality-flags-from-csv', {
  method: 'POST',
  body: formData
})
.then(response => response.json())
.then(data => console.log(data));
Тесты
Для запуска тестов:

bash
uv run pytest -q
Для запуска тестов с покрытием:

bash
uv run pytest --cov=eda_cli --cov=api --cov-report=html
Структура проекта
text
S03/
├── api/                    # API сервис FastAPI
│   ├── main.py            # Основной файл приложения
│   ├── routes/            # Маршруты API
│   └── models/            # Pydantic модели
├── eda_cli/               # CLI приложение
│   ├── core/              # Основная логика EDA
│   ├── cli.py             # CLI интерфейс
│   └── __init__.py
├── data/                  # Примеры данных
│   └── example.csv
├── tests/                 # Тесты
├── pyproject.toml         # Зависимости и конфигурация
└── README.md             # Документация
Поддерживаемые форматы
API поддерживает CSV файлы со следующими content-types:

text/csv

application/vnd.ms-excel

application/octet-stream