"""Testes das proteções de infraestrutura das tools do agente."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.tools import DownloadExameParams, download_exam_report, tools
from app.core.runstate import RUN
from app.reporting.manager import ReportManager


def test_switch_nao_e_exposto_ao_agente():
    assert "switch" in tools.registry.exclude_actions
    assert "switch" not in tools.registry.registry.get_prompt_description()


def test_falha_ao_obter_sessao_cdp_e_registrada():
    class SessaoComFalha:
        async def get_or_create_cdp_session(self, *, focus):
            assert focus is True
            raise RuntimeError("Target not found")

    report = ReportManager()
    RUN.bind(report, "Paciente  de Teste", "123")
    params = DownloadExameParams(
        nome_paciente="Paciente de Teste",
        id_paciente="42",
        nome_exame="US MAMARIA",
        data_exame="01/06/2024",
    )

    result = asyncio.run(
        download_exam_report(params=params, browser_session=SessaoComFalha())
    )

    assert "FALHA DE INFRAESTRUTURA" in result.extracted_content
    assert report.por_paciente["Paciente  de Teste"]["alvos"] == 0
    assert report.por_paciente["Paciente  de Teste"]["falhas"] == 1
    assert report.erros[0]["etapa"] == "cdp_session_unavailable"
