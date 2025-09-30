from loguru import logger

from .stateless_llm.stateless_llm_interface import StatelessLLMInterface
from .stateless_llm.openai_compatible_llm import AsyncLLM as OpenAICompatibleLLM

class LLMFactory:
    @staticmethod
    def create_llm(llm_provider: str, **kwargs) -> StatelessLLMInterface:
        """Create an LLM based on the configuration.

        Args:
            llm_provider: The type of LLM to create
            **kwargs: Additional arguments
        """
        logger.info(f"Initializing LLM: {llm_provider}")

        if llm_provider in {
            "openai_compatible_llm",
            "openai_llm",
            "gemini_llm",
            "zhipu_llm",
            "deepseek_llm",
            "groq_llm",
            "mistral_llm",
            "lmstudio_llm",
        }:
            required_keys = ["model", "base_url"]
            missing = [k for k in required_keys if not kwargs.get(k)]
            if missing:
                raise ValueError(
                    f"Missing required LLM config for {llm_provider}: {', '.join(missing)}"
                )

            params = {
                k: v
                for k, v in {
                    "model": kwargs.get("model"),
                    "base_url": kwargs.get("base_url"),
                    "llm_api_key": kwargs.get("llm_api_key"),
                    "organization_id": kwargs.get("organization_id"),
                    "project_id": kwargs.get("project_id"),
                    "temperature": kwargs.get("temperature"),
                }.items()
                if v is not None
            }

            return OpenAICompatibleLLM(**params)
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_provider}")


# Creating an LLM instance using a factory
# llm_instance = LLMFactory.create_llm("ollama", **config_dict)
