"""Custom actions (tools) registradas no agente browser-use.

A única tool de domínio é `download_exam_report`: o agente navega/clica
livremente (ações nativas do browser-use), mas delega a parte que precisa ser
confiável — capturar o PDF do laudo e enviá-lo à API — para esta tool
determinística, que reaproveita a lógica do RPA maduro via CDP.
"""
import os
import re

from pydantic import BaseModel, Field
from browser_use import Tools, ActionResult
from browser_use.browser import BrowserSession

from app.config import DOWNLOAD_DIR
from app.history import remove_accents, read_download_history, write_download_history
from app.api_client import upload_to_api
from app.extraction import extract_report_pdf, read_report_text
from app.filters import texto_indica_skip

tools = Tools()

# A API ClickPalm hoje usa um id de plataforma fixo (ver api_client / RPA maduro).
ID_PLATAFORMA = "0000000000000001"

_INDISPONIVEL_MARKERS = (
    "nao esta disponivel para exibicao",
    "relatorio nao esta disponivel",
    "nao esta disponivel",
)


class DownloadExameParams(BaseModel):
    nome_paciente: str = Field(description="Nome completo do paciente")
    id_paciente: str = Field(description="ID numérico do paciente no portal (só dígitos)")
    nome_exame: str = Field(description="Nome/descrição do exame, ex.: 'MAMOGRAFIA BILATERAL'")
    data_exame: str = Field(default="", description="Data do exame (DD/MM/AAAA), se conhecida")
    cpf: str = Field(default="", description="CPF do paciente, se conhecido")


@tools.action(
    "Captura o laudo (PDF) do exame ATUALMENTE ABERTO na aba/relatório em foco e o "
    "envia para a API ClickPalm. Chame logo após abrir o relatório do exame (após "
    "clicar em 'Imprimir' e a aba do relatório estar em foco). A tool decide sozinha "
    "se deve ignorar (carta de procedimento) ou reportar indisponível — apenas leia "
    "a mensagem retornada e siga para o próximo exame.",
    param_model=DownloadExameParams,
)
async def download_exam_report(params: DownloadExameParams, browser_session: BrowserSession) -> ActionResult:
    cdp_session = await browser_session.get_or_create_cdp_session(focus=True)

    id_norm = (re.sub(r"\D", "", params.id_paciente) or "0").zfill(16)
    hist_id = f"{remove_accents(params.nome_paciente)}-{id_norm}-{remove_accents(params.nome_exame)}".upper()

    # Anti-duplicação entre execuções.
    if hist_id in read_download_history():
        return ActionResult(extracted_content=(
            f"JA_BAIXADO: '{params.nome_exame}' já foi enviado em execução anterior. "
            f"Pule para o próximo exame."
        ))

    texto = await read_report_text(cdp_session)
    texto_norm = remove_accents(texto).lower()

    # Carta de procedimento (localização pré-op, "PREZADO(A) COLEGA") -> não é
    # exame diagnóstico, não enviar.
    if texto and texto_indica_skip(texto):
        write_download_history(hist_id)
        return ActionResult(extracted_content=(
            f"IGNORADO: '{params.nome_exame}' é carta de procedimento (não diagnóstico). "
            f"Não foi enviado. Siga para o próximo exame."
        ))

    if texto and any(m in texto_norm for m in _INDISPONIVEL_MARKERS):
        return ActionResult(extracted_content=(
            f"INDISPONIVEL: o portal informou que o laudo de '{params.nome_exame}' não está "
            f"disponível para exibição. Registre como indisponível e siga para o próximo."
        ))

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    safe = re.sub(r'[\\/*?:"<>|]', '_', f"{remove_accents(params.nome_paciente)}-{remove_accents(params.nome_exame)}")[:120]
    save_path = os.path.join(DOWNLOAD_DIR, f"{safe}.pdf")

    metodo = await extract_report_pdf(cdp_session, save_path)
    if not metodo:
        return ActionResult(extracted_content=(
            f"FALHA: não consegui extrair o PDF de '{params.nome_exame}'. Confirme que o "
            f"relatório está aberto/focado e tente novamente, ou siga para o próximo."
        ))

    ok = upload_to_api(save_path, ID_PLATAFORMA, id_norm, params.nome_exame)
    if ok:
        write_download_history(hist_id)
        return ActionResult(extracted_content=(
            f"OK: '{params.nome_exame}' baixado [{metodo}] e enviado à API com sucesso."
        ))
    return ActionResult(extracted_content=(
        f"UPLOAD_FALHOU: PDF de '{params.nome_exame}' salvo localmente (método {metodo}), "
        f"mas o envio à API falhou. Considere como falha e siga."
    ))
