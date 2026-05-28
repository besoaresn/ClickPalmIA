import os
import asyncio
import time

# FIX: Removidos 'process_patient_exams' e 'update_sheet_status' (não usados no modo agente-only).
# FIX: Removida importação de 'BROWSER_USE_API_KEY' que não existia em config.py.
from core import read_patients_from_gsheets
from ai_fallback import run_ai_batch_rescue
from data_manager import seed_pendentes_ia_from_patients
from config import DOWNLOAD_DIR, HISTORY_FILE, SHEET_URL

def run_automation():
    start_time = time.time()

    metricas = {
        "total_pacientes_planilha": 0,
        "total_exames_alvo_necessarios": 0,
        "sucesso_download_agente_ia": 0,
        "falha_absoluta_exames": 0
    }

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            f.write("[]")

    print("\n[INICIO] 🚀 Iniciando pipeline Agente-Only")

    result_data = read_patients_from_gsheets(SHEET_URL)

    if "error" in result_data:
        print(f"[ERRO] Falha ao ler a planilha: {result_data['error']}")
        return

    pacientes = result_data.get("pacientes", [])

    if not pacientes:
        print("[AVISO] Nenhum paciente encontrado na planilha.")
        return

    metricas["total_pacientes_planilha"] = len(pacientes)
    print(f"[OK] {len(pacientes)} paciente(s) para processar.\n")

    # FASE 1: Prepara a fila da IA a partir dos pacientes da planilha
    qtd_seed = seed_pendentes_ia_from_patients(pacientes)
    metricas["total_exames_alvo_necessarios"] = qtd_seed
    print(f"[AGENTE] Fila preparada com {qtd_seed} paciente(s).")

    # FASE 2: Agente de IA processa a fila
    print("\n" + "=" * 60)
    print("[SISTEMA] Iniciando Agente de IA...")

    # FIX: run_ai_batch_rescue() não aceita parâmetros. Chamada corrigida.
    res_ia = asyncio.run(run_ai_batch_rescue())

    if res_ia:
        metricas["sucesso_download_agente_ia"] += res_ia.get("sucesso_ia", 0)
        metricas["falha_absoluta_exames"] += res_ia.get("falha_ia", 0)

    # RELATÓRIO FINAL
    tempo_total = time.time() - start_time
    minutos = int(tempo_total // 60)
    segundos = int(tempo_total % 60)

    total_sucessos = metricas["sucesso_download_agente_ia"]
    taxa = (total_sucessos / metricas["total_exames_alvo_necessarios"] * 100) if metricas["total_exames_alvo_necessarios"] > 0 else 0.0

    relatorio = f"""
============================================================
RELATÓRIO FINAL DE EXECUÇÃO
============================================================
TEMPO DE EXECUÇÃO: {minutos} minutos e {segundos} segundos.

1. PACIENTES:
   - Processados na Planilha: {metricas['total_pacientes_planilha']}

2. VOLUME DE EXAMES (ALVOS A PARTIR DE 2024):
   - Total de pacientes enviados para o Agente: {metricas['total_exames_alvo_necessarios']}

3. PERFORMANCE DE DOWNLOAD:
   - 🟢 Baixados pelo Agente IA: {metricas['sucesso_download_agente_ia']}
   - 🔴 Falha Absoluta (Erro no Agente): {metricas['falha_absoluta_exames']}

Taxa de Sucesso Total: {taxa:.2f}%
============================================================
"""
    print(relatorio)

    with open("relatorio_execucao.txt", "w", encoding="utf-8") as f:
        f.write(relatorio)


if __name__ == "__main__":
    run_automation()
