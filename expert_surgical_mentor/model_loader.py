"""Lazy, inference-only loading for the approved 4-bit VLM candidates."""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass
from pathlib import Path


class ModelConfigurationError(ValueError):
    """Raised when the model catalog does not satisfy the local inference policy."""


class ModelDependencyError(RuntimeError):
    """Raised when optional VLM inference dependencies are unavailable."""


@dataclass(frozen=True, slots=True)
class QuantizationSettings:
    load_in_4bit: bool
    quant_type: str
    use_double_quant: bool
    compute_dtype: str


@dataclass(frozen=True, slots=True)
class ModelSpec:
    key: str
    model_id: str
    model_class: str
    priority: int
    quantization: QuantizationSettings


@dataclass(frozen=True, slots=True)
class LoadedVlm:
    spec: ModelSpec
    model: object
    processor: object


class ModelCatalog:
    def __init__(self, default_model: str, models: tuple[ModelSpec, ...]) -> None:
        if not models:
            raise ModelConfigurationError("최소 한 개의 VLM 설정이 필요합니다.")
        if len({model.key for model in models}) != len(models):
            raise ModelConfigurationError("VLM key가 중복되었습니다.")
        if default_model not in {model.key for model in models}:
            raise ModelConfigurationError("default_model이 models에 없습니다.")

        for model in models:
            quantization = model.quantization
            if not quantization.load_in_4bit:
                raise ModelConfigurationError(f"{model.key}는 4-bit 양자화를 사용해야 합니다.")
            if quantization.quant_type != "nf4":
                raise ModelConfigurationError(f"{model.key}의 quant_type은 nf4여야 합니다.")
            if quantization.compute_dtype != "bfloat16":
                raise ModelConfigurationError(
                    f"{model.key}의 compute_dtype은 bfloat16이어야 합니다."
                )

        self.default_model = default_model
        self.models = tuple(sorted(models, key=lambda model: model.priority))
        self._by_key = {model.key: model for model in self.models}

    @classmethod
    def from_file(cls, path: str | Path) -> "ModelCatalog":
        config_path = Path(path)
        try:
            payload = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ModelConfigurationError(f"VLM 설정을 읽을 수 없습니다: {config_path}") from error

        try:
            default_model = payload["default_model"]
            raw_models = payload["models"]
        except (KeyError, TypeError) as error:
            raise ModelConfigurationError("VLM 설정의 필수 필드가 없습니다.") from error
        if not isinstance(default_model, str) or not isinstance(raw_models, list):
            raise ModelConfigurationError("default_model 또는 models 형식이 잘못되었습니다.")

        models: list[ModelSpec] = []
        for raw_model in raw_models:
            try:
                raw_quantization = raw_model["quantization"]
                quantization = QuantizationSettings(
                    load_in_4bit=raw_quantization["load_in_4bit"],
                    quant_type=raw_quantization["quant_type"],
                    use_double_quant=raw_quantization["use_double_quant"],
                    compute_dtype=raw_quantization["compute_dtype"],
                )
                models.append(
                    ModelSpec(
                        key=raw_model["key"],
                        model_id=raw_model["model_id"],
                        model_class=raw_model["model_class"],
                        priority=raw_model["priority"],
                        quantization=quantization,
                    )
                )
            except (KeyError, TypeError) as error:
                raise ModelConfigurationError("VLM 모델 항목 형식이 잘못되었습니다.") from error

        return cls(default_model, tuple(models))

    def get(self, key: str | None = None) -> ModelSpec:
        resolved_key = key or self.default_model
        try:
            return self._by_key[resolved_key]
        except KeyError as error:
            raise ModelConfigurationError(f"등록되지 않은 VLM key입니다: {resolved_key}") from error


class QuantizedVlmLoader:
    """Load one model at a time with an enforced bitsandbytes 4-bit policy."""

    def __init__(self, catalog: ModelCatalog) -> None:
        self._catalog = catalog

    def load(self, key: str | None = None) -> LoadedVlm:
        spec = self._catalog.get(key)
        try:
            torch = importlib.import_module("torch")
            transformers = importlib.import_module("transformers")
        except ImportError as error:
            raise ModelDependencyError(
                "VLM 실행 의존성이 없습니다. requirements-vlm.txt를 설치하세요."
            ) from error

        try:
            model_type = getattr(transformers, spec.model_class)
            processor_type = getattr(transformers, "AutoProcessor")
            bitsandbytes_config_type = getattr(transformers, "BitsAndBytesConfig")
            compute_dtype = getattr(torch, spec.quantization.compute_dtype)
        except AttributeError as error:
            raise ModelDependencyError(
                f"설치된 torch/transformers가 {spec.model_class}를 지원하지 않습니다."
            ) from error

        quantization_config = bitsandbytes_config_type(
            load_in_4bit=spec.quantization.load_in_4bit,
            bnb_4bit_quant_type=spec.quantization.quant_type,
            bnb_4bit_use_double_quant=spec.quantization.use_double_quant,
            bnb_4bit_compute_dtype=compute_dtype,
        )
        model = model_type.from_pretrained(
            spec.model_id,
            device_map="auto",
            low_cpu_mem_usage=True,
            quantization_config=quantization_config,
            torch_dtype=compute_dtype,
        )
        processor = processor_type.from_pretrained(spec.model_id)
        return LoadedVlm(spec=spec, model=model, processor=processor)
