import os
import json
import time
from datetime import datetime

from app.core.config import (
    INFRA_CUSTO_MEMORIA_GB_HORA, INFRA_CUSTO_VCPU_HORA, INFRA_MEMORIA_GB,
    INFRA_VCPU, LLM_PRECO_MILHAO_ENTRADA, LLM_PRECO_MILHAO_SAIDA,
    REPORTS_DIR, TELEMETRY_DIR,
)
from app.integrations.storage import get_storage


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
        self.run_id = self.timestamp.strftime("%d-%m-%Y_%H%M%S")
        self.login_ok = None
        self.exames_eventos = []
        self.llm_tokens_entrada = 0
        self.llm_tokens_saida = 0
        os.makedirs(REPORTS_DIR, exist_ok=True)

    def _slot(self, paciente):
        if paciente not in self.por_paciente:
            self.por_paciente[paciente] = {
                "alvos": 0,
                "baixados": 0,
                "falhas": 0,
                "ignorados": 0,
                "busca_ok": None,
                "download_completo_ok": None,
                "tempo_s": None,
            }
        return self.por_paciente[paciente]

    # [MÉTRICAS] Captura bruta consumida por calcular_metricas.py.
    def registrar_login(self, ok: bool):
        self.login_ok = bool(ok)

    def registrar_busca(self, paciente, encontrado: bool):
        self._slot(paciente)["busca_ok"] = bool(encontrado)

    def registrar_download_completo(self, paciente, ok: bool):
        self._slot(paciente)["download_completo_ok"] = bool(ok)

    def registrar_tempo_paciente(self, paciente, segundos: float):
        self._slot(paciente)["tempo_s"] = round(float(segundos), 2)

    def registrar_exame_visto(self, *, paciente, cpf, data_exame, nome_exame, decisao, metodo=None):
        self.exames_eventos.append({
            "paciente": paciente,
            "cpf": cpf,
            "data_exame": data_exame,
            "nome_exame": nome_exame,
            "decisao": decisao,
            "metodo": metodo,
        })

    def atualizar_decisao_exame(self, *, paciente, data_exame, nome_exame, decisao, metodo=None):
        for ev in reversed(self.exames_eventos):
            if (
                ev["paciente"] == paciente
                and ev["data_exame"] == data_exame
                and ev["nome_exame"] == nome_exame
            ):
                ev["decisao"] = decisao
                if metodo is not None:
                    ev["metodo"] = metodo
                return
        self.registrar_exame_visto(
            paciente=paciente,
            cpf="",
            data_exame=data_exame,
            nome_exame=nome_exame,
            decisao=decisao,
            metodo=metodo,
        )

    def registrar_tokens_llm(self, tokens_entrada: int, tokens_saida: int):
        self.llm_tokens_entrada += int(tokens_entrada or 0)
        self.llm_tokens_saida += int(tokens_saida or 0)

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
        get_storage().upload_result_artifact(path, "reports")
        return path

    def salvar_telemetria(self):
        self._finalizar_timer()
        os.makedirs(TELEMETRY_DIR, exist_ok=True)
        duracao_s = round(self._end - self._start, 3)
        payload = {
            "run_id": self.run_id,
            "inicio": self.timestamp.isoformat(),
            "duracao_s": duracao_s,
            "login_ok": self.login_ok,
            "pacientes_processados": self.pacientes_processados,
            "pacientes_nao_encontrados": self.pacientes_nao_encontrados,
            "total_erros": len(self.erros),
            "erros": self.erros,
            "por_paciente": self.por_paciente,
            "exames": self.exames_eventos,
            # [MÉTRICAS] Custo de infra (Fargate) e de LLM — ver
            # docs/Deploy_AWS_Metricas_Custo_RPA_vs_APA.docx, seções 2-4.
            "infra": {
                "vcpu": INFRA_VCPU,
                "memoria_gb": INFRA_MEMORIA_GB,
                "duracao_s": duracao_s,
                "custo_vcpu_hora": INFRA_CUSTO_VCPU_HORA,
                "custo_memoria_gb_hora": INFRA_CUSTO_MEMORIA_GB_HORA,
            },
        }
        if self.llm_tokens_entrada or self.llm_tokens_saida:
            payload["llm"] = {
                "tokens_entrada": self.llm_tokens_entrada,
                "tokens_saida": self.llm_tokens_saida,
                "preco_por_milhao_entrada": LLM_PRECO_MILHAO_ENTRADA,
                "preco_por_milhao_saida": LLM_PRECO_MILHAO_SAIDA,
            }
        path = os.path.join(TELEMETRY_DIR, f"run_{self.run_id}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(payload, f, indent=4, ensure_ascii=False)
        get_storage().upload_result_artifact(path, "telemetria")
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
        get_storage().upload_result_artifact(path, "reports")
        return path, conteudo
