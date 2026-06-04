import os
import json
import time
from datetime import datetime

from app.config import REPORTS_DIR


class ReportManager:
    """Acumula estatísticas durante a execução e gera dois arquivos em
    REPORTS_DIR: erros_*.json (falhas para intervenção manual) e
    execucao_*.txt (resumo do lote)."""

    def __init__(self):
        self.timestamp = datetime.now()
        self._start = time.perf_counter()
        self._end = None
        self.erros = []
        self.por_paciente = {}
        self.metodos_download = {}
        self.pacientes_processados = 0
        self.pacientes_nao_encontrados = 0
        os.makedirs(REPORTS_DIR, exist_ok=True)

    def _slot(self, paciente):
        if paciente not in self.por_paciente:
            self.por_paciente[paciente] = {"alvos": 0, "baixados": 0, "falhas": 0, "ignorados": 0}
        return self.por_paciente[paciente]

    def registrar_alvos(self, paciente, n):
        self._slot(paciente)["alvos"] += n

    def registrar_baixado(self, paciente):
        self._slot(paciente)["baixados"] += 1

    def registrar_metodo(self, metodo):
        self.metodos_download[metodo] = self.metodos_download.get(metodo, 0) + 1

    def registrar_ignorado(self, paciente):
        self._slot(paciente)["ignorados"] += 1

    def registrar_erro(self, *, paciente, cpf, data_exame, nome_exame, motivo, etapa):
        self._slot(paciente)["falhas"] += 1
        self.erros.append({
            "timestamp": datetime.now().isoformat(),
            "paciente": paciente,
            "cpf": cpf,
            "data_exame": data_exame,
            "nome_exame": nome_exame,
            "etapa": etapa,
            "motivo": motivo,
        })

    def registrar_paciente_processado(self):
        self.pacientes_processados += 1

    def registrar_paciente_nao_encontrado(self, paciente):
        self.pacientes_nao_encontrados += 1
        self._slot(paciente)

    def _finalizar_timer(self):
        if self._end is None:
            self._end = time.perf_counter()

    def _tempo_formatado(self):
        self._finalizar_timer()
        total = int(self._end - self._start)
        horas, resto = divmod(total, 3600)
        minutos, segundos = divmod(resto, 60)
        if horas:
            return f"{horas}h {minutos}min {segundos}s"
        if minutos:
            return f"{minutos}min {segundos}s"
        return f"{segundos}s"

    def salvar_erros(self):
        path = os.path.join(REPORTS_DIR, f"erros_{self.timestamp:%d-%m-%Y_%H%M%S}.json")
        payload = {
            "execucao": self.timestamp.strftime("%d-%m-%Y %H:%M:%S"),
            "total_erros": len(self.erros),
            "erros": self.erros,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
        return path

    def gerar_relatorio_final(self):
        self._finalizar_timer()
        total_baixados = sum(s["baixados"] for s in self.por_paciente.values())
        total_falhas = sum(s["falhas"] for s in self.por_paciente.values())
        total_ignorados = sum(s.get("ignorados", 0) for s in self.por_paciente.values())

        linhas = []
        linhas.append("=" * 60)
        linhas.append(f"RELATÓRIO FINAL DE EXECUÇÃO — {self.timestamp:%d-%m-%Y %H:%M:%S}")
        linhas.append("=" * 60)
        linhas.append(f"Tempo total: {self._tempo_formatado()}")
        linhas.append("")
        linhas.append(f"Pacientes processados: {self.pacientes_processados}")
        linhas.append(f"Pacientes não encontrados no portal: {self.pacientes_nao_encontrados}")
        linhas.append("")
        linhas.append(f"Total de exames baixados com sucesso: {total_baixados}")
        linhas.append(f"Total de exames ignorados (localização pré-operatória): {total_ignorados}")
        linhas.append(f"Total de exames com falha: {total_falhas} (ver erros_*.json para detalhes)")
        if self.metodos_download:
            metodos = ", ".join(f"{m}: {q}" for m, q in sorted(self.metodos_download.items()))
            linhas.append(f"Métodos de download usados: {metodos}")
        linhas.append("")
        linhas.append("Quebra por paciente:")
        if not self.por_paciente:
            linhas.append("  (nenhum paciente processado)")
        else:
            for nome, s in self.por_paciente.items():
                linhas.append(
                    f"  {nome} — alvos: {s['alvos']} | baixados: {s['baixados']} | "
                    f"ignorados: {s.get('ignorados', 0)} | falhas: {s['falhas']}"
                )
        linhas.append("=" * 60)

        path = os.path.join(REPORTS_DIR, f"execucao_{self.timestamp:%d-%m-%Y_%H%M%S}.txt")
        conteudo = "\n".join(linhas) + "\n"
        with open(path, 'w', encoding='utf-8') as f:
            f.write(conteudo)
        return path, conteudo
