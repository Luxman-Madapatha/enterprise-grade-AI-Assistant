"""LLM client abstraction.

Model selection rationale (also in docs/architecture.md):

* **OpenAI-compatible** endpoint was chosen because it is the widest common
  denominator — the same client works with OpenAI, Azure OpenAI, Anthropic
  (via a gateway) and local servers such as Ollama/vLLM, simply by changing
  ``OPENAI_BASE_URL``. This keeps vendor lock-in low.
* **Temperature 0** for deterministic, auditable agent behaviour.
* A **deterministic mock** is used when no key is configured so the POC runs
  end-to-end offline; agent nodes branch on ``settings.llm_available``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class LLMClient(ABC):
    available: bool = False
    model_name: str = "mock"

    @abstractmethod
    async def generate(self, system: str, user: str) -> str:
        """Return the model's text completion."""


class MockLLM(LLMClient):
    """Offline deterministic fallback. Agent nodes avoid relying on its output."""

    available = False
    model_name = "mock"

    async def generate(self, system: str, user: str) -> str:
        return ""


class OpenAILLM(LLMClient):
    available = True

    def __init__(self) -> None:
        from langchain_openai import ChatOpenAI

        self.model_name = settings.llm_model
        self._model = ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=settings.llm_temperature,
        )

    async def generate(self, system: str, user: str) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = await self._model.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        return response.content  # type: ignore[return-value]


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is not None:
        return _llm_client
    if settings.llm_available:
        try:
            _llm_client = OpenAILLM()
            logger.info("llm_client", model=_llm_client.model_name)
            return _llm_client
        except Exception as exc:  # pragma: no cover - depends on env
            logger.warning("openai_llm_init_failed", error=str(exc))
    _llm_client = MockLLM()
    logger.info("llm_client", model="mock")
    return _llm_client
