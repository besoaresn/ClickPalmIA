import asyncio
from time import sleep

import pandas as pd
from playwright.async_api import async_playwright

try:
    df = pd.read_excel("testeRd.xlsx")  # dataframe, tabela de memoria
    listanegociacoes = df.to_dict(
        "records"
    )  # converte a planilha em uma lista de dicionario
    print(f"{len(listanegociacoes)} negociações carregadas do excel")
except FileNotFoundError:
    print("Erro: Arquivo 'testeRd.xlsx' não encontrado.")
    print("Por favor, crie o arquivo Excel e tente novamente.")
    exit()
except Exception as e:
    print(f"Erro ao ler o Excel: {e}")
    exit()


async def run(playwright):
    navegador = await playwright.chromium.launch(headless=False)
    contexto = await navegador.new_context(storage_state="auth.json")
    page = await contexto.new_page()
    await page.goto("https://crm.rdstation.com/app/deals/pipeline")

    # Criar Negociação

    await page.get_by_role("button", name="Criar", exact=True).click()
    await page.get_by_role("menuitem", name="Icone de negociação Criar").click()

    for negociacao in listanegociacoes:
        await page.wait_for_timeout(3000)

<<<<<<< HEAD
        nome = negociacao["Nomes"]

        # preencher campos
        await page.get_by_role("textbox", name="Nome da negociação *").fill(nome)
        await page.get_by_text("Salvar e criar outra", exact=True).click()

    await navegador.close()


async def main():
    async with async_playwright() as playwright:
        await run(playwright)


if __name__ == "__main__":
    asyncio.run(main())
=======
      nome = negociacao['Nomes']
      
      # Fill campos
      page.get_by_role("textbox", name="Nome da negociação *").fill(nome)
      page.get_by_text("Salvar e criar outra", exact=True).click()


    navegador.close()

with sync_playwright() as playwright:
  run(playwright)
>>>>>>> 17996c4cb02946e7370d725391c53e9c6a13a649
