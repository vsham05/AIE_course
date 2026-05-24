import json
from typing import Dict, Set, Optional, Type, Any
from pydantic import BaseModel


class SchemaAwareValidator:
    """
    Валидатор, проверяющий имена таблиц и колонок против схемы БД.
    Гарантирует, что сгенерированные модели ссылаются только на существующие объекты.
    """
    
    DATE_TYPES = {"date", "timestamp", "timestamptz", "datetime", "bigint", "integer"}
    NUMERIC_TYPES = {"integer", "int", "bigint", "smallint", "float", "double", "decimal", "numeric", "real"}
    STRING_TYPES = {"varchar", "char", "text", "string", "character varying"}
    
    def __init__(self, schema: Dict[str, Dict[str, str]]):
        """
        schema: {
            "table_name": {"column_name": "data_type", ...}
        }
        Пример: {"orders": {"id": "integer", "status": "varchar", "created_at": "timestamp"}}
        """
        self.schema = schema
        self._tables = set(schema.keys())
        self._columns: Set[str] = set()
        self._col_types: Dict[str, str] = {}
        self._table_columns: Dict[str, Set[str]] = {}
        
        for table, cols in schema.items():
            self._table_columns[table] = set(cols.keys())
            for col, dtype in cols.items():
                # Нормализуем тип
                dtype_norm = dtype.lower().split("(")[0].strip()
                full_name = f"{table}.{col}"
                self._columns.add(full_name)
                self._columns.add(col)  # разрешаем короткие имена
                self._col_types[full_name] = dtype_norm
                self._col_types[col] = dtype_norm
    
    def validate_table(self, table: str) -> bool:
        return table in self._tables
    
    def validate_column(self, column: str, context: str = "") -> str:
        """Проверяет существование колонки. Возвращает нормализованное имя."""
        if column == "*":
            return column
        
        # Прямое совпадение
        if column in self._columns:
            return column
        
        # Если указан table.column, проверяем по полному имени
        if "." in column:
            table, col = column.rsplit(".", 1)
            if table in self._table_columns and col in self._table_columns[table]:
                return column
            raise ValueError(
                f"{context}Column '{column}' not found. "
                f"Available in '{table}': {sorted(self._table_columns.get(table, []))[:10]}"
            )
        
        # Поиск по короткому имени во всех таблицах
        for table, cols in self._table_columns.items():
            if column in cols:
                return f"{table}.{column}"
        
        available = sorted(self._columns)[:15]
        raise ValueError(
            f"{context}Column '{column}' not in schema. Available: {available}..."
        )
    
    def get_column_type(self, column: str) -> Optional[str]:
        """Возвращает тип колонки в нижнем регистре."""
        return self._col_types.get(column) or self._col_types.get(column.split(".")[-1])
    
    def is_date_column(self, column: str) -> bool:
        col_type = self.get_column_type(column)
        return col_type in self.DATE_TYPES if col_type else False
    
    def is_numeric_column(self, column: str) -> bool:
        col_type = self.get_column_type(column)
        return col_type in self.NUMERIC_TYPES if col_type else False
    
    def validate_date_column(self, column: str) -> str:
        """Проверяет, что колонка имеет тип даты/времени."""
        validated = self.validate_column(column, "DateFilter: ")
        if not self.is_date_column(validated):
            col_type = self.get_column_type(validated)
            raise ValueError(
                f"DateFilter: Column '{validated}' has type '{col_type}', "
                f"expected one of {self.DATE_TYPES}"
            )
        return validated
    
    def validate_agg_column(self, column: str, function: str) -> str:
        """Валидирует колонку для агрегатной функции."""
        if column == "*":
            if function.upper() != "COUNT":
                raise ValueError(f"'*' можно использовать только с COUNT, а не с {function}")
            return column
        validated = self.validate_column(column, f"Aggregation[{function}]: ")
        # COUNT(*) не требует проверки типа, остальные функции — числовые колонки
        if function.upper() in ("SUM", "AVG") and not self.is_numeric_column(validated):
            col_type = self.get_column_type(validated)
            raise ValueError(
                f"Aggregation[{function}]: Column '{validated}' has type '{col_type}', "
                f"expected numeric type for {function}"
            )
        return validated
    
    def get_enum_values(self, column: str) -> Optional[list]:
        """Извлекает возможные значения для ENUM-колонок (если указаны в схеме)."""
        col_type = self.get_column_type(column)
        if col_type and col_type.startswith("enum("):
            # Парсим enum(val1,val2,val3)
            try:
                values_str = col_type[5:-1]  # убираем "enum(" и ")"
                return [v.strip().strip("'\"") for v in values_str.split(",")]
            except:
                return None
        return None


# === ШАБЛОНЫ ПРОМПТОВ ===

PROMPT_TEMPLATES: Dict[str, str] = {
    "AggregationQ": """Ты генерируешь ТОЛЬКО агрегатные функции для SELECT.

Схема БД (используй только эти таблицы и колонки):
{schema}

Вопрос пользователя: {question}

Правила:
1. Используй только столбцы, которые есть в схеме выше
2. Для COUNT(*) указывай column="*" и function="COUNT"
3. Alias должен быть на латинице, без пробелов и спецсимволов
4. distinct=true только если явно нужно посчитать уникальные значения

Верни строго валидный JSON по этой схеме (без лишних полей):
{model_schema}""",

    "DateFilterQ": """Ты отвечаешь за фильтрацию по дате/времени.

Схема БД:
{schema}

Вопрос: {question}

Инструкции:
1. Найди столбец типа DATE/TIMESTAMP/BIGINT в схеме
2. Если в вопросе есть период ("за январь", "с 1 по 31") — укажи start_date и/или end_date в формате 'YYYY-MM-DD' или 'YYYY-MM-DD HH:MM:SS'
3. Для относительных периодов ("за последний месяц", "за неделю") используй relative и unit
4. Верни только те поля, которые нужны (незаполненные можно опустить)

Схема ответа (строгая валидация):
{model_schema}""",

    "DistinctQ": """Нужно ли убрать дубликаты из результата?

Схема БД: {schema}
Вопрос: {question}

Правила:
- is_distinct=true, если вопрос подразумевает уникальные значения ("список пользователей", "какие статусы бывают")
- columns укажи только для PostgreSQL DISTINCT ON (редко)
- Если не уверен — верни is_distinct=false

Схема ответа:
{model_schema}""",

    "GroupQ": """Ты определяешь GROUP BY.

Схема БД: {schema}
Вопрос: {question}

Правила:
1. Группировка нужна, если есть агрегаты (SUM, COUNT...) и вопрос про "по пользователям", "по датам", "по категориям"
2. Используй только столбцы из схемы
3. Если агрегатов нет — верни пустой список или не вызывай этот компонент

Схема ответа:
{model_schema}""",

    "HavingQ": """Ты генерируешь HAVING (фильтрация ПОСЛЕ группировки).

Схема БД: {schema}
Вопрос: {question}

Важно:
- Условия HAVING применяются к результатам агрегатов или GROUP BY столбцам
- Пример: "покажи пользователей с суммой заказов больше 1000" → column="total_sum", operator=">", value=1000
- В column указывай alias агрегата или имя столбца из GROUP BY

Схема:
{model_schema}""",

    "InListQ": """Ты отвечаешь за оператор IN / NOT IN.

Схема: {schema}
Вопрос: {question}

Правила:
- column: столбец для проверки (должен быть в схеме)
- values: список значений. Для строк — без кавычек внутри, они добавятся при сборке
- negate: true для NOT IN (если вопрос "кроме", "исключая", "не равные")

Пример ответа: {{"column": "status", "values": ["pending", "cancelled"], "negate": false}}

Схема:
{model_schema}""",

    "JOINQ": """Ты определяешь JOIN таблиц.

Схема БД: {schema}
Вопрос: {question}

Инструкции:
1. table: имя таблицы из схемы, которую нужно присоединить
2. join_type: INNER (по умолчанию), LEFT (если нужно сохранить все строки из основной таблицы)
3. on: массив условий соединения. Используй формат table.column для однозначности
4. alias: опциональный псевдоним для таблицы (если в вопросе используется)

Пример:
{{"joins": [{{"table": "users", "join_type": "INNER", "on": [{{"left_column": "orders.user_id", "operator": "=", "right_column": "users.id"}}]}}]}}

Схема:
{model_schema}""",

    "LimitQ": """Ты отвечаешь за LIMIT и OFFSET.

Схема: {schema}
Вопрос: {question}

Правила:
- limit: укажи, если в вопросе есть "топ-10", "первые 5", "не более"
- offset: нужен для пагинации ("вторая страница", "следующие 10")
- Если ограничений нет — верни limit=null или не вызывай этот компонент

Схема:
{model_schema}""",

    "NullCheckQ": """Ты проверяешь на NULL.

Схема: {schema}
Вопрос: {question}

Правила:
- is_null=true → IS NULL (вопросы "где нет значения", "пустые", "не заполнено")
- is_null=false → IS NOT NULL ("есть значение", "заполнено", "не пусто")
- column: должен существовать в схеме

Схема:
{model_schema}""",

    "SortQ": """Ты определяешь ORDER BY.

Схема: {schema}
Вопрос: {question}

Правила:
1. column: столбец для сортировки (из схемы или alias агрегата)
2. direction: "DESC" для "по убыванию", "сначала большие", "топ"; "ASC" для "по возрастанию", "сначала старые"
3. nulls: укажи, если важно, где располагать NULL-значения

Пример: {{"orders": [{{"column": "total", "direction": "DESC"}}]}}

Схема:
{model_schema}""",

    "WhereQ": """Ты генерируешь базовые условия WHERE (НЕ даты, НЕ IN, НЕ NULL).

Схема БД: {schema}
Вопрос: {question}

Правила:
1. column: должен быть в схеме
2. operator: =, !=, >, <, >=, <=, LIKE, ILIKE
3. value: для строк — без кавычек, для чисел — без кавычек, для булевых — true/false
4. logical_op: "AND" (по умолчанию) или "OR" если в вопросе есть "или", "либо"

Пример: статус = "выполнен" → {{"column": "status", "operator": "=", "value": "completed"}}

Схема:
{model_schema}"""
}


def build_prompt(
    class_name: str,
    question: str,
    schema: Dict[str, Dict[str, str]],
    model_cls: Type[BaseModel]
) -> str:
    """
    Генерирует финальный промпт с инъекцией схемы и JSON-схемой модели.
    
    Args:
        class_name: Имя класса из DEFAULT_CLASSES
        question: Вопрос пользователя
        schema: Схема БД в формате {table: {column: type}}
        model_cls: Pydantic-модель для structured output
    
    Returns:
        Строка промпта, готовая к отправке в LLM
    """
    # Форматируем схему для читаемости в промпте
    schema_lines = []
    for table, columns in schema.items():
        cols_str = ", ".join(f"{col}({dtype})" for col, dtype in columns.items())
        schema_lines.append(f"  {table}: [{cols_str}]")
    schema_text = "\n".join(schema_lines)
    
    # Получаем JSON-схему модели для инъекции в промпт
    model_schema = model_cls.model_json_schema()
    # Убираем лишние поля из JSON-схемы для компактности
    model_schema_clean = {
        "type": model_schema.get("type"),
        "properties": model_schema.get("properties", {}),
        "required": model_schema.get("required", [])
    }
    
    # Выбираем шаблон
    template = PROMPT_TEMPLATES.get(class_name)
    if not template:
        raise ValueError(f"Unknown class_name: {class_name}. Available: {list(PROMPT_TEMPLATES.keys())}")
    
    # Формируем промпт
    prompt = template.format(
        schema=schema_text,
        question=question,
        model_schema=json.dumps(model_schema_clean, indent=2, ensure_ascii=False)
    )
    
    # Финальная инструкция
    return prompt.strip() + "\n\nОтветь ТОЛЬКО валидным JSON. Без markdown-оберток, без комментариев, без пояснений."


def preview_prompt(class_name: str, question: str, schema: Dict, model_cls: Type[BaseModel]) -> None:
    """Выводит сгенерированный промпт в консоль для отладки."""
    prompt = build_prompt(class_name, question, schema, model_cls)
    print(f"\n{'='*60}")
    print(f"PROMPT FOR: {class_name}")
    print(f"{'='*60}\n")
    print(prompt)
    print(f"\n{'='*60}\n")