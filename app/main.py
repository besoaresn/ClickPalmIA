"""Entrypoint do extrator agêntico.

Uso:  python -m app.main
"""
import asyncio
import os

from app.core.config import SHEET_URL, GEMINI_API_KEY, USER, PASS
from app.pipeline.graph import Pipeline, build_graph


def _avisar_config() -> None:
    """Avisa (sem abortar) sobre config faltando/placeholder — a causa comum de
    'Invalid URL url_de_auth' (upload falha) e de login no portal não funcionar."""
    problemas = []
    if not USER or not PASS:
        problemas.append("PORTAL_USER / PORTAL_PASS vazios (login no portal vai falhar).")
    for var in ("CLICKPALM_LOGIN_URL", "CLICKPALM_UPLOAD_URL"):
        val = (os.getenv(var) or "").strip()
        if not val or not val.lower().startswith("http"):
            problemas.append(f"{var}='{val or '(vazio)'}' não é uma URL http(s) — o upload à API vai falhar.")
    if problemas:
        print("\n⚠️  AVISO DE CONFIGURAÇÃO (.env):")
        for p in problemas:
            print(f"   - {p}")
        print("   Os PDFs serão baixados localmente, mas o envio à API não vai funcionar.\n")


async def _run() -> None:
    if not GEMINI_API_KEY:
        print("ERRO: configure GEMINI_API_KEY no .env.")
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
    print("\n[INÍCIO] 🚀 Pipeline agêntico (browser-use + Gemini + LangGraph)")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
