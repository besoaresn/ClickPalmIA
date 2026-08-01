"""Camada de agente: monta o browser-use Agent (LLM + tools) por paciente
e devolve a saída estruturada (SaidaAgente)."""
import asyncio
import base64
import os
from typing import Any

from browser_use import Agent, Browser, ChatGoogle
from browser_use.llm import ChatAWSBedrock
from browser_use.llm.base import BaseChatModel
from browser_use.llm.exceptions import ModelProviderError, ModelRateLimitError

from app.core.config import (
    AWS_ACCESS_KEY_ID, AWS_REGION, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN,
    BEDROCK_API_KEY, BEDROCK_AUTH_MODE, BEDROCK_FALLBACK_MODEL,
    BEDROCK_MAX_TOKENS, BEDROCK_MODEL, BEDROCK_RETRY_ATTEMPTS, GEMINI_API_KEY,
    GEMINI_FALLBACK_API_KEY, GEMINI_FALLBACK_MODEL, GEMINI_MODEL, HEADLESS_MODE,
    DOWNLOAD_DIR, LLM_PROVIDER,
)
from app.domain.models import Paciente, SaidaAgente
from app.agent.prompts import build_task
from app.agent.tools import tools
from app.reporting import ReportManager

MAX_STEPS = 60
NON_RETRYABLE_BEDROCK_MESSAGES = (
    "accessdenied",
    "could not resolve",
    "credentials not found",
    "not authorized",
    "not recognised",
    "not recognized",
    "validationexception",
)


class RetryingChatAWSBedrock(ChatAWSBedrock):
    async def ainvoke(self, messages: list, output_format: type | None = None, **kwargs: Any):
        last_error: ModelProviderError | None = None
        attempts = max(1, BEDROCK_RETRY_ATTEMPTS)

        for attempt in range(1, attempts + 1):
            try:
                return await super().ainvoke(messages, output_format, **kwargs)
            except (ModelRateLimitError, ModelProviderError) as exc:
                if not _is_retryable_bedrock_error(exc) or attempt == attempts:
                    raise
                last_error = exc
                await asyncio.sleep(min(2 ** (attempt - 1), 8))

        raise last_error or ModelProviderError(message="Bedrock falhou sem resposta", model=self.name)


def _looks_like_aws_key_pair(access_key: str, secret_key: str) -> bool:
    return access_key.startswith(("AKIA", "ASIA")) and len(access_key) == 20 and len(secret_key) >= 20


def _normalize_bedrock_api_key(api_key: str) -> str:
    key = api_key.strip()
    if key.startswith("bedrock-api-key-"):
        return key

    try:
        decoded = base64.b64decode(key, validate=True).decode("utf-8").strip()
    except Exception:
        return key

    if decoded.startswith("bedrock-api-key-"):
        return decoded
    return key


def _validate_bedrock_api_key(api_key: str) -> None:
    if not api_key:
        return
    if api_key.startswith("bedrock-api-key-"):
        return
    raise RuntimeError(
        "API key do Bedrock com formato inválido. Gere uma Bedrock API key no "
        "console da AWS e coloque o valor que começa com 'bedrock-api-key-' em "
        "AWS_BEARER_TOKEN_BEDROCK ou BEDROCK_API_KEY. Não use URL/token "
        "CallWithBearerToken em AWS_ACCESS_KEY_ID."
    )


def _is_retryable_bedrock_error(error: ModelProviderError) -> bool:
    message = getattr(error, "message", str(error)).lower()
    if any(marker in message for marker in NON_RETRYABLE_BEDROCK_MESSAGES):
        return False
    status_code = getattr(error, "status_code", 502)
    return status_code in {429, 500, 502, 503, 504}


def _configure_bedrock_credentials() -> dict:
    kwargs: dict = {}
    if AWS_REGION:
        kwargs["aws_region"] = AWS_REGION

    api_key = _normalize_bedrock_api_key(BEDROCK_API_KEY)
    access_key = AWS_ACCESS_KEY_ID.strip()
    secret_key = AWS_SECRET_ACCESS_KEY.strip()

    # A Bedrock API key deve ir em AWS_BEARER_TOKEN_BEDROCK. Se ela foi colocada
    # por engano em AWS_ACCESS_KEY_ID, evita que boto3 trate isso como chave IAM.
    if not api_key and access_key and not _looks_like_aws_key_pair(access_key, secret_key):
        if len(access_key) > 100 and len(secret_key) < 20:
            api_key = _normalize_bedrock_api_key(access_key)
        os.environ.pop("AWS_ACCESS_KEY_ID", None)
        os.environ.pop("AWS_SECRET_ACCESS_KEY", None)
        os.environ.pop("AWS_SESSION_TOKEN", None)

    if api_key:
        _validate_bedrock_api_key(api_key)
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key
        kwargs["aws_sso_auth"] = True
    elif _looks_like_aws_key_pair(access_key, secret_key):
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if AWS_SESSION_TOKEN:
            kwargs["aws_session_token"] = AWS_SESSION_TOKEN
    elif BEDROCK_AUTH_MODE in {"default", "sso", "profile"}:
        kwargs["aws_sso_auth"] = True

    return kwargs


def _make_gemini_llm(model: str, api_key: str) -> ChatGoogle:
    """ChatGoogle com thinking contido e orçamento de saída folgado.

    Sem isto o flash-lite (Gemini 3) usa thinking dinâmico (~8k tokens) com
    max_output_tokens=8096 default -> o 'thinking' consome quase todo o
    orçamento e o JSON da ação chega truncado (finish_reason=MAX_TOKENS ->
    'Failed to parse JSON response'). thinking_level='low' segura o thinking e
    max_output_tokens alto dá folga para a resposta.

    temperature baixa = agente mais determinístico. (Tem efeito aqui, no LLM;
    passar temperature= ao Agent é no-op — cai no **kwargs e é ignorado.)"""
    kwargs: dict = dict(
        model=model,
        api_key=api_key,
        temperature=0.1,
        max_output_tokens=16384,
        # 429/quota deve trocar de chave imediatamente; erros 5xx continuam
        # usando o retry/backoff interno do ChatGoogle.
        max_retries=1,
        retryable_status_codes=[500, 502, 503, 504],
    )
    if "gemini-3" in model and "flash" in model:
        kwargs["thinking_level"] = "low"      # Gemini 3 Flash: segura o thinking
    elif "gemini-2.5" in model:
        kwargs["thinking_budget"] = 2048      # Gemini 2.5: limita o thinking
    return ChatGoogle(**kwargs)


class RotatingGemini:
    """Gemini com troca permanente de chave durante o lote.

    As quotas do Gemini são por projeto. A segunda chave deve estar associada
    a outro projeto Google para funcionar como reserva real.
    """

    def __init__(self, primary: ChatGoogle, secondary: ChatGoogle | None = None):
        self._clients = [primary] + ([secondary] if secondary is not None else [])
        self._active = 0

    @property
    def provider(self) -> str:
        return "google"

    @property
    def model(self) -> str:
        return self._clients[self._active].model

    @property
    def name(self) -> str:
        return self._clients[self._active].name

    @property
    def model_name(self) -> str:
        return self.model

    async def ainvoke(self, messages: list, output_format: type | None = None, **kwargs: Any):
        try:
            return await self._clients[self._active].ainvoke(messages, output_format, **kwargs)
        except (ModelRateLimitError, ModelProviderError) as exc:
            if self._active == 0 and len(self._clients) > 1 and _is_gemini_key_rotation_error(exc):
                self._active = 1
                print(
                    f"[LLM] Gemini quota/limite atingido; alternando para a segunda chave "
                    f"(modelo {self.model})."
                )
                return await self._clients[self._active].ainvoke(messages, output_format, **kwargs)
            raise


def _is_gemini_key_rotation_error(error: ModelProviderError) -> bool:
    message = getattr(error, "message", str(error)).lower()
    status_code = getattr(error, "status_code", 502)
    markers = (
        "resource exhausted",
        "quota exceeded",
        "quota_exceeded",
        "rate limit",
        "rate_limit_exceeded",
        "too many requests",
        "insufficient credits",
        "billing",
        "daily quota",
    )
    return status_code in {401, 402, 429} or any(marker in message for marker in markers)


def _make_bedrock_llm(model: str) -> BaseChatModel:
    """Claude via AWS Bedrock.

    Usa o caminho Converse do Bedrock, que é o mesmo caminho documentado pela AWS
    para o modelId / inference profile do Opus 4.6.
    """
    kwargs: dict = dict(
        model=model,
        temperature=0.1,
        max_tokens=BEDROCK_MAX_TOKENS,
    )
    kwargs.update(_configure_bedrock_credentials())

    return RetryingChatAWSBedrock(**kwargs)


def _make_llm(model: str) -> BaseChatModel:
    if LLM_PROVIDER == "gemini":
        return _make_gemini_llm(model, GEMINI_API_KEY)
    if LLM_PROVIDER in {"bedrock", "aws_bedrock", "anthropic_bedrock", "claude_bedrock"}:
        return _make_bedrock_llm(model)
    raise RuntimeError(f"LLM_PROVIDER inválido: {LLM_PROVIDER!r}. Use 'gemini' ou 'bedrock'.")


def build_llm() -> BaseChatModel:
    if not GEMINI_API_KEY:
        if LLM_PROVIDER == "gemini":
            raise RuntimeError("GEMINI_API_KEY não configurada no .env")
    if LLM_PROVIDER == "gemini":
        primary = _make_gemini_llm(GEMINI_MODEL, GEMINI_API_KEY)
        secondary = (
            _make_gemini_llm(GEMINI_FALLBACK_MODEL, GEMINI_FALLBACK_API_KEY)
            if GEMINI_FALLBACK_API_KEY else None
        )
        return RotatingGemini(primary, secondary)
    return _make_llm(BEDROCK_MODEL)


def build_fallback_llm() -> BaseChatModel | None:
    """Fallback adicional do browser-use, usado apenas no modo Bedrock.

    No Gemini, a rotação de chave fica dentro de RotatingGemini para continuar
    ativa entre pacientes.
    """
    if LLM_PROVIDER == "gemini":
        return None
    return _make_llm(BEDROCK_FALLBACK_MODEL)


def build_browser() -> Browser:
    """Uma única sessão de browser para o lote (login uma vez, como o RPA maduro).

    keep_alive=True é ESSENCIAL: sem isso, o Agent mata o browser ao fim de cada
    run() (browser_profile.keep_alive=False -> session.kill()), e o próximo
    paciente roda em cima de um browser desconectado ('browser not connected')."""
    return Browser(headless=HEADLESS_MODE, downloads_path=DOWNLOAD_DIR, keep_alive=True)


async def run_patient(browser: Browser, llm: BaseChatModel, paciente: Paciente,
                      fallback_llm: BaseChatModel | None = None,
                      report: ReportManager | None = None) -> SaidaAgente:
    task = build_task(paciente.nome, paciente.cpf)
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        tools=tools,
        output_model_schema=SaidaAgente,
        use_vision=False,
        fallback_llm=fallback_llm,
        directly_open_url=False,
    )
    history = await agent.run(max_steps=MAX_STEPS)
    # [MÉTRICAS] Custo de LLM por execução — ver
    # docs/Deploy_AWS_Metricas_Custo_RPA_vs_APA.docx, seção 3.
    if report is not None and history.usage is not None:
        report.registrar_tokens_llm(
            history.usage.total_prompt_tokens,
            history.usage.total_completion_tokens,
        )
    saida = history.structured_output
    return saida if isinstance(saida, SaidaAgente) else SaidaAgente()
