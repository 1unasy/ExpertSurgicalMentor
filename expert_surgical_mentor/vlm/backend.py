"""Inference adapter for Qwen-family inventory VLMs."""

import importlib
from typing import Protocol

from .inventory import VisualInventoryAssessment
from .model_loader import LoadedVlm, ModelDependencyError
from .prompt import InventoryPrompt


class VisionInventoryBackend(Protocol):
    def assess(
        self,
        image: object,
        prompt: InventoryPrompt,
    ) -> VisualInventoryAssessment:
        """Classify required tools visible in the supplied workspace image."""


class QwenVisionInventoryBackend:
    """Run deterministic image-to-JSON inference without exposing training APIs."""

    def __init__(self, loaded_vlm: LoadedVlm, max_new_tokens: int = 128) -> None:
        if max_new_tokens <= 0:
            raise ValueError("max_new_tokens는 양수여야 합니다.")
        self._loaded_vlm = loaded_vlm
        self._max_new_tokens = max_new_tokens

    def assess(
        self,
        image: object,
        prompt: InventoryPrompt,
    ) -> VisualInventoryAssessment:
        try:
            torch = importlib.import_module("torch")
            qwen_utils = importlib.import_module("qwen_vl_utils")
        except ImportError as error:
            raise ModelDependencyError(
                "Qwen VLM 추론 의존성이 없습니다. requirements-vlm.txt를 설치하세요."
            ) from error

        messages = [
            {
                "role": "system",
                "content": [{"type": "text", "text": prompt.system_text}],
            },
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt.user_text},
                ],
            },
        ]
        processor = self._loaded_vlm.processor
        model = self._loaded_vlm.model
        rendered_prompt = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        image_inputs, video_inputs = qwen_utils.process_vision_info(messages)
        inputs = processor(
            text=[rendered_prompt],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        )
        inputs = inputs.to(model.device)
        input_length = inputs["input_ids"].shape[1]

        with torch.inference_mode():
            output_ids = model.generate(
                **inputs,
                do_sample=False,
                max_new_tokens=self._max_new_tokens,
            )
        generated_ids = output_ids[:, input_length:]
        model_text = processor.batch_decode(
            generated_ids,
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )[0]
        return VisualInventoryAssessment.from_model_text(model_text)
