import os
import json
import numpy as np
import torch
from pathlib import Path
from typing import List, Union, Optional, Dict
from transformers import AutoTokenizer, AutoModelForSequenceClassification


class MultiLabelSQLClient:    
    DEFAULT_CLASSES = [
        "AggregationQ", "DateFilterQ", "DistinctQ", "GroupQ", "HavingQ",
        "InListQ", "JOINQ", "LimitQ", "NullCheckQ", "SortQ", "WhereQ"
    ]
    
    def __init__(
        self,
        model_dir: str,
        device: Optional[str] = None,
        classes_file: Optional[str] = None,
        threshold: float = 0.5
    ):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.model_dir = Path(model_dir)
        self.threshold = threshold
        
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_dir, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(self.model_dir, local_files_only=True)
        self.model.to(self.device)
        self.model.eval()
        
        if classes_file and os.path.exists(classes_file):
            with open(classes_file, 'r', encoding='utf-8') as f:
                self.classes = json.load(f)
        else:
            self.classes = self.DEFAULT_CLASSES
        
        self.id2label = {i: label for i, label in enumerate(self.classes)}
    
    def _prepare_input(self, question: str, schema: Optional[Union[dict, str]] = None) -> str:
        if schema is None:
            return question
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError:
                return question
        if not isinstance(schema, dict):
            return question
        
        parts = []
        for table, columns in schema.items():
            if isinstance(columns, dict):
                cols = ', '.join(f"{col}({dtype})" for col, dtype in columns.items())
            elif isinstance(columns, list):
                cols = ', '.join(str(c) for c in columns)
            else:
                cols = str(columns)
            parts.append(f"{table}: [{cols}]")
        schema_text = ' | '.join(parts)
        return f"{question} [SCHEMA] {schema_text}"
    
    def _encode(self, texts: Union[str, List[str]], max_length: int = 128) -> Dict[str, torch.Tensor]:
        if isinstance(texts, str):
            texts = [texts]
        encodings = self.tokenizer(
            texts,
            max_length=max_length,
            truncation=True,
            padding=True,
            return_tensors='pt'
        )
        return {k: v.to(self.device) for k, v in encodings.items()}
    
    def predict(
        self,
        question: str,
        schema: Optional[Union[dict, str]] = None,
        return_scores: bool = False,
        max_length: int = 128
    ) -> Union[List[str], Dict[str, Union[List[str], Dict[str, float]]]]:
        input_text = self._prepare_input(question, schema)
        inputs = self._encode(input_text, max_length=max_length)
        
        with torch.no_grad():
            outputs = self.model(**inputs)
            logits = outputs.logits.cpu().numpy()
        
        probs = 1 / (1 + np.exp(-logits[0]))
        
        if return_scores:
            result = {
                'labels': [],
                'scores': {}
            }
            for i, prob in enumerate(probs):
                label = self.id2label[i]
                if prob >= self.threshold:
                    result['labels'].append(label)
                    result['scores'][label] = float(prob)
            return result
        
        predicted = [self.id2label[i] for i, prob in enumerate(probs) if prob >= self.threshold]
        return predicted
    
    def predict_batch(
        self,
        questions: List[str],
        schemas: Optional[List[Optional[Union[dict, str]]]] = None,
        return_scores: bool = False,
        batch_size: int = 8,
        max_length: int = 128
    ) -> List[Union[List[str], Dict[str, Union[List[str], Dict[str, float]]]]]:
        if schemas is None:
            schemas = [None] * len(questions)
        
        inputs = [self._prepare_input(q, s) for q, s in zip(questions, schemas)]
        results = []
        
        for i in range(0, len(inputs), batch_size):
            batch = inputs[i:i + batch_size]
            encoded = self._encode(batch, max_length=max_length)
            
            with torch.no_grad():
                outputs = self.model(**encoded)
                logits = outputs.logits.cpu().numpy()
            
            for j, logit in enumerate(logits):
                probs = 1 / (1 + np.exp(-logit))
                if return_scores:
                    result = {'labels': [], 'scores': {}}
                    for k, prob in enumerate(probs):
                        label = self.id2label[k]
                        if prob >= self.threshold:
                            result['labels'].append(label)
                            result['scores'][label] = float(prob)
                    results.append(result)
                else:
                    predicted = [self.id2label[k] for k, prob in enumerate(probs) if prob >= self.threshold]
                    results.append(predicted)
        
        return results
    
    def set_threshold(self, threshold: float):
        self.threshold = threshold