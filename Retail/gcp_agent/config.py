from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── LLM ──────────────────────────────────────────────────────────────────
    geminillm_url: str = ""
    geminillm_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    timeout: float = Field(default=30.0)
    max_retries: int = Field(default=2)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def build_llm(self):
        from google.genai import types as gtypes
        from langchain_google_genai import ChatGoogleGenerativeAI

        http_options = gtypes.HttpOptions(
            base_url=self.geminillm_url,
            client_args={"headers": {"API-Key": self.geminillm_api_key, "Authorization": ""}},
        )
        return ChatGoogleGenerativeAI(
            model=self.gemini_model,
            google_api_key=self.geminillm_api_key,
            http_options=http_options,
        )


settings = Settings()

