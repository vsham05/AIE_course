import logging
import copy
import json
from typing import Any, Dict, Optional, Type
import requests
from pydantic import BaseModel, TypeAdapter

logger = logging.getLogger(__name__)

class LLMClientError(Exception): pass
class SchemaPreparationError(LLMClientError): pass
class ResponseParseError(LLMClientError): pass


def flatten_json_schema(schema: Dict[str, Any], *, max_depth: int = 10) -> Dict[str, Any]:
    try:
        flat = copy.deepcopy(schema)
        defs = flat.pop("$defs", flat.pop("definitions", {}))
        if not defs:
            return _cleanup_schema(flat)
        return _cleanup_schema(_inline_refs(flat, defs, depth=0, max_depth=max_depth))
    except Exception as e:
        raise SchemaPreparationError(f"Failed to flatten JSON schema: {e}") from e


def _inline_refs(obj: Any, defs: Dict[str, Any], depth: int, max_depth: int) -> Any:
    if depth > max_depth:
        return {"type": "object", "description": "[circular reference]"}
    if isinstance(obj, dict):
        if "$ref" in obj:
            ref_name = obj["$ref"].split("/")[-1]
            if ref_name in defs:
                return _inline_refs(copy.deepcopy(defs[ref_name]), defs, depth + 1, max_depth)
            return obj
        return {k: _inline_refs(v, defs, depth, max_depth) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_inline_refs(i, defs, depth, max_depth) for i in obj]
    return obj


def _cleanup_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Удаляет метаданные Pydantic, оставляя только валидационную структуру."""
    remove_keys = {"title", "description", "examples", "default", "markdownDescription"}
    cleaned = {k: v for k, v in schema.items() if k not in remove_keys}
    
    if "properties" in cleaned and isinstance(cleaned["properties"], dict):
        cleaned["properties"] = {
            k: _cleanup_schema(v) if isinstance(v, dict) else v 
            for k, v in cleaned["properties"].items()
        }
    if "items" in cleaned and isinstance(cleaned["items"], dict):
        cleaned["items"] = _cleanup_schema(cleaned["items"])
        
    return cleaned


class OllamaStructuredClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen3.5:2b-q4_k_m",
        timeout: int = 60
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._session = requests.Session()

    def _prepare_schema(self, response_model: Type[BaseModel]) -> Dict[str, Any]:
        return flatten_json_schema(response_model.model_json_schema())

    def generate(
        self,
        prompt: str,
        response_model: Type[BaseModel],
        options: Optional[Dict[str, Any]] = None
    ) -> BaseModel:
        schema = self._prepare_schema(response_model)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": schema,
            "stream": False,
            "temperature": 0.0,
            "options": {
                "num_ctx": (options or {}).get("num_ctx", 2048),
                "num_thread": (options or {}).get("num_thread", 6),
                "num_predict": (options or {}).get("num_predict", 256)
            }
        }

        last_error = None
        for attempt in range(1, 3):
            try:
                resp = self._session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout
                )
                resp.raise_for_status()
                raw_json = resp.json().get("response", "").strip()
                if not raw_json:
                    raise ResponseParseError("Empty response from model")

                return TypeAdapter(response_model).validate_python(json.loads(raw_json))

            except requests.HTTPError as e:
                last_error = e
                if e.response.status_code == 500 and attempt == 1:
                    logger.warning("LLM server returned 500, retrying with soft JSON mode")
                    payload["format"] = {"type": "json_object"}
                    continue
                raise LLMClientError(f"HTTP {e.response.status_code} on attempt {attempt}") from e
            except json.JSONDecodeError as e:
                raise ResponseParseError(f"Invalid JSON from LLM: {e}") from e
            except Exception as e:
                raise LLMClientError(f"Unexpected error on attempt {attempt}: {e}") from e

        raise LLMClientError(f"Generation failed after 2 attempts: {last_error}")