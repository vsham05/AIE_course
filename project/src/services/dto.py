from pydantic import BaseModel, Field
from typing import Dict, List


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
    question: str = Field(..., min_length=1, max_length=2000)
    schema: DatabaseSchema


class ClassifyResponse(BaseModel):
    intents: List[str]
    question: str


class GenerateRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    schema: DatabaseSchema
    base_table: str = Field(..., min_length=1, max_length=128)


class GenerateResponse(BaseModel):
    sql: str
    intents: List[str]
    components_used: List[str]