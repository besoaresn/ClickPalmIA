"""Custom actions (tools) registradas no agente browser-use.

A única tool de domínio é `download_exam_report`: o agente navega/clica
livremente (ações nativas do browser-use), mas delega a parte que precisa ser
confiável — capturar o PDF do laudo e CONTABILIZAR o resultado — para esta tool
determinística, que reaproveita a lógica do RPA maduro via CDP.
"""
import os
import re
import logging
from datetime import datetime

from pydantic import BaseModel, Field
from browser_use import Tools, ActionResult
from browser_use.browser import BrowserSession

from app.core.config import DOWNLOAD_DIR
from app.core.runstate import RUN
from app.integrations.storage import get_storage
from app.core.config import DEDUP_LOG_RATIO_MIN, DEDUP_SIMILARIDADE
from app.domain.history import remove_accents, read_download_history, write_download_history
from app.domain.filters import (
    check_exam_date,
    is_relevant_exam,
    laudo_tem_ressonancia,
    laudo_tem_titulo_valido,
    texto_indica_skip,
    is_duplicate_report,
)
from app.agent.extraction import extract_pdf_text, extract_report_pdf, read_report_text

tools = Tools()
# O portal abre o laudo em uma nova aba e devolve o foco automaticamente ao
# fechá-la. Trocar de aba manualmente deixa o DownloadsWatchdog do browser-use
# sujeito a uma corrida com a aba que acabou de ser encerrada. Removemos a ação
# do schema exposto ao LLM, em vez de depender apenas da instrução no prompt.
tools.exclude_action("switch")
logger = logging.getLogger(__name__)

_INDISPONIVEL_MARKERS = (
    "nao esta disponivel para exibicao",
    "relatorio nao esta disponivel",
    "nao esta disponivel",
)


class DownloadExameParams(BaseModel):
    nome_paciente: str = Field(description="Nome completo do paciente")
    id_paciente: str = Field(description="ID numérico do paciente no portal (só dígitos)")
    nome_exame: str = Field(description="Nome/descrição do exame, ex.: 'MAMOGRAFIA BILATERAL'")
    data_exame: str = Field(default="", description="Data do exame (DD/MM/AAAA) — IMPORTANTE para diferenciar exames de mesmo nome")
    cpf: str = Field(default="", description="CPF do paciente, se conhecido")


def _normalize_patient_name(nome: str) -> str:
    """Normaliza diferenças de formatação entre planilha e resposta do agente."""
    return " ".join(remove_accents(nome).split()).upper()


def _registrar(metodo: str, **kwargs) -> None:
    """Escreve no ReportManager atual (fonte de verdade das contagens)."""
    rep, pac = RUN.report, RUN.paciente
    if not rep or not pac:
        return
    if metodo == "alvo":
        rep.registrar_alvos(pac, 1)
    elif metodo == "baixado":
        rep.registrar_baixado(pac)
        rep.registrar_metodo(kwargs.get("download_method", "?"))
    elif metodo == "ignorado":
        rep.registrar_ignorado(pac)
    elif metodo == "erro":
        rep.registrar_erro(
            paciente=pac, cpf=RUN.cpf,
            data_exame=kwargs.get("data_exame", ""), nome_exame=kwargs.get("nome_exame", ""),
            motivo=kwargs.get("motivo", ""), etapa=kwargs.get("etapa", "erro"),
        )
    elif metodo == "exame":
        rep.registrar_exame_visto(
            paciente=pac,
            cpf=RUN.cpf,
            data_exame=kwargs.get("data_exame", ""),
            nome_exame=kwargs.get("nome_exame", ""),
            decisao=kwargs.get("decisao", ""),
            metodo=kwargs.get("download_method"),
        )
    elif metodo == "decisao_exame":
        rep.atualizar_decisao_exame(
            paciente=pac,
            data_exame=kwargs.get("data_exame", ""),
            nome_exame=kwargs.get("nome_exame", ""),
            decisao=kwargs.get("decisao", ""),
            metodo=kwargs.get("download_method"),
        )


@tools.action(
    "Captura o laudo (PDF) do exame ATUALMENTE ABERTO na aba/relatório em foco e o "
    "salva em disco. Chame logo após abrir o relatório do exame (após clicar em "
    "'Imprimir' e a aba do relatório estar em foco). A tool decide sozinha se deve "
    "ignorar (carta de procedimento) ou reportar indisponível — apenas leia a "
    "mensagem retornada e siga para o próximo exame. SEMPRE informe data_exame.",
    param_model=DownloadExameParams,
)
async def download_exam_report(params: DownloadExameParams, browser_session: BrowserSession) -> ActionResult:
    # Barreira contra chamadas vazadas de outro run/paciente. O agente é
    # recriado por paciente, mas a tool é global; nunca aceitar silenciosamente
    # um nome vazio ou diferente do paciente atualmente vinculado.
    expected_patient = _normalize_patient_name(RUN.paciente)
    supplied_patient = _normalize_patient_name(params.nome_paciente)
    if expected_patient and supplied_patient != expected_patient:
        _registrar("erro", nome_exame=params.nome_exame, data_exame=params.data_exame,
                   motivo=(f"Tool recebeu paciente diferente do contexto atual: "
                           f"{params.nome_paciente!r}"), etapa="patient_context_mismatch")
        return ActionResult(extracted_content=(
            "FALHA DE CONTEXTO: o paciente informado não é o paciente atual. "
            "Não baixe este laudo; confirme o registro atual e siga."
        ))
    if not re.fullmatch(r"\d+", params.id_paciente or ""):
        _registrar("erro", nome_exame=params.nome_exame, data_exame=params.data_exame,
                   motivo="ID numérico do paciente ausente ou inválido.", etapa="patient_id_invalid")
        return ActionResult(extracted_content=(
            "FALHA DE CONTEXTO: ID numérico do paciente ausente ou inválido. "
            "Confirme o registro atual antes de continuar."
        ))

    id_norm = (re.sub(r"\D", "", params.id_paciente) or "0").zfill(16)
    data_norm = remove_accents(params.data_exame).strip()
    # Chave estável (paciente-id-data-nome). Inclui a data: exames de mesmo nome
    # em datas diferentes são distintos (sem isto o 2º virava JA_BAIXADO).
    hist_id = f"{remove_accents(params.nome_paciente)}-{id_norm}-{data_norm}-{remove_accents(params.nome_exame)}".upper()

    def ignore(decisao: str, texto: str) -> ActionResult:
        RUN.marcar_processado(hist_id)
        _registrar("ignorado")
        _registrar("exame", nome_exame=params.nome_exame, data_exame=params.data_exame, decisao=decisao)
        return ActionResult(extracted_content=texto)

    # Etapa A: a tool também aplica os filtros do card como última barreira
    # determinística caso o agente tenha selecionado um card indevido.
    if "APENAS IMAGENS" in remove_accents(params.nome_exame).upper():
        return ignore("ignorado_apenas_imagens", f"IGNORADO: '{params.nome_exame}' é apenas imagens.")
    if not check_exam_date(params.data_exame):
        return ignore("ignorado_data", f"IGNORADO: '{params.nome_exame}' está fora da janela de 2024-2025.")
    if not is_relevant_exam(params.nome_exame):
        return ignore("ignorado_irrelevante", f"IGNORADO: '{params.nome_exame}' não é um exame-alvo autorizado.")

    # Já TENTADO nesta execução? Não reprocessa. Sem isto, se algo falhar depois
    # de abrir o laudo, o agente pode reabrir o mesmo exame em loop e inflar as
    # contagens. Cada alvo é tentado no máximo 1x por execução, como no RPA maduro.
    if RUN.ja_processou(hist_id):
        return ActionResult(extracted_content=(
            f"JA_PROCESSADO: '{params.nome_exame}' ({params.data_exame}) já foi tentado nesta "
            f"execução. NÃO reabra nem reprocesse — vá para o PRÓXIMO exame ainda não tentado "
            f"ou finalize se já tentou todos."
        ))

    # Já baixado em execução anterior (histórico persistente entre runs).
    if hist_id in read_download_history():
        RUN.marcar_processado(hist_id)
        _registrar(
            "exame",
            nome_exame=params.nome_exame,
            data_exame=params.data_exame,
            decisao="ja_no_historico",
        )
        return ActionResult(extracted_content=(
            f"JA_BAIXADO: '{params.nome_exame}' ({params.data_exame}) já foi baixado antes. "
            f"Pule para o próximo exame."
        ))

    # A aba do laudo pode ter acabado de ser criada/fechada quando o browser-use
    # ainda atualiza o DownloadsWatchdog. Essa falha ocorre antes da extração e,
    # sem este tratamento, desaparecia das métricas e do erros_*.json.
    try:
        cdp_session = await browser_session.get_or_create_cdp_session(focus=True)
    except Exception as exc:
        RUN.marcar_processado(hist_id)
        logger.exception(
            "cdp_session_unavailable paciente=%s exame=%s data=%s",
            params.nome_paciente,
            params.nome_exame,
            params.data_exame,
        )
        _registrar(
            "erro",
            nome_exame=params.nome_exame,
            data_exame=params.data_exame,
            motivo=f"Não foi possível obter a sessão CDP da aba do laudo: {exc}",
            etapa="cdp_session_unavailable",
        )
        _registrar(
            "exame",
            nome_exame=params.nome_exame,
            data_exame=params.data_exame,
            decisao="falha_sessao_cdp",
        )
        return ActionResult(extracted_content=(
            f"FALHA DE INFRAESTRUTURA: não consegui acessar a aba do laudo de "
            f"'{params.nome_exame}'. O erro foi registrado; não tente este exame novamente "
            "nesta execução e siga para o próximo."
        ))

    # Marca ANTES de processar: aconteça o que acontecer (sucesso, indisponível
    # ou falha), este exame não é tentado de novo nesta execução.
    RUN.marcar_processado(hist_id)
    _registrar("alvo")
    _registrar(
        "exame",
        nome_exame=params.nome_exame,
        data_exame=params.data_exame,
        decisao="alvo",
    )

    texto = await read_report_text(cdp_session)
    texto_norm = remove_accents(texto).lower()

    # B5: marcador no corpo exige a segunda checagem pelo título. Isso preserva
    # ecografias/mamografias válidas que também usam a saudação.
    if texto and texto_indica_skip(texto) and not laudo_tem_titulo_valido(texto):
        write_download_history(hist_id)
        _registrar("ignorado")
        _registrar(
            "decisao_exame",
            nome_exame=params.nome_exame,
            data_exame=params.data_exame,
            decisao="ignorado_marcador",
        )
        return ActionResult(extracted_content=(
            f"IGNORADO: '{params.nome_exame}' é carta de procedimento (não diagnóstico). "
            f"Não foi salvo como laudo. Siga para o próximo exame."
        ))

    # B6: cards genéricos podem esconder a modalidade no cabeçalho do laudo.
    if texto and laudo_tem_ressonancia(texto):
        _registrar("ignorado")
        _registrar("decisao_exame", nome_exame=params.nome_exame, data_exame=params.data_exame,
                   decisao="ignorado_ressonancia")
        return ActionResult(extracted_content=(
            f"IGNORADO: o laudo de '{params.nome_exame}' é ressonância. Siga para o próximo."
        ))

    # B7: um laudo combinado pode aparecer em vários cards do mesmo paciente.
    duplicado, ratio = is_duplicate_report(texto, params.data_exame, RUN.relatorios_salvos)
    if duplicado:
        _registrar("ignorado")
        _registrar("decisao_exame", nome_exame=params.nome_exame, data_exame=params.data_exame,
                   decisao="ignorado_duplicado")
        return ActionResult(extracted_content=(
            f"IGNORADO: laudo duplicado de '{params.nome_exame}' (similaridade {ratio:.3f})."
        ))
    if ratio >= DEDUP_LOG_RATIO_MIN:
        logger.info(
            "candidato_dedup paciente=%s exame=%s data=%s similaridade=%.3f limiar=%.2f",
            params.nome_paciente, params.nome_exame, params.data_exame,
            ratio, DEDUP_SIMILARIDADE,
        )

    if texto and any(m in texto_norm for m in _INDISPONIVEL_MARKERS):
        _registrar("erro", nome_exame=params.nome_exame, data_exame=params.data_exame,
                   motivo="Portal informou laudo indisponível para exibição.", etapa="relatorio_indisponivel")
        _registrar(
            "decisao_exame",
            nome_exame=params.nome_exame,
            data_exame=params.data_exame,
            decisao="relatorio_indisponivel",
        )
        return ActionResult(extracted_content=(
            f"INDISPONIVEL: o portal informou que o laudo de '{params.nome_exame}' não está "
            f"disponível para exibição. Registre como indisponível e siga para o próximo."
        ))

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    # Nome de arquivo único: inclui data + timestamp -> não sobrescreve exames de
    # mesmo nome (era a causa de "só 3 PDFs no disco").
    data_tag = re.sub(r"\D", "", params.data_exame) or "semdata"
    stamp = datetime.now().strftime("%H%M%S%f")
    base = re.sub(r'[\\/*?:"<>|]', '_', f"{remove_accents(params.nome_paciente)}-{remove_accents(params.nome_exame)}-{data_tag}")[:100]
    save_path = os.path.join(DOWNLOAD_DIR, f"{base}-{stamp}.pdf")

    metodo = await extract_report_pdf(cdp_session, save_path)
    if not metodo:
        _registrar("erro", nome_exame=params.nome_exame, data_exame=params.data_exame,
                   motivo="Não foi possível extrair o PDF do portal.", etapa="extract_pdf_failed")
        _registrar(
            "decisao_exame",
            nome_exame=params.nome_exame,
            data_exame=params.data_exame,
            decisao="falha_extracao",
        )
        return ActionResult(extracted_content=(
            f"FALHA: não consegui extrair o PDF de '{params.nome_exame}'. Confirme que o "
            f"relatório está aberto/focado e tente novamente, ou siga para o próximo."
        ))

    # O relatório pode estar em um iframe de PDF cujo texto não é acessível ao
    # DOM. Reaplica os filtros de conteúdo e o dedup com a fonte definitiva
    # antes de manter o arquivo.
    texto_pdf = extract_pdf_text(save_path)
    if texto_pdf:
        if texto_indica_skip(texto_pdf) and not laudo_tem_titulo_valido(texto_pdf):
            os.remove(save_path)
            write_download_history(hist_id)
            _registrar("ignorado")
            _registrar(
                "decisao_exame",
                nome_exame=params.nome_exame,
                data_exame=params.data_exame,
                decisao="ignorado_marcador_pdf",
            )
            return ActionResult(extracted_content=(
                f"IGNORADO: o PDF de '{params.nome_exame}' é carta ou procedimento "
                "(não diagnóstico); o arquivo temporário foi removido."
            ))

        if laudo_tem_ressonancia(texto_pdf):
            os.remove(save_path)
            _registrar("ignorado")
            _registrar(
                "decisao_exame",
                nome_exame=params.nome_exame,
                data_exame=params.data_exame,
                decisao="ignorado_ressonancia_pdf",
            )
            return ActionResult(extracted_content=(
                f"IGNORADO: o PDF de '{params.nome_exame}' é ressonância; "
                "o arquivo temporário foi removido."
            ))

        duplicado, ratio = is_duplicate_report(
            texto_pdf, params.data_exame, RUN.relatorios_salvos
        )
        if duplicado:
            os.remove(save_path)
            _registrar("ignorado")
            _registrar(
                "decisao_exame",
                nome_exame=params.nome_exame,
                data_exame=params.data_exame,
                decisao="ignorado_duplicado_pdf",
            )
            return ActionResult(extracted_content=(
                f"IGNORADO: PDF duplicado de '{params.nome_exame}' "
                f"(similaridade {ratio:.3f}); o arquivo temporário foi removido."
            ))

    storage = get_storage()
    s3_uri = None
    # Com RESULTS_S3_URI, o contrato de métricas envia somente telemetria e
    # relatórios. PDFs com dados de paciente permanecem no EFS/disco local.
    if storage.enabled and not storage.results_enabled:
        try:
            s3_uri = storage.upload_artifact(save_path, "downloads")
        except Exception as exc:
            _registrar(
                "erro", nome_exame=params.nome_exame, data_exame=params.data_exame,
                motivo=f"PDF salvo localmente, mas não foi enviado ao S3: {exc}",
                etapa="s3_upload_failed",
            )
            return ActionResult(extracted_content=(
                f"FALHA: o PDF de '{params.nome_exame}' foi extraído, mas o upload para "
                "o armazenamento persistente falhou. Não marque como concluído."
            ))

    write_download_history(hist_id)
    RUN.relatorios_salvos.append({
        "data_exame": params.data_exame,
        "texto": texto_pdf or texto,
    })
    _registrar("baixado", download_method=metodo)
    _registrar(
        "decisao_exame",
        nome_exame=params.nome_exame,
        data_exame=params.data_exame,
        decisao="baixado",
        download_method=metodo,
    )
    destino = s3_uri or save_path
    return ActionResult(extracted_content=(
        f"OK: '{params.nome_exame}' ({params.data_exame}) baixado [{metodo}] em {destino}."
    ))
