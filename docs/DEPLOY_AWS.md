# Deploy na AWS — ClickPalmIA (APA agêntico)

Registro operacional do que foi criado na conta AWS e os comandos pra rodar,
monitorar, mexer nos dados e limpar tudo. Base teórica em
[`Deploy_AWS_Metricas_Custo_RPA_vs_APA.docx`](Deploy_AWS_Metricas_Custo_RPA_vs_APA.docx).

## Recursos criados

Os identificadores reais (account ID, VPC/subnet/SG, EFS, nomes de role) não
ficam neste arquivo público — estão em `docs/bedrock-deploy/deploy.env`
(gitignored). Copie `docs/bedrock-deploy/deploy.env.example` para
`deploy.env` e preencha antes de rodar os comandos abaixo; todos os exemplos
usam as variáveis de lá (`$AWS_ACCOUNT_ID`, `$ECS_CLUSTER`, `$SUBNET_ID_A`,
etc. — carregue com `source docs/bedrock-deploy/deploy.env`).

| Recurso | Descrição |
|---|---|
| Repositório ECR | `$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME` |
| Cluster ECS | `$ECS_CLUSTER` |
| Task Definition (produção) | `$ECS_TASK_FAMILY:2` — 1 vCPU / 2GB |
| Task Definition (debug/shell) | `$ECS_TASK_FAMILY_DEBUG:1` — mesma imagem, `entryPoint=sleep 3600` |
| Execution Role | `$EXECUTION_ROLE_NAME` (pull da imagem + leitura dos secrets) |
| Task Role | `$TASK_ROLE_NAME` (permissões extras pontuais, ex. ECS Exec, Bedrock) |
| EFS (dados persistentes) | `$EFS_ID`, access point `$EFS_ACCESS_POINT_ID` → montado em `/data` |
| Secrets Manager | `clickpalmia-apa/PORTAL_USER`, `clickpalmia-apa/PORTAL_PASS`, `clickpalmia-apa/GEMINI_API_KEY`, `clickpalmia-apa/GEMINI_FALLBACK_API_KEY` |
| Log group | `$LOG_GROUP` |
| VPC / Subnets / SG | `$VPC_ID` / `$SUBNET_ID_A` (us-east-1a), `$SUBNET_ID_B` (us-east-1b) / `$SECURITY_GROUP_ID` |

Com `RESULTS_S3_URI`, a task publica telemetria e relatórios no bucket privado.
PDFs de laudo permanecem no EFS por padrão, pois contêm dados de paciente. Para
batches de teste, `RESULTS_S3_UPLOAD_PDFS=true` publica os PDFs em `exames/`. O
`credenciais.json` continua fora do S3, montado como arquivo somente leitura.

Exemplo de variáveis na task definition:

```text
RESULTS_S3_URI=s3://clickpalmia-metricas-857145323577/apa
# Somente em batch de teste, se for necessário armazenar os PDFs.
RESULTS_S3_UPLOAD_PDFS=false
DATA_DIR=/tmp/clickpalmia
```

A Task Role precisa permitir `s3:GetObject`, `s3:PutObject` e `s3:ListBucket`
somente no bucket/prefixo usados pelos resultados.

Preço do LLM configurado na task definition (Gemini 3.1 Flash-Lite, tier padrão):
`LLM_PRECO_MILHAO_ENTRADA=0.25`, `LLM_PRECO_MILHAO_SAIDA=1.50` (USD/milhão de tokens).

## Pré-requisitos locais

```bash
# AWS CLI v2 (instalado em ~/.local/bin/aws neste ambiente)
aws --version

# Autenticação — rodar num terminal de verdade, nunca colar chaves no chat:
aws configure

# Session Manager plugin (necessário pro ECS Exec)
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/linux_64bit/session-manager-plugin.rpm" -o session-manager-plugin.rpm
sudo dnf install -y ./session-manager-plugin.rpm

# Carrega os identificadores reais da conta (ver seção "Recursos criados" acima)
cp docs/bedrock-deploy/deploy.env.example docs/bedrock-deploy/deploy.env   # 1a vez só
source docs/bedrock-deploy/deploy.env
```

## 1. Build + push da imagem (repetir a cada mudança de código)

```bash
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"

docker build -t "$ECR_REPO_NAME:latest" .
docker tag "$ECR_REPO_NAME:latest" "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:latest"
docker push "$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$ECR_REPO_NAME:latest"
```

Se mudar `app/core/config.py` (novas env vars) ou o tamanho da task, registrar nova
revisão da task definition antes de rodar — ver `docs/bedrock-deploy/update-task-def-for-bedrock.sh`
(script pronto pra isso, já usado pra migrar pra Bedrock/Haiku).

## 2. Rodar o pipeline de produção

```bash
aws ecs run-task --cluster "$ECS_CLUSTER" \
  --task-definition "$ECS_TASK_FAMILY" \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID_A],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
  --region "$AWS_REGION"
```

Guarde o `taskArn` da resposta. Só processa pacientes com `STATUS=1` na planilha;
ao concluir com sucesso, o app zera o `STATUS` deles (não reprocessa sozinho).

**Acompanhar status:**
```bash
aws ecs describe-tasks --cluster "$ECS_CLUSTER" --tasks SEU_TASK_ARN --region "$AWS_REGION" \
  --query "tasks[0].{status:lastStatus,stopCode:stopCode,reason:stoppedReason}"
```

**Ver logs em tempo real:**
```bash
aws logs tail "$LOG_GROUP" --follow --region "$AWS_REGION"
```

## 3. Preencher/atualizar os secrets

Rodar sempre no seu terminal local — nunca colar valores reais no chat:

```bash
aws secretsmanager put-secret-value --secret-id clickpalmia-apa/PORTAL_USER --secret-string "SEU_LOGIN"
aws secretsmanager put-secret-value --secret-id clickpalmia-apa/PORTAL_PASS --secret-string "SUA_SENHA"
aws secretsmanager put-secret-value --secret-id clickpalmia-apa/GEMINI_API_KEY --secret-string "SUA_GEMINI_API_KEY"
aws secretsmanager put-secret-value --secret-id clickpalmia-apa/GEMINI_FALLBACK_API_KEY --secret-string "SUA_GEMINI_FALLBACK_API_KEY"
```

## 4. Acessar o EFS (dados persistentes) via ECS Exec

O container de produção só roda `python -m app.main` — pra mexer nos arquivos de
`/data` (ver PDFs, editar gabarito, resetar histórico) precisa de uma task auxiliar
com shell:

```bash
# Sobe a task de debug (sleep 3600, encerra sozinha em 1h)
aws ecs run-task --cluster "$ECS_CLUSTER" \
  --task-definition "$ECS_TASK_FAMILY_DEBUG" \
  --launch-type FARGATE \
  --enable-execute-command \
  --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_ID_A],securityGroups=[$SECURITY_GROUP_ID],assignPublicIp=ENABLED}" \
  --region "$AWS_REGION"
# guarde o taskArn/ID retornado

# Espera ficar RUNNING (ExecuteCommandAgent também precisa estar RUNNING)
aws ecs describe-tasks --cluster "$ECS_CLUSTER" --tasks SEU_TASK_ID --region "$AWS_REGION" \
  --query "tasks[0].{status:lastStatus,agent:containers[0].managedAgents[0].lastStatus}"

# Abre um shell interativo dentro do container
aws ecs execute-command --cluster "$ECS_CLUSTER" \
  --task SEU_TASK_ID --container shell --interactive --command "/bin/bash"
```

**Quando terminar, sempre parar a task de debug** (evita custo residual):
```bash
aws ecs stop-task --cluster "$ECS_CLUSTER" --task SEU_TASK_ID \
  --reason "fim do debug" --region "$AWS_REGION"
```

### Comandos úteis dentro do shell (`/data` = EFS)

```bash
# Listar PDFs baixados
ls -la /data/downloads

# Ver histórico de anti-duplicação
cat /data/historico_downloads.json

# Zerar SÓ downloads + histórico (permite reprocessar os mesmos pacientes)
rm -rf /data/downloads /data/historico_downloads.json && mkdir -p /data/downloads

# Zerar SÓ métricas (telemetria/gabarito/refinado)
rm -rf /data/metricas && mkdir -p /data/metricas

# Reset completo (mantém sempre credenciais.json)
rm -rf /data/downloads /data/metricas /data/reports /data/historico_downloads.json
mkdir -p /data/downloads /data/metricas /data/reports
```

**Importante:** resetar `historico_downloads.json` no EFS não reabre a fila
sozinho — o `STATUS` do paciente na planilha do Google Sheets também precisa
voltar pra `1` manualmente, senão o pipeline nem inclui ele na fila.

## 5. Gerar as métricas (Blocos 1 + 3 + custo)

Dentro do shell da task de debug, mesmo fluxo do `README.md`:

```bash
python calcular_metricas.py --gerar-gabarito
# revisar a coluna "autorizado" (1/0) no gabarito.csv — ver seção 6 (transferir arquivo)
python calcular_metricas.py --validar-gabarito   # opcional, precisa do termo .xlsx
python calcular_metricas.py                      # gera geral.csv e detalhado_<run_id>.csv em /data/metricas/refinado
```

O `geral.csv`/`detalhado_*.csv` já saem com `Custo_Infra`, `Custo_LLM`, `Custo_Total`
e `Custo_por_1000_Exec`, calculados a partir dos blocos `infra`/`llm` gravados na
telemetria (`app/reporting/manager.py`).

## 6. Transferir arquivos entre seu computador e o EFS

O EFS só é alcançável de dentro da VPC — não dá pra montar direto do seu laptop.
O caminho usado (pra `credenciais.json` e `gabarito.csv`) foi um bucket S3
temporário, sempre criado/apagado na hora (nunca deixado de pé):

```bash
# 1. Criar bucket privado temporário
BUCKET="clickpalmia-apa-tmp-${AWS_ACCOUNT_ID}"
aws s3api create-bucket --bucket "$BUCKET" --region "$AWS_REGION"
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'

# 2. Dar permissão temporária de leitura/escrita à Task Role (arquivo de política com
#    Resource restrito ao objeto específico, ex. arn:aws:s3:::$BUCKET/NOME_ARQUIVO)
aws iam put-role-policy --role-name "$TASK_ROLE_NAME" \
  --policy-name tmp-s3-transfer --policy-document file://politica.json

# 3a. Subir do EFS pro S3 (dentro do shell da task de debug)
python3 -c "import boto3; boto3.client('s3', region_name='$AWS_REGION').upload_file('/data/CAMINHO','$BUCKET','NOME_ARQUIVO')"
# 3b. Baixar do S3 pro EFS (dentro do shell)
python3 -c "import boto3; boto3.client('s3', region_name='$AWS_REGION').download_file('$BUCKET','NOME_ARQUIVO','/data/CAMINHO')"

# 4. No seu terminal local: baixar/subir do bucket normalmente
aws s3 cp s3://$BUCKET/NOME_ARQUIVO NOME_ARQUIVO
aws s3 cp NOME_ARQUIVO s3://$BUCKET/NOME_ARQUIVO

# 5. Limpar sempre depois de usar
aws s3 rm s3://$BUCKET/NOME_ARQUIVO
aws s3api delete-bucket --bucket "$BUCKET" --region "$AWS_REGION"
aws iam delete-role-policy --role-name "$TASK_ROLE_NAME" --policy-name tmp-s3-transfer
```

Pra colar segredos (senhas, chaves) dentro do container, prefira sempre esse
caminho via S3 em vez de colar direto no terminal do ECS Exec — heredocs com
JSON/chave privada quebram fácil no paste de uma sessão SSM.

## 7. Rodar localmente antes de subir (docker compose)

```bash
docker compose up --build
```

Usa `.env` local + `credenciais.json` local via bind mount (`docker-compose.yml`),
grava em `./data` — não toca no EFS nem em nenhum recurso AWS. Bom pra validar
uma mudança de código antes de fazer build+push pro ECR.

## Pendências / decisões já tomadas

- **LLM em produção:** Bedrock/Claude Haiku 4.5 (`LLM_PROVIDER=bedrock`), via
  Task Role (sem chave estática) — decisão trocada de Gemini pra Bedrock em
  2026-07-23. Task Role autenticada via `bedrock:InvokeModel` (ver
  `bedrock-invoke-policy.json`), sem Bedrock API key/bearer token na task
  definition (esses expiram em ~12h e não servem pra workload Fargate).
- **Tamanho da Task:** 1 vCPU / 2GB (bate com `INFRA_VCPU`/`INFRA_MEMORIA_GB` no
  `.env` e na task definition, usados pelo cálculo de custo).
- **Conta AWS:** já existia, com permissões prontas para ECS/ECR/EFS/Secrets/IAM.
