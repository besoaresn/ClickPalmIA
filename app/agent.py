"""Camada de agente: monta o browser-use Agent (Gemini + tools) por paciente
e devolve a saída estruturada (SaidaAgente)."""
from browser_use import Agent, Browser, ChatGoogle

from app.config import (
    GEMINI_API_KEY, GEMINI_MODEL, HEADLESS_MODE, DOWNLOAD_DIR,
)
from app.models import Paciente, SaidaAgente
from app.prompts import build_task
from app.tools import tools

MAX_STEPS = 60


def build_llm() -> ChatGoogle:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY não configurada no .env")
    return ChatGoogle(model=GEMINI_MODEL, api_key=GEMINI_API_KEY)


def build_browser() -> Browser:
    """Uma única sessão de browser para o lote (login uma vez, como o RPA maduro)."""
    return Browser(headless=HEADLESS_MODE, downloads_path=DOWNLOAD_DIR)


async def run_patient(browser: Browser, llm: ChatGoogle, paciente: Paciente) -> SaidaAgente:
    task = build_task(paciente.nome, paciente.cpf)
    agent = Agent(
        task=task,
        llm=llm,
        browser=browser,
        tools=tools,
        output_model_schema=SaidaAgente,
        use_vision=False,
    )
    history = await agent.run(max_steps=MAX_STEPS)
    saida = history.structured_output
    return saida if isinstance(saida, SaidaAgente) else SaidaAgente()
