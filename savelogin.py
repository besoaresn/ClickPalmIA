import time
from playwright.sync_api import sync_playwright

def run(playwright):
    # Inicia o navegador em modo "headed" (visível)
    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    # 1. MUDE AQUI: Coloque o link da sua página de login
    page.goto("https://crm.rdstation.com/app/deals/pipeline")

    print("--- SCRIPT PAUSADO ---")
    print("1. Vá para a janela do navegador que abriu.")
    print("2. Faça o login manualmente (usuário, senha e RESOLVA O CAPTCHA).")
    print("3. Após estar LOGADO (na página principal), volte aqui no terminal.")
    
    # Pausa o script e espera você apertar Enter no terminal
    input("4. Pressione ENTER aqui no terminal para continuar e salvar a sessão...")

    # 5. O script continua...
    # Salva o estado de autenticação (cookies, etc.) em um arquivo
    context.storage_state(path="auth.json")

    print("✅ Estado de autenticação salvo com sucesso em auth.json!")
    browser.close()

with sync_playwright() as p:
    run(p)