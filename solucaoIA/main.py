import os
import asyncio
import time
from core import read_patients_from_gsheets, update_sheet_status, process_patient_exams
from ai_fallback import run_ai_batch_rescue
from data_manager import read_pendentes_ia, seed_pendentes_ia_from_patients
from config import DOWNLOAD_DIR, HISTORY_FILE, SHEET_URL, AGENT_ONLY_MODE

def run_automation():
    start_time = time.time()
    
    metricas = {
        "total_pacientes_planilha": 0,
        "pacientes_nao_encontrados_portal": 0,
        "total_exames_alvo_necessarios": 0,
        "sucesso_download_rpa": 0,
        "sucesso_download_agente_ia": 0,
        "falha_absoluta_exames": 0
    }

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f: f.write("[]")

    print(f"\n[INICIO] 🚀 Iniciando pipeline {'Agente-Only' if AGENT_ONLY_MODE else 'Híbrido (RPA + Resgate IA)'}")
    result_data = read_patients_from_gsheets(SHEET_URL)
    
    if "error" in result_data:
        print(f"[ERRO] Falha ao ler a planilha: {result_data['error']}")
        return

    pacientes = result_data.get("pacientes", [])
    total_linhas = result_data.get("total_linhas", 0)

    if not pacientes:
        if AGENT_ONLY_MODE and total_linhas > 0:
            print("[AVISO] Nenhuma linha com STATUS=1, mas o modo agente-only vai usar os registros da planilha.")
            pacientes = result_data.get("pacientes", [])
        else:
            print("[AVISO] Fila vazia no Google Sheets (Nenhum paciente com STATUS 1).")
            return

    metricas["total_pacientes_planilha"] = len(pacientes)
    print(f"[OK] {len(pacientes)} paciente(s) para processar.\n")
    
    # 1. FASE RPA (
    if AGENT_ONLY_MODE:
        qtd_seed = seed_pendentes_ia_from_patients(pacientes)
        metricas["total_exames_alvo_necessarios"] = qtd_seed
        print(f"[AGENTE-ONLY] Fila da IA preparada com {qtd_seed} paciente(s) da planilha.")
    else:
        for p_info in pacientes:
            nome, cpf, row_idx = p_info["nome"], p_info["cpf"], p_info["sheet_row"]
            print("=" * 60)

            res_rpa = process_patient_exams(nome, cpf)

            if res_rpa["status"] == "not_found":
                metricas["pacientes_nao_encontrados_portal"] += 1
                print(f"[AVISO] {nome} não possui cadastro no portal do laboratório.")

            metricas["total_exames_alvo_necessarios"] += res_rpa["alvos_encontrados"]
            metricas["sucesso_download_rpa"] += res_rpa["sucesso_rpa"]

            if res_rpa["status"] == "success":
                print(f"[FINALIZADO] RPA concluiu todos os exames de {nome}. Status -> 0")
                update_sheet_status(SHEET_URL, row_idx, 0)
            elif res_rpa["status"] == "partial_fail":
                print(f"[PENDENTE] O RPA enviou {res_rpa['falha_rpa_enviado_ia']} exames para a fila da IA.")

    # 2. FASE IA (Resgate)
    print("\n" + "="*60)
    if AGENT_ONLY_MODE:
        print("[SISTEMA] Iniciando Agente de IA em modo exclusivo...")
    else:
        print("[SISTEMA] Iniciando Agente de IA para limpar a fila de erros...")
    
    res_ia = asyncio.run(run_ai_batch_rescue())

    if res_ia:
        metricas["sucesso_download_agente_ia"] += res_ia.get("sucesso_ia", 0)
        metricas["falha_absoluta_exames"] += res_ia.get("falha_ia", 0)

    # 3. VERIFICAÇÃO FINAL E RELATÓRIO
    print("\n[SISTEMA] Verificação final de pendências para atualizar o Sheets...")
    fila_pos_ia = read_pendentes_ia()
    
    for p_info in pacientes:
        nome_paciente, row_idx = p_info["nome"], p_info["sheet_row"]
        ainda_tem_erro = any(item.get("nome") == nome_paciente for item in fila_pos_ia)
        
        if not ainda_tem_erro:
            update_sheet_status(SHEET_URL, row_idx, 0)

    tempo_total_segundos = time.time() - start_time
    minutos = int(tempo_total_segundos // 60)
    segundos = int(tempo_total_segundos % 60)
    
    total_sucessos = metricas['sucesso_download_rpa'] + metricas['sucesso_download_agente_ia']
    if metricas['total_exames_alvo_necessarios'] > 0:
        taxa = (total_sucessos / metricas['total_exames_alvo_necessarios']) * 100
    else:
        taxa = 0.0

    relatorio = f"""
============================================================
RELATÓRIO FINAL DE EXECUÇÃO (MÉTRICAS QUANTITATIVAS)
============================================================
TEMPO DE EXECUÇÃO: {minutos} minutos e {segundos} segundos.

1. PACIENTES:
   - Processados na Planilha: {metricas['total_pacientes_planilha']}
   - Não encontrados no Portal: {metricas['pacientes_nao_encontrados_portal']}

2. VOLUME DE EXAMES (ALVOS A PARTIR DE 2024):
   - Total de exames que atendiam aos critérios: {metricas['total_exames_alvo_necessarios']}

3. PERFORMANCE DE DOWNLOAD:
   - 🟢 Baixados pelo RPA (Hardcoded): {metricas['sucesso_download_rpa']}
   - 🟡 Baixados pelo Agente IA (Resgate): {metricas['sucesso_download_agente_ia']}
   - 🔴 Falha Absoluta (Erro no RPA e IA): {metricas['falha_absoluta_exames']}

Taxa de Sucesso Total: {taxa:.2f}%
============================================================
"""
    print(relatorio)
    
    with open("relatorio_execucao.txt", "w", encoding="utf-8") as f:
        f.write(relatorio)

if __name__ == "__main__":
    run_automation()