"""Testes puros dos filtros de exame (sem browser)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.domain.filters import (
    check_exam_date,
    is_duplicate_report,
    is_relevant_exam,
    laudo_tem_ressonancia,
    laudo_tem_titulo_valido,
    texto_indica_skip,
)


def test_check_exam_date_corte_2024():
    assert check_exam_date("15/03/2024 10:30") is True
    assert check_exam_date("01/01/2025") is True
    assert check_exam_date("01/01/2026") is False
    assert check_exam_date("31/12/2023 09:00") is False
    assert check_exam_date("data oculta") is False
    assert check_exam_date("") is False


def test_is_relevant_exam_keywords_mama():
    assert is_relevant_exam("MAMOGRAFIA BILATERAL") is True
    assert is_relevant_exam("US MAMARIA") is True
    assert is_relevant_exam("Ecografia de mama direita") is True
    assert is_relevant_exam("RAIO-X DE TORAX") is False
    assert is_relevant_exam("TOMOGRAFIA DE CRANIO") is False


def test_is_relevant_exam_exclui_pre_cirurgica():
    # Mesmo contendo "MAMO", localização pré-cirúrgica é excluída pelo nome.
    assert is_relevant_exam("MAMOGRAFIA LOCALIZACAO PRE-CIRURGICA") is False
    assert is_relevant_exam("MAMA PRE OPERATORIA") is False


def test_is_relevant_exam_aplica_denylist_antes_da_palavra_alvo():
    assert is_relevant_exam("MR BREAST RM DE MAMA") is False
    assert is_relevant_exam("BIOPSIA DE MAMA") is False
    assert is_relevant_exam("TOMOGRAFIA DE MAMA") is False
    assert is_relevant_exam("TERMOGRAFIA DE MAMA") is True


def test_laudo_com_saudacao_mantem_titulo_diagnostico():
    texto = "ECOGRAFIA DE MAMA BILATERAL\nPaciente...\nPREZADO(A) COLEGA"
    assert texto_indica_skip(texto) is True
    assert laudo_tem_titulo_valido(texto) is True

    biopsia = "BIOPSIA DE MAMA\nPREZADO(A) COLEGA"
    assert laudo_tem_titulo_valido(biopsia) is False


def test_laudo_detecta_rm_somente_no_cabecalho():
    assert laudo_tem_ressonancia("RM DE MAMA\nINFORMACAO CLINICA: nódulo") is True
    assert laudo_tem_ressonancia("ECOGRAFIA\nINFORMACAO CLINICA: RM DE MAMA") is False


def test_deduplica_laudo_dentro_da_janela():
    anterior = [{"data_exame": "10/01/2025", "texto": "Laudo idêntico da mama"}]
    assert is_duplicate_report("Laudo identico da mama", "12/01/2025", anterior)[0] is True
    assert is_duplicate_report("Laudo identico da mama", "20/01/2025", anterior)[0] is False


def test_texto_indica_skip_carta_procedimento():
    assert texto_indica_skip("Prezado(a) Colega, encaminho a paciente...") is True
    assert texto_indica_skip("LOCALIZACAO PRE-OPERATORIA da lesao") is True
    assert texto_indica_skip("Mamografia: BI-RADS 2. Achados benignos.") is False


def test_procedimentos_detectados_no_texto_do_pdf_nao_tem_titulo_valido():
    localizacao = """LOCALIZAÇÃO PRÉ-OPERATÓRIA GUIADA POR MAMOGRAFIA
    Prezado(a) Colega, localização pré-operatória de lesão não palpável."""
    biopsia = """BIÓPSIA MAMÁRIA GUIADA POR ECOGRAFIA
    Prezado(a) colega, resultado de exame anatomopatológico."""

    for texto in (localizacao, biopsia):
        assert texto_indica_skip(texto) is True
        assert laudo_tem_titulo_valido(texto) is False
