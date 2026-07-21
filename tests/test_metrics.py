"""Testes puros do refinador de métricas."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from calcular_metricas import calcular_etapas, classificar_exames


def test_classificar_exames_com_gabarito_e_janela():
    exames = [
        {
            "paciente": "Maria",
            "cpf": "1",
            "data_exame": "10/01/2024",
            "nome_exame": "MAMOGRAFIA",
            "decisao": "baixado",
        },
        {
            "paciente": "Maria",
            "cpf": "1",
            "data_exame": "11/01/2024",
            "nome_exame": "US MAMARIA",
            "decisao": "falha_extracao",
        },
        {
            "paciente": "Maria",
            "cpf": "1",
            "data_exame": "11/01/2026",
            "nome_exame": "MAMOGRAFIA",
            "decisao": "baixado",
        },
    ]
    gabarito = {
        ("MARIA", "10/01/2024", "MAMOGRAFIA"): True,
        ("MARIA", "11/01/2024", "US MAMARIA"): True,
    }

    resumo, detalhe = classificar_exames(exames, gabarito)

    assert resumo["VP"] == 1
    assert resumo["FN"] == 1
    assert resumo["Fora_Janela"] == 1
    assert resumo["Total"] == 2
    assert [d["classificacao"] for d in detalhe] == ["VP", "FN", "FORA_JANELA"]


def test_calcular_etapas_usa_denominadores_corretos():
    run = {
        "login_ok": True,
        "por_paciente": {
            "Maria": {
                "alvos": 2,
                "baixados": 1,
                "busca_ok": True,
                "download_completo_ok": False,
            },
            "Ana": {
                "alvos": 1,
                "baixados": 1,
                "busca_ok": True,
                "download_completo_ok": True,
            },
        },
    }

    etapas = calcular_etapas(run)

    assert etapas["Login_OK"] == 2
    assert etapas["Busca_OK"] == 2
    assert etapas["Download_unitario_OK"] == 2
    assert etapas["Download_completo_OK"] == 1
    assert etapas["Taxa_Download_unitario"] == 2 / 3
