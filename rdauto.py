from playwright.sync_api import sync_playwright
import pandas as pd
from time import sleep


try:
    df = pd.read_excel("testeRd.xlsx")              # dataframe, tabela de memoria
    listanegociacoes = df.to_dict('records')        # converte a planilha em uma lista de dicionario
    print(f"{len(listanegociacoes)} negociações carregadas do excel")
except FileNotFoundError:
    print("Erro: Arquivo 'testeRd.xlsx' não encontrado.")
    print("Por favor, crie o arquivo Excel e tente novamente.")
    exit()
except Exception as e:
    print(f"Erro ao ler o Excel: {e}")
    exit()
    

def run(playwright):
    navegador = playwright.chromium.launch(headless=False)
    contexto = navegador.new_context(storage_state="auth.json")
    page = contexto.new_page()
    page.goto("https://crm.rdstation.com/app/deals/pipeline")

    # Criar Negociação
    sleep(2)
    
    page.get_by_role("button", name="Criar", exact=True).click()
    page.get_by_role("menuitem", name="Icone de negociação Criar").click()

    

    for negociacao in listanegociacoes:
      page.wait_for_timeout(3000)

      nome = negociacao['Nomes']
      
      # Fill campos
      page.get_by_role("textbox", name="Nome da negociação *").fill(nome)
      page.get_by_text("Salvar e criar outra", exact=True).click()
      

    navegador.close()
    
with sync_playwright() as playwright:
  run(playwright)