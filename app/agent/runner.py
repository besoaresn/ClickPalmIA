"""Camada de agente: monta o browser-use Agent (Gemini + tools) por paciente
e devolve a saída estruturada (SaidaAgente)."""
from browser_use import Agent, Browser, ChatGoogle

from app.core.config import (
    GEMINI_API_KEY, GEMINI_MODEL, GEMINI_FALLBACK_MODEL, HEADLESS_MODE, DOWNLOAD_DIR,
)
from app.domain.models import Paciente, SaidaAgente
from app.agent.prompts import build_task
from app.agent.tools import tools

MAX_STEPS = 60


def _make_llm(model: str) -> ChatGoogle:
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
        api_key=GEMINI_API_KEY,
        temperature=0.1,
        max_output_tokens=16384,
    )
    if "gemini-3" in model and "flash" in model:
        kwargs["thinking_level"] = "low"      # Gemini 3 Flash: segura o thinking
    elif "gemini-2.5" in model:
        kwargs["thinking_budget"] = 2048      # Gemini 2.5: limita o thinking
    return ChatGoogle(**kwargs)


def build_llm() -> ChatGoogle:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")
    return _make_llm(GEMINI_MODEL)


def build_fallback_llm() -> ChatGoogle:
    """LLM de reserva para quando o principal retorna 503 (alta demanda)."""
    return _make_llm(GEMINI_FALLBACK_MODEL)


def build_browser() -> Browser:
    """Uma única sessão de browser para o lote (login uma vez, como o RPA maduro).

    keep_alive=True é ESSENCIAL: sem isso, o Agent mata o browser ao fim de cada
    run() (browser_profile.keep_alive=False -> session.kill()), e o próximo
    paciente roda em cima de um browser desconectado ('browser not connected')."""
    return Browser(headless=HEADLESS_MODE, downloads_path=DOWNLOAD_DIR, keep_alive=True)


async def run_patient(browser: Browser, llm: ChatGoogle, paciente: Paciente,
                      fallback_llm: ChatGoogle | None = None) -> SaidaAgente:
    task = build_task(paciente.nome, paciente.cpf)
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        tools=tools,
        output_model_schema=SaidaAgente,
        use_vision=False,
        fallback_llm=fallback_llm,
    )
    history = await agent.run(max_steps=MAX_STEPS)
    saida = history.structured_output
    return saida if isinstance(saida, SaidaAgente) else SaidaAgente()
