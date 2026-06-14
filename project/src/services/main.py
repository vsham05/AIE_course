import logging
from contextlib import asynccontextmanager
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from src.settings.config import get_settings

from src.models.llm.llm_client import OllamaStructuredClient
from src.models.llm.models import (
    AggregationQ, DateFilterQ, DistinctQ, GroupQ, HavingQ, InListQ,
    JOINQ, LimitQ, NullCheckQ, SortQ, WhereQ
)
from src.models.multilabel_classifier import MultiLabelSQLClient
from src.models.llm.prompts.prompt_builder import SchemaAwareValidator, build_prompt
from src.features.sql_assembler import SQLAssembler
from src.services.dto import (
    ClassifyRequest, ClassifyResponse, GenerateRequest, GenerateResponse
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

classifier: MultiLabelSQLClient | None = None
llm_client: OllamaStructuredClient | None = None
settings = None

asynccontextmanager
async def lifespan(app: FastAPI):
    global classifier, llm_client, settings
    settings = get_settings() 
    
    logger.info("Initializing models with config: model=%s, dir=%s", 
                settings.llm_model_name, settings.classifier_model_dir)
    try:
        classifier = MultiLabelSQLClient(model_dir=settings.classifier_model_dir)
        llm_client = OllamaStructuredClient(
            model=settings.llm_model_name,
            base_url=settings.ollama_base_url,
            timeout=settings.ollama_timeout
        )
    except Exception as e:
        logger.error("Model initialization failed: %s", e)
        raise RuntimeError("Service startup failed") from e
    yield
    logger.info("Service shutting down...")

app = FastAPI(title="SQLGen API", version="1.0.0", lifespan=lifespan)

@app.get("/health")
async def health_check():
    return JSONResponse(status_code=200, content={"status": "healthy", "models_ready": bool(classifier and llm_client)})

@app.post("/api/predict", response_model=ClassifyResponse)
async def classify_intent(req: ClassifyRequest):
    if classifier is None:
        raise HTTPException(status_code=503, detail="Classifier not initialized")
    try:
        intents = classifier.predict(req.question, schema=req.schema)
        logger.info("Classified: '%s' -> %s", req.question, intents)
        return ClassifyResponse(intents=intents, question=req.question)
    except Exception as e:
        logger.error("Classification error: %s", e)
        raise HTTPException(status_code=500, detail="Classification failed")

@app.post("/api/generate", response_model=GenerateResponse)
async def generate_sql(req: GenerateRequest):
    if classifier is None or llm_client is None:
        raise HTTPException(status_code=503, detail="Models not initialized")
    try:
        schema_flat = req.schema
        active_classes = classifier.predict(req.question, schema=schema_flat)
        logger.info("Active intents for '%s': %s", req.question, active_classes)

        sql_result, used_components = _run_pipeline(
            question=req.question,
            db_schema=schema_flat,
            active_classes=active_classes,
            base_table=req.base_table
        )
        logger.info("SQL generated successfully. Components: %s", used_components)
        return GenerateResponse(sql=sql_result, intents=active_classes, components_used=used_components)
    except Exception as e:
        logger.error("Generation error: %s", e)
        raise HTTPException(status_code=500, detail="SQL generation failed")

def _run_pipeline(
    question: str,
    db_schema: Dict[str, Dict[str, str]],
    active_classes: List[str],
    base_table: str
) -> tuple[str, List[str]]:
    if llm_client is None:
        raise RuntimeError("LLM client unavailable")

    validator = SchemaAwareValidator(db_schema)
    assembler = SQLAssembler(base_table, validator)

    CLASS_MAP = {
        "AggregationQ": AggregationQ, "DateFilterQ": DateFilterQ, "DistinctQ": DistinctQ,
        "GroupQ": GroupQ, "HavingQ": HavingQ, "InListQ": InListQ, "JOINQ": JOINQ,
        "LimitQ": LimitQ, "NullCheckQ": NullCheckQ, "SortQ": SortQ, "WhereQ": WhereQ,
    }

    components: Dict[str, object] = {}
    for cls_name in active_classes:
        model_cls = CLASS_MAP.get(cls_name)
        if not model_cls:
            logger.warning("Unknown class skipped: %s", cls_name)
            continue

        prompt = build_prompt(cls_name, question, db_schema, model_cls)
        try:
            result = llm_client.generate(prompt, model_cls)
            
            if hasattr(result, "aggregations"):
                for agg in result.aggregations:
                    validator.validate_agg_column(agg.column, agg.function)
            if hasattr(result, "conditions"):
                for cond in result.conditions:
                    validator.validate_column(cond.column)
            if hasattr(result, "column"):
                validator.validate_column(result.column)

            components[cls_name] = result
        except Exception as e:
            logger.warning("Component %s failed and was skipped: %s", cls_name, e)

    return assembler.assemble(components), list(components.keys())