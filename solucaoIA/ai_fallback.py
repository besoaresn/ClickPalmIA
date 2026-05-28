import os
os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["BROWSER_USE_ANONYMOUS_TELEMETRY"] = "false"
import asyncio
import glob
import shutil
import re
import tempfile
from datetime import datetime
from browser_use import Agent, Browser
from browser_use.llm.google import ChatGoogle
from config import USER, PASS, SITE_URL, DOWNLOAD_DIR, GEMINI_MODEL
from api_client import upload_to_api
from data_manager import write_download_history, read_pendentes_ia, remove_pendente_ia, remove_accents, write_erro_agente

def limpar_pastas_temporarias():
    temp_dir = tempfile.gettempdir()
    for d in os.listdir(temp_dir):
        if d.startswith("browser-use-downloads"):
            caminho = os.path.join(temp_dir, d)
            try:
                shutil.rmtree(caminho)
            except:
                pass


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
                            print(f"    [WATCHDOG] Arquivo capturado e protegido na pasta de transição!")
                    except Exception:
                        pass
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

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("    [ERRO] Configure GEMINI_API_KEY no .env para usar o agente.")
        return stats_ia

    try:
        llm = ChatGoogle(model=GEMINI_MODEL, api_key=api_key, temperature=0.7)
    except Exception as e:
        print(f"    [ERRO] Falha ao inicializar LLM Gemini: {e}")
        return stats_ia

    for nome_paciente, exames in pacientes_agrupados.items():
        print(f"\n    [AGENTE] Iniciando lote para {nome_paciente} ({len(exames)} exame(s))")

        exames_texto = "\n".join([f"- Data: {e['data_exame']} | Nome: {e['nome_exame'][:40]}" for e in exames])
        nome_normalizado = remove_accents(nome_paciente).upper()
        browser = None

        try:
            browser = Browser(headless=True)

            task_prompt = f"""
            Download {len(exames)} breast exam(s) for patient: {nome_normalizado}

            ACCESS
            - Site: {SITE_URL}
            - Username: {USER}
            - Password: {PASS}

            EXAMS TO DOWNLOAD ({len(exames)} total)
            {exames_texto}

            STEP BY STEP

            1. LOGIN
               - Access the site
               - Login with the provided credentials

            2. FIND PATIENT (max 3 attempts)
               - Attempt 1: search "{nome_normalizado}" (full name)
               - Attempt 2: search FIRST NAME only
               - If not found: RESPOND with ID_EXTRAIDO: NAO_ENCONTRADO

            3. OPEN PATIENT RECORD
               - Click on the found patient
               - SAVE the numeric patient ID

            4. INJECT ONCE (do this only one time, before any download)
                Inject via evaluate:
                window.print=function(){{return false;}};window.open=async function(url){{if(url.toLowerCase().includes('showreport.htm')){{window.location.href=url;return null;}}let pdfUrl=url;try{{const res=await fetch(url,{{credentials:'include'}});const text=await res.text();const match=text.match(/src=["']([^"']*(?:GetLatestReportStream|ReportService)[^"']*)["']/i);if(match){{let ext=match[1];pdfUrl=ext.startsWith('/')?window.location.origin+ext:ext;}}}}catch(e){{}}fetch(pdfUrl,{{credentials:'include'}}).then(r=>r.blob()).then(b=>{{const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='resgate_ia.pdf';document.body.appendChild(a);a.click()}});return null;}};
                IMPORTANT: If you have already injected this script in a previous step,
                DO NOT inject again. Proceed directly to clicking "Imprimir".

            5. DOWNLOAD EXAMS
               - For EACH exam in the list above:
                 a) Locate the exam by date and name
                 b) Click the exam to open it — wait for page to load
                 c) Click "Imprimir" — this is a separate action after the page loads
                 d) Wait 3 seconds
                 e) PDF will download automatically
                 f) Navigate BACK to the exam list
                 g) Next exam

            6. ERROR HANDLING
               - If you see "não está disponível": report does not exist, continue
               - If page did not change: PDF already downloaded in background, continue
               - If HTML page opened: try to save as PDF manually

            7. FINISH
               - After processing ALL {len(exames)} exams
               - Respond with the format below

            REQUIRED RESPONSE
            ID_EXTRAIDO: [patient number or NAO_ENCONTRADO]
            EXAMES_INDISPONIVEIS: [unavailable exam names or 'Nenhum']
            """

            estado_escuta = {"ativo": True}
            watchdog_task = asyncio.create_task(watchdog_pastas(estado_escuta, staging_dir))

            agent = Agent(task=task_prompt,
                    llm=llm,
                    browser=browser,
                    use_vision=False,
                    vision_detail_level="low",
                    max_actions=50
          )
            history = await agent.run()
            final_result = history.final_result() or ""

            estado_escuta["ativo"] = False
            arquivos_capturados = await watchdog_task

            match_id = re.search(r'ID_EXTRAIDO:\s*(\d+)', final_result, re.IGNORECASE)
            ID_PACIENTE = match_id.group(1).zfill(16) if match_id else "0000000000000000"

            match_indisp = re.search(r'EXAMES_INDISPONIVEIS:\s*(.+)', final_result, re.IGNORECASE)

            if "NAO_ENCONTRADO" in final_result.upper():
                print(f"    [AGENTE] Paciente {nome_paciente} NÃO ENCONTRADO no sistema")
                for e in exames:
                    write_erro_agente({
                        "nome_paciente": nome_paciente,
                        "exam_history_id": e["exam_history_id"],
                        "erro": "PACIENTE_NAO_ENCONTRADO",
                        "data_erro": datetime.now().isoformat(),
                        "data_exame": e.get("data_exame", "N/A"),
                        "nome_exame": e.get("nome_exame", "N/A")
                    })
                stats_ia["falha_ia"] += len(exames)
                continue

            if match_indisp and "nenhum" not in match_indisp.group(1).lower():
                print(f"    [AGENTE] Laudos indisponíveis no servidor: {match_indisp.group(1).strip()}")

            if arquivos_capturados:
                os.makedirs(DOWNLOAD_DIR, exist_ok=True)
                for i, origem in enumerate(arquivos_capturados):
                    exame_ref = exames[i] if i < len(exames) else exames[0]
                    timestamp = datetime.now().strftime("%H%M%S_%f")[:10]
                    nome_arquivo = re.sub(
                        r'[\\/*?:"<>|]', '_',
                        f"0000000000000001_{remove_accents(nome_paciente)}_{ID_PACIENTE}_{exame_ref['cpf']}_{timestamp}_IA.pdf"
                    )
                    destino = os.path.join(DOWNLOAD_DIR, nome_arquivo)
                    try:
                        shutil.move(origem, destino)
                        stats_ia["sucesso_ia"] += 1
                        if upload_to_api(destino, "0000000000000001", ID_PACIENTE):
                            print(f"    [AGENTE] Upload OK ({i+1}): {nome_arquivo}")
                    except Exception as me:
                        print(f"    [AGENTE] Erro ao mover arquivo: {me}")

                for e in exames:
                    remove_pendente_ia(e["exam_history_id"])
                    write_download_history(e["exam_history_id"])
            else:
                if match_indisp and "nenhum" not in match_indisp.group(1).lower():
                    print(f"    [AGENTE] Nenhum arquivo capturado (laudos indisponíveis — justificado).")
                    for e in exames:
                        remove_pendente_ia(e["exam_history_id"])
                        write_download_history(e["exam_history_id"])
                else:
                    print(f"    [AGENTE] Agente concluiu, mas nenhum PDF foi capturado.")
                    stats_ia["falha_ia"] += len(exames)

        except Exception as e:
            print(f"    [AGENTE] Erro no paciente {nome_paciente}: {e}")
            stats_ia["falha_ia"] += len(exames)

            for exame in exames:
                write_erro_agente({
                    "nome_paciente": nome_paciente,
                    "exam_history_id": exame["exam_history_id"],
                    "erro": str(e),
                    "data_erro": datetime.now().isoformat(),
                    "data_exame": exame["data_exame"],
                    "nome_exame": exame["nome_exame"]
                })
        finally:
            limpar_pastas_temporarias()
            if browser:
                try:
                    await browser.close()
                except:
                    pass

    return stats_ia
