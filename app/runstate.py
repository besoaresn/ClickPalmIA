"""Estado compartilhado entre a orquestração (graph) e a tool do agente.

As tools são registradas a nível de módulo no browser-use, então precisam de um
canal para saber em qual paciente/relatório escrever. A orquestração seta isto
antes de cada run do agente. Assim as CONTAGENS vêm da tool (fonte de verdade),
não do que o LLM relata na saída estruturada (que pode errar)."""


class _RunState:
    def __init__(self):
        self.report = None      # ReportManager atual
        self.paciente = ""      # nome do paciente atual
        self.cpf = ""

    def bind(self, report, paciente: str, cpf: str = "") -> None:
        self.report = report
        self.paciente = paciente
        self.cpf = cpf


RUN = _RunState()
