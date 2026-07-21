# Texto para o chamado de suporte AWS

Abrir em: https://console.aws.amazon.com/support/home#/case/create
Tipo: **"Account and billing support"** (gratuito, não precisa de plano de suporte pago)
Categoria sugerida: **Service Limit Increase** (se não tiver Bedrock na lista, usar "Other Account and Billing Issue")

---

**Assunto:** Liberação de acesso programático (API) ao Amazon Bedrock — conta nova

**Descrição:**

Minha conta AWS (ID 857145323577) consegue usar modelos Anthropic Claude no
Bedrock Playground (console) normalmente — testei o Claude Haiku 4.5 na região
us-east-1 e funcionou.

Porém, chamadas programáticas à API (`Converse`/`InvokeModel`, via boto3/CLI)
retornam `ThrottlingException: Too many tokens per day` para qualquer modelo
Claude (testei Haiku 4.5, Sonnet 5 e Opus 4.1), mesmo modelo e região do teste
que funcionou no console.

Ao consultar `list-service-quotas` para o serviço `bedrock`, a cota "Model
invocation max tokens per day" para esses modelos aparece com valor `0.0` e
`Adjustable: false` — não consigo solicitar aumento pelo Service Quotas normal.

**Pedido:** Preciso que o acesso de invocação programática (API) ao Bedrock
seja liberado para esta conta, para os modelos Anthropic Claude (uso via
inference profile `us.anthropic.claude-haiku-4-5-20251001-v1:0`), na região
us-east-1. É para um caso de uso de produção (extração de dados estruturados
de documentos), volume moderado.

---

Depois de enviado, a AWS costuma responder/resolver em algumas horas a 1-2 dias
úteis. Quando a cota for liberada, é só rodar de novo:

```bash
python3 docs/bedrock-deploy/smoke_test_bedrock.py
```
