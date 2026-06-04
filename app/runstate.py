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
        self._processados: set[str] = set()  # hist_ids já tentados nesta execução do paciente

    def bind(self, report, paciente: str, cpf: str = "") -> None:
        self.report = report
        self.paciente = paciente
        self.cpf = cpf
        self._processados = set()   # zera a memória de tentativas a cada paciente

    def marcar_processado(self, hist_id: str) -> None:
        """Registra que um exame já foi tentado nesta execução (mesmo se falhou)."""
        self._processados.add(hist_id)

    def ja_processou(self, hist_id: str) -> bool:
        return hist_id in self._processados


RUN = _RunState()
