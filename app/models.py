"""Schemas Pydantic compartilhados entre o agente e a orquestração."""
from typing import List
from pydantic import BaseModel, Field


class Paciente(BaseModel):
    sheet_row: int
    nome: str
    cpf: str = ""


class SaidaAgente(BaseModel):
    """Saída estruturada que o agente deve produzir ao terminar um paciente.
    Substitui o parsing por regex da versão antiga."""
    id_paciente: str = Field(
        default="",
        description="ID numérico do paciente no portal, ou vazio se não encontrado.",
    )
    nao_encontrado: bool = Field(
        default=False,
        description="True se o paciente não foi localizado no portal.",
    )
    exames_baixados: int = Field(
        default=0,
        description="Quantidade de exames baixados e enviados com sucesso.",
    )
    exames_indisponiveis: List[str] = Field(
        default_factory=list,
        description="Nomes dos exames cujo laudo o portal informou indisponível.",
    )


class ResultadoPaciente(BaseModel):
    """Resultado consolidado de um paciente, usado pelo nó de persistência."""
    paciente: Paciente
    saida: SaidaAgente
    erro: str = ""
