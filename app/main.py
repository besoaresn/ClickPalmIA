"""Entrypoint do extrator agêntico.

Uso:  python -m app.main
"""
import asyncio

from app.core.config import (
    GEMINI_API_KEY, LLM_PROVIDER, SHEET_URL, USER, PASS,
)
from app.pipeline.graph import Pipeline, build_graph


def _avisar_config() -> None:
    """Avisa (sem abortar) sobre config faltando/placeholder."""
    problemas = []
    if not USER or not PASS:
        problemas.append("PORTAL_USER / PORTAL_PASS vazios (login no portal vai falhar).")
    if problemas:
        print("\n⚠️  AVISO DE CONFIGURAÇÃO (.env):")
        for p in problemas:
            print(f"   - {p}")
        print("   Corrija a configuração antes de rodar o lote.\n")


async def _run() -> None:
    if LLM_PROVIDER == "gemini" and not GEMINI_API_KEY:
        print("ERRO: configure GEMINI_API_KEY no .env.")
        return
    valid_llm_providers = {"gemini", "bedrock", "aws_bedrock", "anthropic_bedrock", "claude_bedrock"}
    if LLM_PROVIDER not in valid_llm_providers:
        print("ERRO: LLM_PROVIDER inválido. Use 'gemini' ou 'bedrock'.")
        return
    if not SHEET_URL:
        print("ERRO: configure SHEET_URL no .env.")
        return

    _avisar_config()

    pipeline = Pipeline()
    graph = build_graph(pipeline)
    try:
        # recursion_limit alto: o grafo faz loop de 1 nó por paciente.
        await graph.ainvoke({}, config={"recursion_limit": 10_000})
    finally:
        # Rede de segurança: garante browser fechado + relatórios gerados mesmo
        # se o grafo levantar exceção no meio do lote.
        await pipeline.shutdown()


def main() -> None:
    print(f"\n[INÍCIO] 🚀 Pipeline agêntico (browser-use + {LLM_PROVIDER} + LangGraph)")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
