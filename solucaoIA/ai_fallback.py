import os
# Desabilitar telemetria do Browser Use (não usar dados para treinamento)
os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["BROWSER_USE_ANONYMOUS_TELEMETRY"] = "false"
import asyncio
import glob
import shutil
import re
import tempfile
import unicodedata
from datetime import datetime
from browser_use import Agent, Browser
from browser_use.llm.google import ChatGoogle

from config import USER, PASS, SITE_URL, DOWNLOAD_DIR
from api_client import upload_to_api
from data_manager import write_download_history, read_pendentes_ia, remove_pendente_ia

try: 
    from browser_use import BrowserConfig
except ImportError: 
    BrowserConfig = None

def remove_accents(input_str):
    if not input_str: return ""
    nfkd_form = unicodedata.normalize('NFKD', str(input_str))
    return "".join([c for c in nfkd_form if not unicodedata.combining(c)])

def limpar_pastas_temporarias():
    temp_dir = tempfile.gettempdir()
    for d in os.listdir(temp_dir):
        if d.startswith("browser-use-downloads"):
            caminho = os.path.join(temp_dir, d)
            try: shutil.rmtree(caminho)
            except: pass

async def watchdog_pastas(estado_escuta, staging_dir):
    temp_dir = tempfile.gettempdir()
    arquivos_protegidos = []
    
    while estado_escuta["ativo"]:
        pastas = [os.path.join(temp_dir, d) for d in os.listdir(temp_dir) if d.startswith("browser-use-downloads")]
        for pasta in pastas:
            if os.path.isdir(pasta):
                pdfs = glob.glob(os.path.join(pasta, "*.pdf"))
                for pdf in pdfs:
                    try:
                        if os.path.getsize(pdf) > 0:
                            novo_nome = f"resgate_{datetime.now().strftime('%H%M%S_%f')}.pdf"
                            destino_staging = os.path.join(staging_dir, novo_nome)
                            shutil.move(pdf, destino_staging)
                            arquivos_protegidos.append(destino_staging)
                            print(f"    [WATCHDOG] 🐕 Arquivo capturado no ar e protegido na pasta de transição!")
                    except Exception: pass
        await asyncio.sleep(0.5)
        
    return arquivos_protegidos

async def run_ai_batch_rescue() -> dict:
    stats_ia = {"sucesso_ia": 0, "falha_ia": 0}
    
    pendentes = read_pendentes_ia()
    if not pendentes:
        print("    [IA] Fila de pendentes vazia.")
        return stats_ia
    
    limpar_pastas_temporarias()
    staging_dir = os.path.join(tempfile.gettempdir(), "resgate_seguro_ia")
    os.makedirs(staging_dir, exist_ok=True)
    
    pacientes_agrupados = {}
    for p in pendentes:
        nome = p["nome"]
        if nome not in pacientes_agrupados:
            pacientes_agrupados[nome] = []
        pacientes_agrupados[nome].append(p)

    # Aceita os dois nomes de variável para evitar quebra por documentação antiga.
    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("    [ERRO] Configure GEMINI_API_KEY no ambiente para usar o resgate IA.")
        return stats_ia

    try:
        llm = ChatGoogle(
            model="gemini-2.5-pro",
            api_key=api_key,
            temperature=0.7
        )
    except Exception as e:
        print(f"    [ERRO] Falha ao inicializar LLM: {e}")
        return stats_ia

    for nome_paciente, exames in pacientes_agrupados.items():
        print(f"\n    [IA RESGATE] 🤖 Iniciando resgate LOTE ÚNICO para {nome_paciente} ({len(exames)} exames)")
        
        exames_texto = "\n".join([f"- Data: {e['data_exame']} | Nome: {e['nome_exame'][:40]}" for e in exames])
        browser = None
        
        try:
            conf = BrowserConfig(cdp_url="http://localhost:9222") if BrowserConfig else None
            browser = Browser(config=conf) if conf else Browser()

            # prompt do agente
            task_prompt = f"""
            OBJETIVO RESTRITO: Você é um robô de extração avançado. Missão: baixar TODOS OS {len(exames)} EXAMES.
            
            1. Acesse {SITE_URL} com login '{USER}' / '{PASS}'.
            2. Busque o paciente '{nome_paciente}' e abra o prontuário.
            3. Memorize o ID do paciente.
            
            ALVOS DO DOWNLOAD:
            {exames_texto}
            
            FLUXO DE DOWNLOAD SILENCIOSO (PARA CADA EXAME):
            - 1º PASSO: Encontre o exame correto na lista.
            - 2º PASSO (INJEÇÃO ANTI-JANELA): ANTES de clicar em 'Imprimir', use a ação 'evaluate' para injetar este código que rouba o ticket e ANULA a caixa de diálogo do Windows:
              window.print = function(){{ return false; }}; window.open = async function(url) {{ if (url.toLowerCase().includes('showreport.htm')) {{ window.location.href = url; return null; }} let pdfUrl = url; try {{ const res = await fetch(url); const text = await res.text(); const match = text.match(/src=["']([^"']*(?:GetLatestReportStream|ReportService)[^"']*)["']/i); if (match) {{ let ext = match[1]; pdfUrl = ext.startsWith('/') ? window.location.origin + ext : ext; }} }} catch(e) {{}} fetch(pdfUrl).then(r => r.blob()).then(b => {{ const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'resgate_ia.pdf'; document.body.appendChild(a); a.click(); }}); return null; }};
            - 3º PASSO: Agora, CLIQUE no botão 'Imprimir' do exame. 
            - 4º PASSO: Aguarde 4 segundos. 
              -> Se a tela mostrar "não está disponível para exibição", o laudo não existe no hospital. Ignore o download, anote o nome do exame e FECHE a aba (se alguma abriu).
              -> Se a página NÃO MUDOU, o arquivo baixou invisível. Prossiga para o próximo exame.
              -> Se a página MUDOU para um relatório de texto (HTML), use a sua ação nativa de gerar PDF (save_as_pdf), aguarde e feche a aba.
            - 5º PASSO: Repita para o PRÓXIMO exame da lista.
            
            REGRAS DE PARADA:
            - É PROIBIDO clicar em botões de Salvar dentro de visualizadores de PDF.
            - ASSIM QUE PROCESSAR TODOS OS {len(exames)} EXAMES, use a ação 'Done/Concluir'.
            
            MENSAGEM FINAL OBRIGATÓRIA (Siga exatamente este formato):
            - ID_EXTRAIDO: [numero]
            - EXAMES_INDISPONIVEIS: [liste os nomes dos exames que exibiram erro de 'não disponível', ou escreva 'Nenhum']
            """
            
            estado_escuta = {"ativo": True}
            watchdog_task = asyncio.create_task(watchdog_pastas(estado_escuta, staging_dir))
            
            # ChatGoogle é o adaptador nativo compatível com o Agent do browser-use.
            agent = Agent(task=task_prompt, llm=llm, browser=browser)
            history = await agent.run()
            final_result = history.final_result() or ""

            estado_escuta["ativo"] = False
            arquivos_capturados = await watchdog_task

            match_id = re.search(r'ID_EXTRAIDO:\s*(\d+)', final_result, re.IGNORECASE)
            ID_PACIENTE = match_id.group(1).zfill(16) if match_id else "0000000000000000"

            # Imprime se a IA reportar exames quebrados
            match_indisp = re.search(r'EXAMES_INDISPONIVEIS:\s*(.+)', final_result, re.IGNORECASE)
            if match_indisp and "nenhum" not in match_indisp.group(1).lower():
                print(f"    [IA] O Agente detectou laudos indisponíveis no servidor: {match_indisp.group(1).strip()}")

            if arquivos_capturados:
                os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                for i, origem in enumerate(arquivos_capturados):
                    exame_ref = exames[i] if i < len(exames) else exames[0]
                    
                    timestamp = datetime.now().strftime("%H%M%S_%f")[:10]
                    nome_arquivo = re.sub(r'[\\/*?:"<>|]', '_', f"0000000000000001_{remove_accents(nome_paciente)}_{ID_PACIENTE}_{exame_ref['cpf']}_{timestamp}_IA.pdf")
                    destino = os.path.join(DOWNLOAD_DIR, nome_arquivo)
                    
                    try:
                        shutil.move(origem, destino)
                        stats_ia["sucesso_ia"] += 1
                         # comentar as duas linhas abaixo para evitar upload real durante os testes
                        if upload_to_api(destino, "0000000000000001", ID_PACIENTE):
                          print(f"    [IA] Sucesso no resgate ({i+1}): {nome_arquivo}")
                        
                        #print(f"    [IA] Sucesso no resgate ({i+1}): {nome_arquivo} (Upload API desativado)")
                    except Exception as me:
                        print(f"    [IA] Erro ao mover: {me}")

                # Limpa a fila de pendentes para não ficar num loop infinito
                for e in exames:
                    remove_pendente_ia(e["exam_history_id"])
                    write_download_history(e["exam_history_id"])
            else:
                # Se não baixou nada, mas foi porque o exame estava indisponível, a IA não "falhou".
                if match_indisp and "nenhum" not in match_indisp.group(1).lower():
                    print(f"    [IA] Nenhum arquivo capturado, mas justificado por laudos indisponíveis.")
                    for e in exames:
                        remove_pendente_ia(e["exam_history_id"])
                        write_download_history(e["exam_history_id"])
                else:
                    print(f"    [IA] A IA terminou, mas nenhum PDF foi capturado no ar.")
                    stats_ia["falha_ia"] += len(exames)

        except Exception as e:
            print(f"    [IA] Erro no paciente {nome_paciente}: {e}")
            stats_ia["falha_ia"] += len(exames)
        finally:
            limpar_pastas_temporarias()
            if browser:
                try: await browser.close()
                except: pass

    return stats_ia