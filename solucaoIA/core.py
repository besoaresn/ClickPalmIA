import os
import time
import re
import shutil
import unicodedata
import requests
import pandas as pd
from urllib.parse import urlparse, parse_qs
import gspread
from playwright.sync_api import sync_playwright

from api_client import upload_to_api
from data_manager import (
    remove_accents, normalize_name, read_download_history, 
    write_download_history, write_pendente_ia
)
from config import (
    USER_FIELD_SELECTOR, PASS_FIELD_SELECTOR, LOGIN_BUTTON_SELECTOR, 
    SITE_URL, USER, PASS, DOWNLOAD_DIR, SEARCH_BAR_SELECTOR,
    HEADLESS_MODE, IS_DOCKER, AGENT_ONLY_MODE, CREDENTIALS_FILE
)

def check_exam_date(date_str):
    try: 
        ano = int(date_str.split(" ")[0].split("/")[2])
        return ano >= 2024  # Apenas exames de 2024 em diante
    except: 
        return False 

def is_relevant_exam(exam_text: str) -> bool:
    target_keywords = ["MAMA", "MAMO", "MAMMO", "MMG", "BREAST", "AXILA", "IMPLANT", "NODULO", "ECOGRAFIA", "ULTRASSONOGRAFIA"]
    return any(keyword in remove_accents(exam_text).upper() for keyword in target_keywords)

def download_pdf_from_url(url: str, cookies: list, save_path: str) -> bool:
    try:
        session = requests.Session()
        for cookie in cookies: session.cookies.set(cookie['name'], cookie['value'], domain=cookie.get('domain', ''))
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/pdf,*/*'}
        response = session.get(url, headers=headers, timeout=60, stream=True)
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192): f.write(chunk)
            return True
        return False
    except: return False

def extract_pdf_from_blob_url(page, save_path: str) -> bool:
    try:
        pdf_base64 = page.evaluate("""
            async () => {
                const iframe = document.querySelector('iframe');
                const target = (window.location.href.startsWith('blob:')) ? window.location.href : (iframe && iframe.src.includes('blob:') ? iframe.src : null);
                if (target) {
                    const response = await fetch(target);
                    const blob = await response.blob();
                    return new Promise((resolve) => {
                        const reader = new FileReader();
                        reader.onloadend = () => resolve(reader.result.split(',')[1]);
                        reader.readAsDataURL(blob);
                    });
                }
                return null;
            }
        """)
        if pdf_base64:
            import base64
            pdf_bytes = base64.b64decode(pdf_base64)
            if pdf_bytes[:4] == b'%PDF':
                with open(save_path, 'wb') as f: f.write(pdf_bytes)
                return True
        return False
    except: return False

def convert_html_to_pdf_playwright(context, html_url: str, save_path: str) -> bool:
    pdf_page = None
    try:
        pdf_page = context.new_page()
        pdf_page.add_init_script("window.print = function() { return false; };")
        pdf_page.goto(html_url, timeout=45000)
        pdf_page.wait_for_load_state('networkidle', timeout=20000)
        time.sleep(5)
        pdf_page.pdf(path=save_path, format='A4', print_background=True)
        pdf_page.close()
        return os.path.exists(save_path)
    except:
        if pdf_page: pdf_page.close()
        return False

def is_html_report(url: str) -> bool:
    try: 
        return parse_qs(urlparse(url).query).get('pdf', ['true'])[0].lower() == 'false'
    except: 
        return False

def read_patients_from_gsheets(sheet_url: str) -> dict:
    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        planilha = gc.open_by_url(sheet_url).sheet1
        df = pd.DataFrame(planilha.get_all_records())

        if AGENT_ONLY_MODE:
            pacientes_filtrados = [
                {
                    "sheet_row": index + 2,
                    "nome": str(row.get("Por gentileza, informe o seu nome completo:", "")).strip(),
                    "cpf": str(row.get("CPF", "")).strip(),
                    "status": str(row.get("STATUS", "")).strip(),
                }
                for index, row in df.iterrows()
                if str(row.get("Por gentileza, informe o seu nome completo:", "")).strip()
            ]
        else:
            pacientes_filtrados = [
                {
                    "sheet_row": index + 2,
                    "nome": str(row.get("Por gentileza, informe o seu nome completo:", "")).strip(),
                    "cpf": str(row.get("CPF", "")).strip(),
                    "status": str(row.get("STATUS", "0")).strip(),
                }
                for index, row in df.iterrows()
                if str(row.get("STATUS", "0")) == "1"
                and str(row.get("Por gentileza, informe o seu nome completo:", "")).strip()
            ]

        return {"pacientes": pacientes_filtrados, "total_linhas": len(df)}
    except Exception as e: return {"error": str(e)}

def update_sheet_status(sheet_url, row_index, status_value):
    try:
        gc = gspread.service_account(filename=CREDENTIALS_FILE)
        sh = gc.open_by_url(sheet_url).sheet1
        headers = sh.row_values(1)
        if "STATUS" in headers:
            col_idx = headers.index("STATUS") + 1
            sh.update_cell(row_index, col_idx, status_value)
    except: pass


def process_patient_exams(nome_paciente: str, cpf_paciente: str) -> dict:
    print(f"    [RPA] Iniciando Playwright para {nome_paciente}")
    USER_DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
    
    stats = {
        "status": "success", 
        "alvos_encontrados": 0, 
        "sucesso_rpa": 0, 
        "falha_rpa_enviado_ia": 0
    }

    with sync_playwright() as p:
        browser, context = None, None
        try:
            browser = p.chromium.launch(headless=HEADLESS_MODE)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            page.goto(SITE_URL, timeout=60000)
            page.fill(f"#{USER_FIELD_SELECTOR}", USER)
            page.fill(f"#{PASS_FIELD_SELECTOR}", PASS)
            with page.expect_navigation(): page.click(f"#{LOGIN_BUTTON_SELECTOR}")

            page.locator(f"#{SEARCH_BAR_SELECTOR}").fill(remove_accents(nome_paciente))
            page.press(f"#{SEARCH_BAR_SELECTOR}", "Enter")

            try: page.locator("#patientsTableBody tr:first-child").wait_for(state="visible", timeout=15000)
            except: 
                stats["status"] = "not_found"
                return stats

            found, id_cell = False, ""
            for row in page.locator("#patientsTableBody tr").all():
                if normalize_name(row.locator("td:nth-child(1)").inner_text()) == normalize_name(nome_paciente):
                    found, id_cell = True, row.locator("td:nth-child(2)").inner_text().strip()
                    row.locator("td:nth-child(1)").click()
                    break

            if not found: 
                stats["status"] = "not_found"
                return stats

            page.locator(".studyControlPlace").first.wait_for(state='visible', timeout=15000)
            
            print(f"    [RPA] Lendo histórico completo de exames...")
            ultimo_count = 0
            tentativas_sem_mudanca = 0
            
            while tentativas_sem_mudanca < 5:
                elementos = page.locator(".studyControlPlace")
                count_atual = elementos.count()
                
                if count_atual > 0:
                    try:
                        elementos.nth(count_atual - 1).scroll_into_view_if_needed()
                        page.keyboard.press("PageDown")
                        page.mouse.wheel(0, 2000)
                    except: pass
                
                time.sleep(2.5)
                novo_count = page.locator(".studyControlPlace").count()
                
                if novo_count > count_atual:
                    tentativas_sem_mudanca = 0
                    ultimo_count = novo_count
                else:
                    tentativas_sem_mudanca += 1

            num_exams = page.locator(".studyControlPlace").count()
            history = read_download_history()
            ID_PACIENTE = id_cell.zfill(16)

            exames_alvo = []
            exames_vistos_nesta_sessao = set()

            for i in range(num_exams):
                cont = page.locator(".studyControlPlace").nth(i)
                texto_completo_card = cont.inner_text().strip()
                html_content = cont.inner_html().lower()
                
                try: date_text = cont.locator(".sccDate").inner_text().strip()
                except: date_text = "Data Oculta"
                
                if "apenas imagens" in html_content:
                    continue

                name_str_limpo = texto_completo_card.replace('\n', ' ').strip()

                if check_exam_date(date_text) and is_relevant_exam(texto_completo_card):
                    
                    exam_history_id = f"{nome_paciente}-{ID_PACIENTE}-{date_text}-{name_str_limpo}"
                    
                    if exam_history_id not in history and exam_history_id not in exames_vistos_nesta_sessao: 
                        exames_vistos_nesta_sessao.add(exam_history_id)
                        exames_alvo.append({
                            "index": i,
                            "date": date_text,
                            "name": name_str_limpo,
                            "history_id": exam_history_id
                        })
            
            stats["alvos_encontrados"] = len(exames_alvo)
            print(f"    [RPA] Mapeamento interno concluído: {len(exames_alvo)} exames únicos serão baixados.")

            for alvo in exames_alvo:
                i = alvo["index"]
                date_text = alvo["date"]
                name_str = alvo["name"]
                exam_history_id = alvo["history_id"]

                try:
                    cont = page.locator(".studyControlPlace").nth(i)
                    cont.scroll_into_view_if_needed()
                    
                    exame_safe = remove_accents(name_str)
                    
                    # O limite [:80] fica APENAS aqui para evitar que o Windows dê erro de 'caminho muito longo'
                    filename = re.sub(r'[\\/*?:"<>|]', '_', f"0000000000000001_{remove_accents(nome_paciente)}_{ID_PACIENTE}_{str(cpf_paciente).replace('.0','')}_{date_text.split(' ')[0].replace('/', '-')}_{exame_safe[:80]}.pdf")
                    temp_save_path, final_dest_path = os.path.join(USER_DOWNLOADS, filename), os.path.join(DOWNLOAD_DIR, filename)

                    print(f"    [RPA] ⬇ Baixando via Iframe: {name_str[:50]}...")

                    cont.locator("div[id$='_study']").click(force=True)
                    time.sleep(3)

                    file_saved, pdf_url, new_page = False, None, None
                    relatorio_indisponivel = False
                    
                    def handle_new_page(new_pg):
                        try: new_pg.add_init_script("window.print = function() { return false; };")
                        except: pass

                    context.on("page", handle_new_page)
                    try:
                        with context.expect_page(timeout=15000) as np: 
                            page.locator("span[id$='_printBtn'].btnPrint").click(force=True)
                        new_page = np.value
                        new_page.wait_for_load_state('domcontentloaded', timeout=15000)
                        time.sleep(2)

                        try:
                            conteudo_pagina = new_page.content().lower()
                            if "não está disponível para exibição" in conteudo_pagina or "relatório não está disponível" in conteudo_pagina:
                                relatorio_indisponivel = True
                            else:
                                for frame in new_page.frames:
                                    try:
                                        if "não está disponível para exibição" in frame.content().lower():
                                            relatorio_indisponivel = True
                                            break
                                    except: pass
                        except: pass

                        if not relatorio_indisponivel:
                            new_page_url = new_page.url
                            iframe_locator = new_page.locator('iframe#PrintFrame, iframe[src*="ReportService"], iframe').first
                            
                            if iframe_locator.count() > 0:
                                iframe_src = iframe_locator.get_attribute('src')
                                if iframe_src:
                                    if iframe_src.startswith('./') or iframe_src.startswith('/'):
                                        pdf_url = f"{urlparse(new_page_url).scheme}://{urlparse(new_page_url).netloc}{iframe_src.replace('./', '/')}"
                                    else: pdf_url = iframe_src

                            is_html = is_html_report(new_page_url)

                            if pdf_url and not is_html:
                                file_saved = download_pdf_from_url(pdf_url, context.cookies(), temp_save_path)
                                if file_saved:
                                    with open(temp_save_path, 'rb') as f:
                                        if f.read(4) != b'%PDF': 
                                            os.remove(temp_save_path)
                                            file_saved, is_html = False, True

                            if not file_saved and not is_html:
                                try:
                                    js_pdf_url = new_page.evaluate("() => { const iframe = document.querySelector('iframe'); return iframe ? iframe.src : null; }")
                                    if js_pdf_url: file_saved = download_pdf_from_url(js_pdf_url, context.cookies(), temp_save_path)
                                except: pass

                            if not file_saved: 
                                file_saved = extract_pdf_from_blob_url(new_page, temp_save_path)

                            if not file_saved and (is_html or pdf_url):
                                file_saved = convert_html_to_pdf_playwright(context, pdf_url or new_page_url, temp_save_path)

                    except Exception as e: 
                        print(f"    [AVISO] Erro ao extrair PDF: {e}")
                    finally:
                        try: context.remove_listener("page", handle_new_page)
                        except: pass
                        if new_page:
                            try: new_page.close()
                            except: pass
                            
                        try: page.keyboard.press("Escape")
                        except: pass
                        time.sleep(1)

                    if file_saved and os.path.exists(temp_save_path):
                        if os.path.exists(final_dest_path): os.remove(final_dest_path)
                        shutil.move(temp_save_path, final_dest_path)
                        
                        write_download_history(exam_history_id)
                        stats["sucesso_rpa"] += 1
                        # comentar as duas linhas abaixo para evitar upload real durante os testes
                        if upload_to_api(final_dest_path, "0000000000000001", ID_PACIENTE):
                            pass
                            
                        #print(f"    [RPA] Sucesso na extração! (Upload API desativado)")
                    elif relatorio_indisponivel:
                        print(f"    [RPA] Laudo indisponível no servidor do hospital. Ignorando...")
                        write_download_history(exam_history_id)
                        stats["alvos_encontrados"] -= 1
                    else:
                        print(f"    [RPA] Falha na extração. Enviando para a fila da IA...")
                        write_pendente_ia({"nome": nome_paciente, "cpf": cpf_paciente, "exam_history_id": exam_history_id, "data_exame": date_text, "nome_exame": name_str})
                        stats["falha_rpa_enviado_ia"] += 1

                except Exception as e: 
                    print(f"    [RPA] Erro crítico no exame {name_str}: {e}")
                    write_pendente_ia({"nome": nome_paciente, "cpf": cpf_paciente, "exam_history_id": exam_history_id, "data_exame": date_text, "nome_exame": name_str})
                    stats["falha_rpa_enviado_ia"] += 1

            if stats["falha_rpa_enviado_ia"] > 0:
                stats["status"] = "partial_fail"
                
            return stats
        except Exception as e:
            print(f"    [RPA] Erro crítico no Playwright: {e}")
            stats["status"] = "critical_error"
            return stats
        finally:
            if browser: browser.close()