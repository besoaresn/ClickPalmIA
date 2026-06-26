"""Orquestração LangGraph: o agente browser-use é um nó dentro do grafo.

Fluxo:  load_queue -> open_browser -> process_patient --(loop)--> finalize

Resumo/idempotência vêm do STATUS da planilha: paciente concluído sai da fila
(STATUS->0), então re-executar o lote retoma de onde parou.
"""
import asyncio
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

from app.core.config import SHEET_URL
from app.core.runstate import RUN
from app.domain.models import Paciente, SaidaAgente
from app.integrations.sheets import read_patients_from_gsheets, update_sheet_status
from app.reporting import ReportManager
from app.agent.runner import build_llm, build_fallback_llm, build_browser, run_patient


class PipelineState(TypedDict, total=False):
    pacientes: list[dict]
    idx: int
    erro_fatal: str


class Pipeline:
    def __init__(self):
        self.llm = build_llm()
        self.fallback_llm = build_fallback_llm()
        self.browser = None
        self.report = ReportManager()
        self._finalized = False

    # --- nós ---
    async def load_queue(self, state: PipelineState) -> PipelineState:
        res = read_patients_from_gsheets(SHEET_URL)
        if "error" in res:
            print(f"ERRO ao ler a planilha: {res['error']}")
            return {"pacientes": [], "idx": 0, "erro_fatal": res["error"]}
        pacientes = res.get("pacientes", [])
        print(f"{len(pacientes)} paciente(s) na fila (STATUS=1).")
        return {"pacientes": pacientes, "idx": 0}

    async def open_browser(self, state: PipelineState) -> PipelineState:
        if state.get("erro_fatal") or not state.get("pacientes"):
            return {}
        self.browser = build_browser()
        await self.browser.start()
        return {}

    async def process_patient(self, state: PipelineState) -> PipelineState:
        i = state["idx"]
        pac = Paciente(**state["pacientes"][i])
        print("=" * 60)
        print(f"[{i + 1}/{len(state['pacientes'])}] Processando: {pac.nome}")
        # A tool escreve as contagens diretamente no ReportManager deste paciente.
        RUN.bind(self.report, pac.nome, pac.cpf)
        try:
            saida = await run_patient(self.browser, self.llm, pac, fallback_llm=self.fallback_llm)
            self._persist(pac, saida, erro="")
        except Exception as e:
            print(f"ERRO no paciente {pac.nome}: {e}")
            self._persist(pac, SaidaAgente(), erro=str(e))
        return {"idx": i + 1}

    async def finalize(self, state: PipelineState) -> PipelineState:
        await self.shutdown()
        return {}

    async def shutdown(self) -> None:
        """Fecha o browser e gera os relatórios. Idempotente: é chamado pelo nó
        `finalize` (fluxo normal) E pelo `finally` do main (rede de segurança se
        o grafo crashar no meio), mas só executa de fato uma vez."""
        if self._finalized:
            return
        self._finalized = True

        if self.browser:
            try:
                await self.browser.kill()
                # Dá tempo dos transports do subprocess (Chromium) fecharem antes
                # de o loop encerrar -> reduz o ruído "I/O operation on closed
                # pipe" do Proactor (Windows + Python 3.13) no fim do processo.
                await asyncio.sleep(0.25)
            except Exception:
                pass

        try:
            path_erros = self.report.salvar_erros()
            path_final, conteudo = self.report.gerar_relatorio_final()
            print("\n" + conteudo)
            print(f"Relatório final: {path_final}")
            print(f"Relatório de erros: {path_erros}")
        except Exception as e:
            print(f"ERRO ao gerar relatórios: {e}")

    # --- roteamento ---
    def route(self, state: PipelineState) -> str:
        if state.get("erro_fatal") or not state.get("pacientes"):
            return "finalize"
        return "process" if state["idx"] < len(state["pacientes"]) else "finalize"

    # --- persistência por paciente ---
    def _persist(self, pac: Paciente, saida: SaidaAgente, erro: str) -> None:
        nome, cpf, row = pac.nome, pac.cpf, pac.sheet_row

        if erro:
            self.report.registrar_erro(
                paciente=nome, cpf=cpf, data_exame="", nome_exame="",
                motivo=f"Exceção na sessão do agente: {erro}", etapa="patient_session_crash",
            )
            return

        if saida.nao_encontrado:
            self.report.registrar_paciente_nao_encontrado(nome)
            self.report.registrar_erro(
                paciente=nome, cpf=cpf, data_exame="", nome_exame="",
                motivo="Paciente não retornado pela busca no portal.", etapa="patient_not_found",
            )
            update_sheet_status(SHEET_URL, row, 0)  # sai da fila, como no RPA maduro
            self.report.registrar_paciente_processado()
            return

        # As contagens (alvos/baixados/ignorados/indisponíveis/falhas) já foram
        # gravadas pela tool download_exam_report (fonte de verdade). Aqui só
        # decidimos o STATUS da planilha a partir das falhas reais registradas.
        falhas = self.report.por_paciente.get(nome, {}).get("falhas", 0)
        if falhas == 0:
            # Sucesso pleno -> sai da fila. Com falhas/indisponíveis, mantém
            # STATUS=1 para reprocessar depois.
            update_sheet_status(SHEET_URL, row, 0)
        self.report.registrar_paciente_processado()


def build_graph(pipeline: Pipeline):
    g = StateGraph(PipelineState)
    g.add_node("load_queue", pipeline.load_queue)
    g.add_node("open_browser", pipeline.open_browser)
    g.add_node("process", pipeline.process_patient)
    g.add_node("finalize", pipeline.finalize)

    g.add_edge(START, "load_queue")
    g.add_edge("load_queue", "open_browser")
    g.add_conditional_edges("open_browser", pipeline.route, {"process": "process", "finalize": "finalize"})
    g.add_conditional_edges("process", pipeline.route, {"process": "process", "finalize": "finalize"})
    g.add_edge("finalize", END)
    return g.compile()
