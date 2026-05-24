import logging
from typing import Dict, Any, List

from pydantic import BaseModel

from src.models.llm.models import BaseCondition
from src.models.llm.prompts.prompt_builder import SchemaAwareValidator

logger = logging.getLogger(__name__)

class AssemblyError(Exception):
    """Ошибка сборки SQL-запроса."""
    pass


class SQLAssembler:
    """Собирает валидированные компоненты в итоговый SQL."""
    
    def __init__(self, base_table: str, schema_validator: SchemaAwareValidator):
        self.base_table = base_table
        self.validator = schema_validator

    def assemble(self, components: Dict[str, BaseModel]) -> str:
        try:
            parts = [
                f"SELECT {self._build_select(components)}",
                f"FROM {self.base_table}"
            ]
            parts.extend(self._build_joins(components))
            
            where_conds = self._build_where(components)
            if where_conds:
                parts.append(f"WHERE {' AND '.join(where_conds)}")

            if "GroupQ" in components and components["GroupQ"].columns:
                parts.append(f"GROUP BY {', '.join(components['GroupQ'].columns)}")

            if "HavingQ" in components and components["HavingQ"].conditions:
                op = components["HavingQ"].logical_op
                having = [self._format_condition(c) for c in components["HavingQ"].conditions]
                parts.append(f"HAVING {' ' + op + ' '.join(having)}")

            if "SortQ" in components and components["SortQ"].orders:
                orders = [
                    f"{o.column} {o.direction}" + (f" NULLS {o.nulls}" if o.nulls else "")
                    for o in components["SortQ"].orders
                ]
                parts.append(f"ORDER BY {', '.join(orders)}")

            if "LimitQ" in components:
                lim = components["LimitQ"]
                if lim.limit is not None:
                    parts.append(f"LIMIT {lim.limit}")
                if lim.offset > 0:
                    parts.append(f"OFFSET {lim.offset}")

            return " ".join(parts) + ";"
        except Exception as e:
            logger.error("SQL assembly failed: %s", e)
            raise AssemblyError(f"Failed to assemble SQL: {e}") from e

    def _build_select(self, components: Dict[str, BaseModel]) -> str:
        items = ["*"]
        if "AggregationQ" in components and components["AggregationQ"].aggregations:
            items = []
            for agg in components["AggregationQ"].aggregations:
                col = agg.column if agg.column != "*" else ""
                distinct = "DISTINCT " if agg.distinct else ""
                items.append(f"{agg.function}({distinct}{col}) AS {agg.alias}")

        prefix = ""
        if "DistinctQ" in components and components["DistinctQ"].is_distinct:
            cols = components["DistinctQ"].columns
            prefix = f"DISTINCT ON ({', '.join(cols)}) " if cols else "DISTINCT "

        return f"{prefix}{', '.join(items)}"

    def _build_joins(self, components: Dict[str, BaseModel]) -> List[str]:
        if "JOINQ" not in components:
            return []
        joins = []
        for j in components["JOINQ"].joins:
            on_conds = [f"{c.left_column} {c.operator} {c.right_column}" for c in j.on]
            alias = f" AS {j.alias}" if j.alias else ""
            joins.append(f"{j.join_type} JOIN {j.table}{alias} ON {' AND '.join(on_conds)}")
        return joins

    def _build_where(self, components: Dict[str, BaseModel]) -> List[str]:
        conds = []

        if "WhereQ" in components and components["WhereQ"].conditions:
            for c in components["WhereQ"].conditions:
                conds.append(self._format_condition(c))

        if "DateFilterQ" in components:
            df = components["DateFilterQ"]
            if df.relative:
                conds.append(f"{df.column} >= NOW() - INTERVAL '1 {df.unit}'")
            else:
                if df.start_date:
                    conds.append(f"{df.column} >= '{df.start_date}'")
                if df.end_date:
                    conds.append(f"{df.column} <= '{df.end_date}'")

        if "InListQ" in components:
            il = components["InListQ"]
            vals = ", ".join(self._sql_value(v) for v in il.values)
            neg = "NOT " if il.negate else ""
            conds.append(f"{il.column} {neg}IN ({vals})")

        if "NullCheckQ" in components:
            nc = components["NullCheckQ"]
            conds.append(f"{nc.column} {'IS NULL' if nc.is_null else 'IS NOT NULL'}")

        return conds

    def _format_condition(self, c: BaseCondition) -> str:
        if c.operator in ("IS NULL", "IS NOT NULL"):
            return f"{c.column} {c.operator}"
        return f"{c.column} {c.operator} {self._sql_value(c.value)}"

    @staticmethod
    def _sql_value(val: Any) -> str:
        if val is None: return "NULL"
        if isinstance(val, bool): return str(val).upper()
        if isinstance(val, (int, float)): return str(val)
        if isinstance(val, list): return f"({', '.join(SQLAssembler._sql_value(v) for v in val)})"
        return f"'{str(val)}'"