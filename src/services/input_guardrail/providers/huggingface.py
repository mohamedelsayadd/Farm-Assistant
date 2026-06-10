import asyncio
import logging
import time

from services.input_guardrail.interface import GuardrailResult, InputGuardrail


logger = logging.getLogger(__name__)


class HuggingFaceInputGuardrail(InputGuardrail):
    def __init__(self, model_name: str, max_tokens: int, block_threshold: float) -> None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch

        self.model_name = model_name
        self.max_tokens = max_tokens
        self.block_threshold = block_threshold
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self.model.to(self.device)
        self.model.eval()
        logger.info("huggingface_input_guardrail_initialized model=%s device=%s", model_name, self.device)

    async def check(self, message: str) -> GuardrailResult:
        return await asyncio.to_thread(self._classify, message)

    def _classify(self, message: str) -> GuardrailResult:
        start_time = time.perf_counter()
        try:
            inputs = self.tokenizer(
                message,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self.max_tokens,
            ).to(self.device)
            with self.torch.no_grad():
                logits = self.model(**inputs).logits

            probabilities = self.torch.nn.functional.softmax(logits, dim=-1)
            predicted_class_id = self.torch.argmax(probabilities, dim=-1).item()
            label = self._get_label(predicted_class_id)
            score = probabilities[0][predicted_class_id].item()
            unsafe_score = score if label != "BENIGN" else 0.0
            allowed = unsafe_score < self.block_threshold
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "input_guardrail_completed provider=huggingface model=%s label=%s unsafe_score=%.4f allowed=%s duration_ms=%.2f",
                self.model_name,
                label,
                unsafe_score,
                allowed,
                duration_ms,
            )
            return GuardrailResult(
                allowed=allowed,
                label=label,
                score=unsafe_score,
                reason=None if allowed else "unsafe_prompt_detected",
            )
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "input_guardrail_failed provider=huggingface model=%s duration_ms=%.2f",
                self.model_name,
                duration_ms,
            )
            raise

    def _get_label(self, class_id: int) -> str:
        id_to_label = getattr(self.model.config, "id2label", {})
        return str(id_to_label.get(class_id, class_id)).upper()
