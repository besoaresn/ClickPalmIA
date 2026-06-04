"""Entrypoint do extrator agêntico.

Uso:  python -m app.main
"""
import asyncio

from app.config import SHEET_URL, GEMINI_API_KEY
from app.graph import Pipeline, build_graph


async def _run() -> None:
    if not GEMINI_API_KEY:
        print("ERRO: configure GEMINI_API_KEY no .env.")
        return
    if not SHEET_URL:
        print("ERRO: configure SHEET_URL no .env.")
        return

    pipeline = Pipeline()
    graph = build_graph(pipeline)
    # recursion_limit alto: o grafo faz loop de 1 nó por paciente.
    await graph.ainvoke({}, config={"recursion_limit": 10_000})


def main() -> None:
    print("\n[INÍCIO] 🚀 Pipeline agêntico (browser-use + Gemini + LangGraph)")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
