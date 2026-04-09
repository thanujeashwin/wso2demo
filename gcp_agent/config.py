from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── LLM ──────────────────────────────────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    timeout: float = Field(default=30.0)
    max_retries: int = Field(default=2)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def build_llm(self):
        if self.anthropic_api_key:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=self.anthropic_model,
                api_key=self.anthropic_api_key,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        if self.openai_api_key:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=self.openai_model,
                api_key=self.openai_api_key,
                timeout=self.timeout,
                max_retries=self.max_retries,
            )
        raise ValueError(
            "No LLM API key configured. "
            "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in environment or .env"
        )


settings = Settings()
