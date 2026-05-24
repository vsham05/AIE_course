from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Literal, Union, Any
from enum import Enum

# === Общие типы ===
SQLOperator = Literal["=", "!=", ">", "<", ">=", "<=", "LIKE", "ILIKE", "IN", "IS NULL", "IS NOT NULL"]
AggFunction = Literal["COUNT", "SUM", "AVG", "MIN", "MAX", "STRING_AGG", "ARRAY_AGG"]
JoinType = Literal["INNER", "LEFT", "RIGHT", "FULL", "CROSS"]
SortDirection = Literal["ASC", "DESC"]
DateUnit = Literal["day", "week", "month", "year", "hour", "minute"]


SQLValue = Union[str, int, float, bool, List[str]]

class BaseCondition(BaseModel):
    column: str = Field(..., description="Имя столбца. Формат: 'table.column' или 'column'")
    operator: str = Field(..., description="SQL оператор: =, !=, >, <, >=, <=, LIKE, IN, IS NULL, IS NOT NULL")
    value: SQLValue = Field(..., description="Значение для сравнения")
    
    @field_validator("column")
    @classmethod
    def validate_column_exists(cls, v: str) -> str:
        # Валидация будет добавлена динамически через __init__ или внешний валидатор
        return v


# === 1. AggregationQ ===
class AggregationItem(BaseModel):
    function: AggFunction = Field(..., description="Агрегатная функция")
    column: str = Field(..., description="Столбец для агрегации или '*' для COUNT(*)")
    alias: str = Field(..., description="Псевдоним результата в SELECT", min_length=1, max_length=64)
    distinct: bool = Field(default=False, description="Применять COUNT(DISTINCT column)?")

class AggregationQ(BaseModel):
    aggregations: List[AggregationItem] = Field(default_factory=list, description="Список агрегаций для SELECT")
    
    @model_validator(mode="after")
    def validate_agg_columns(self):
        for agg in self.aggregations:
            if agg.function == "COUNT" and agg.column != "*" and not agg.column:
                raise ValueError("COUNT требует столбец или '*'")
        return self


# === 2. DateFilterQ ===
class DateFilterQ(BaseModel):
    column: str = Field(..., description="Столбец типа DATE, TIMESTAMP или BIGINT (unix time)")
    start_date: Optional[str] = Field(default=None, description="Начало диапазона: '2024-01-01' или '2024-01-01 00:00:00'")
    end_date: Optional[str] = Field(default=None, description="Конец диапазона")
    unit: Optional[DateUnit] = Field(default=None, description="Единица для относительных дат: 'last 7 days' → unit='day'")
    relative: Optional[str] = Field(default=None, description="Относительный период: 'today', 'last_week', 'last_month'")
    
    @model_validator(mode="after")
    def validate_date_range(self):
        if not self.start_date and not self.end_date and not self.relative:
            raise ValueError("Укажите start_date, end_date или relative")
        return self


# === 3. DistinctQ ===
class DistinctQ(BaseModel):
    is_distinct: bool = Field(..., description="Применять SELECT DISTINCT?")
    columns: Optional[List[str]] = Field(default=None, description="DISTINCT ON (columns) для PostgreSQL. Если None — глобальный DISTINCT")


# === 4. GroupQ ===
class GroupQ(BaseModel):
    columns: List[str] = Field(..., description="Столбцы для GROUP BY", min_length=1)
    
    @field_validator("columns")
    @classmethod
    def validate_group_columns(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("GROUP BY требует хотя бы один столбец")
        return v


# === 5. HavingQ ===
class HavingQ(BaseModel):
    conditions: List[BaseCondition] = Field(default_factory=list, description="Условия HAVING (применяются к агрегатам)")
    logical_op: Literal["AND", "OR"] = Field(default="AND", description="Логический оператор между условиями")


# === 6. InListQ ===
class InListQ(BaseModel):
    column: str = Field(..., description="Столбец для проверки IN (...)")
    values: List[Any] = Field(..., description="Список значений для IN", min_length=1)
    negate: bool = Field(default=False, description="Если True — использовать NOT IN")


# === 7. JOINQ ===
class JoinCondition(BaseModel):
    left_column: str = Field(..., description="Столбец из левой таблицы, например 'orders.user_id'")
    operator: Literal["=", "!="] = Field(default="=", description="Оператор соединения (обычно =)")
    right_column: str = Field(..., description="Столбец из правой таблицы, например 'users.id'")

class JoinItem(BaseModel):
    table: str = Field(..., description="Имя присоединяемой таблицы")
    join_type: JoinType = Field(default="INNER", description="Тип JOIN")
    on: List[JoinCondition] = Field(..., description="Условия соединения ON", min_length=1)
    alias: Optional[str] = Field(default=None, description="Псевдоним таблицы")

class JOINQ(BaseModel):
    joins: List[JoinItem] = Field(default_factory=list, description="Список JOIN операций")


# === 8. LimitQ ===
class LimitQ(BaseModel):
    limit: Optional[int] = Field(default=None, description="Максимальное количество строк", ge=0, le=10000)
    offset: int = Field(default=0, description="Смещение выборки", ge=0)


# === 9. NullCheckQ ===
class NullCheckQ(BaseModel):
    column: str = Field(..., description="Столбец для проверки")
    is_null: bool = Field(..., description="True → IS NULL, False → IS NOT NULL")


class OrderItem(BaseModel):
    column: str = Field(..., description="Столбец для сортировки")
    direction: SortDirection = Field(default="ASC", description="Направление сортировки")
    nulls: Optional[Literal["FIRST", "LAST"]] = Field(default=None, description="Позиция NULL: NULLS FIRST / LAST")

class SortQ(BaseModel):
    orders: List[OrderItem] = Field(..., description="Список правил ORDER BY", min_length=1)


class WhereQ(BaseModel):
    conditions: List[BaseCondition] = Field(default_factory=list, description="Условия WHERE")
    logical_op: Literal["AND", "OR"] = Field(default="AND", description="Логический оператор между условиями")