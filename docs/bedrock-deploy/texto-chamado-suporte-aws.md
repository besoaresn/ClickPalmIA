# Texto para o chamado de suporte AWS

Abrir em: https://console.aws.amazon.com/support/home#/case/create
Tipo: **"Account and billing support"** (gratuito, não precisa de plano de suporte pago)
Categoria sugerida: **Service Limit Increase** (se não tiver Bedrock na lista, usar "Other Account and Billing Issue")

---

**Assunto:** Liberação de acesso programático (API) ao Amazon Bedrock — conta nova

**Descrição:**

Minha conta AWS (ID <AWS_ACCOUNT_ID> — ver `docs/bedrock-deploy/deploy.env`) consegue usar modelos Anthropic Claude no
Bedrock Playground (console) normalmente — testei o Claude Haiku 4.5 na região
us-east-1 e funcionou.

Porém, chamadas programáticas à API (`Converse`/`InvokeModel`, via boto3/CLI)
retornam `ThrottlingException: Too many tokens per day` para **qualquer**
modelo testado — não é específico da Anthropic: reproduzi o mesmo erro com
Claude Haiku 4.5, Claude Opus 4.6, Claude 3 Haiku (modelo antigo, invocação
on-demand direta, sem inference profile) e até com `amazon.nova-micro-v1:0`
(modelo da própria AWS). Testei com 3 métodos de credencial diferentes
(usuário IAM, IAM role via ECS Task Role, Bedrock API key) — mesmo erro em
todos. Isso indica que a restrição é da conta como um todo, não de um modelo
ou provider específico.

Ao consultar `list-service-quotas` para o serviço `bedrock`, TODAS as cotas
"Model invocation max tokens per day" da conta aparecem com valor `0.0` e
`Adjustable: false` (Anthropic, Amazon Nova, Meta, Mistral etc.) — não
consigo solicitar aumento pelo Service Quotas normal. `list-requested-service-quota-change-history`
não mostra nenhum pedido de aumento anterior para `bedrock` nesta conta.

**Pedido:** Preciso que o acesso de invocação programática (API) ao Bedrock
seja liberado para esta conta (a cota de "tokens per day" está zerada pra
todos os modelos, não só Anthropic), na região us-east-1. Uso principal
via inference profile `us.anthropic.claude-haiku-4-5-20251001-v1:0`. É para
um caso de uso de produção (extração de dados estruturados de documentos),
volume moderado.

---

Depois de enviado, a AWS costuma responder/resolver em algumas horas a 1-2 dias
úteis. Quando a cota for liberada, é só rodar de novo:

```bash
python3 docs/bedrock-deploy/smoke_test_bedrock.py
```
