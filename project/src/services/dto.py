from pydantic import BaseModel, Field
from typing import Dict, List


SCHEMA_EXAMPLE = {
    "employees": {"id": "INT", "name": "VARCHAR", "salary": "FLOAT"},
    "departments": {"id": "INT", "name": "VARCHAR"}
}

class ColumnSpec(BaseModel):
    """Спецификация столбца."""
    dtype: str = Field(..., description="Тип данных столбца")


class TableSpec(BaseModel):
    """Спецификация таблицы."""
    columns: Dict[str, ColumnSpec] = Field(..., description="Столбцы таблицы")


class DatabaseSchema(BaseModel):
    """Схема базы данных."""
    tables: Dict[str, TableSpec] = Field(..., description="Таблицы и их схемы")
    
    def to_flat(self) -> Dict[str, Dict[str, str]]:
        """Конвертация в плоский формат {table: {column: dtype}}."""
        return {
            table: {col: spec.dtype for col, spec in spec_table.columns.items()}
            for table, spec_table in self.tables.items()
        }
    
    @classmethod
    def from_flat(cls, data: Dict[str, Dict[str, str]]) -> "DatabaseSchema":
        """Создание из плоского формата."""
        return cls(
            tables={
                table: TableSpec(columns={col: ColumnSpec(dtype=dtype) for col, dtype in cols.items()})
                for table, cols in data.items()
            }
        )


class ClassifyRequest(BaseModel):
    question: str = Field(...)
    schema: Dict[str, Dict[str, str]] = Field(
        ...,
        json_schema_extra={"example": SCHEMA_EXAMPLE}
    )


class ClassifyResponse(BaseModel):
    intents: List[str]
    question: str


class GenerateRequest(BaseModel):
    question: str = Field(..., description="Вопрос пользователя")
    schema: Dict[str, Dict[str, str]] = Field(
        ...,
        description="Схема БД: {таблица: {колонка: тип}}",
        json_schema_extra={"example": SCHEMA_EXAMPLE}  # ← перебивает additionalProp
    )
    base_table: str = Field(..., description="Основная таблица")


class GenerateResponse(BaseModel):
    sql: str
    intents: List[str]
    components_used: List[str]

