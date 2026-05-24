from typing import Dict, Type
from src.models.llm.llm_client import OllamaStructuredClient
from src.models.llm.models import (
    DateFilterQ, GroupQ, AggregationQ, InListQ, DistinctQ,
    HavingQ, JOINQ, LimitQ, NullCheckQ, SortQ, WhereQ
)
from src.models.multilabel_classifier import MultiLabelSQLClient
from src.models.llm.prompts.prompt_builder import SchemaAwareValidator, build_prompt
from src.features.sql_assembler import SQLAssembler

# Выносим маппинг наружу: создаётся один раз при импорте модуля
CLASS_TO_MODEL: Dict[str, Type] = {
    "AggregationQ": AggregationQ,
    "DateFilterQ": DateFilterQ,
    "DistinctQ": DistinctQ,
    "GroupQ": GroupQ,
    "HavingQ": HavingQ,
    "InListQ": InListQ,
    "JOINQ": JOINQ,
    "LimitQ": LimitQ,
    "NullCheckQ": NullCheckQ,
    "SortQ": SortQ,
    "WhereQ": WhereQ,
}

def generate_with_ollama(
    question: str,
    db_schema: Dict[str, Dict[str, str]],
    classifier: MultiLabelSQLClient,
    base_table: str,
    model_name: str = "qwen3.5:2b-q4_k_m"
) -> str:
    """Полный пайплайн: классификация → генерация → сборка."""
    
    validator = SchemaAwareValidator(db_schema)
    assembler = SQLAssembler(base_table, validator)
    
    # 1. Классификация вопроса
    active_classes = classifier.predict(question, schema=db_schema)
    print(f" Активные классы: {active_classes}")
    
    # 2. Инициализация LLM-клиента (СТРОГО ОДИН РАЗ)
    llm_client = OllamaStructuredClient(model=model_name)
    
    components = {}
    for cls_name in active_classes:
        if cls_name not in CLASS_TO_MODEL:
            continue
            
        model_cls = CLASS_TO_MODEL[cls_name]
        prompt = build_prompt(cls_name, question, db_schema, model_cls)
        
        try:
            # 3. Генерация с гарантированным JSON Schema
            result = llm_client.generate(prompt, model_cls)
            
            # 4. Бизнес-валидация столбцов
            if cls_name == "AggregationQ":
                for agg in result.aggregations:
                    validator.validate_agg_column(agg.column, agg.function)
            elif cls_name == "DateFilterQ":
                validator.validate_date_column(result.column)
            elif hasattr(result, "conditions"):
                for cond in result.conditions:
                    validator.validate_column(cond.column, f"{cls_name}: ")
                    
            components[cls_name] = result
            print(f"✅ Успешно: {cls_name}")
            
        except Exception as e:
            print(f" Пропуск {cls_name}: {e}")
            # Компонент не добавляется в components → SQL соберётся без него
            
    # 5. Финальная сборка
    return assembler.assemble(components)


# ========================
# ЗАПУСК / ТЕСТ
# ========================
if __name__ == "__main__":
    DB_SCHEMA = {
        "orders": {
            "id": "integer",
            "user_id": "integer",
            "total": "decimal",
            "created_at": "timestamp",
            "status": "enum(pending,completed,cancelled)"
        },
        "users": {
            "id": "integer",
            "name": "varchar",
            "email": "varchar", 
            "is_active": "boolean"
        }
    }

    # Старый OllamaClient больше не нужен в этом пайплайне
    classifier = MultiLabelSQLClient(model_dir="artifacts/bert_bird_finetuned/checkpoint-6188")

    sql = generate_with_ollama(
        question="Show the top 5 active users by the amount of completed orders for 2024",
        db_schema=DB_SCHEMA,
        classifier=classifier,
        base_table="orders",
        model_name="qwen3:1.7b"  # Можно переключить на qwen3:0.6b-q4_k_m для скорости
    )

    print("\n📄 Итоговый SQL:")
    print(sql)