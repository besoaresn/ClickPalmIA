#!/usr/bin/env bash
# Registra uma nova revisão de clickpalmia-apa apontando para Bedrock/Claude.
# Roda no SEU terminal (precisa de `aws configure` / sessão válida). Requer `jq`.
#
# O que faz:
#   1. Baixa a task definition ativa (clickpalmia-apa:2, ou a revisão passada em $1)
#   2. Sobrescreve/insere as env vars de LLM_PROVIDER=bedrock
#   3. Registra a nova revisão
#   4. Imprime o comando pra rodar essa revisão com `ecs run-task`
#
# Não roda nada destrutivo sozinho — a revisão antiga continua existindo,
# então dá pra voltar pra ela se algo der errado.

set -euo pipefail

REGION="us-east-1"
FAMILY="clickpalmia-apa"
CURRENT_REVISION="${1:-3}"   # ajuste se a revisão em produção não for mais a :3
ROLE_NAME="clickpalmia-apa-task-role"

echo "== 1. Baixando task definition ${FAMILY}:${CURRENT_REVISION} =="
aws ecs describe-task-definition \
  --task-definition "${FAMILY}:${CURRENT_REVISION}" \
  --region "$REGION" \
  --query "taskDefinition" > /tmp/current-task-def.json

echo "== 2. Aplicando env vars de Bedrock =="
# Ajusta o [] .environment do primeiro container da task definition.
# containerDefinitions[0] assume que só há 1 container (padrão neste projeto).
jq '
  .containerDefinitions[0].environment as $env
  | ($env | map(select(.name != "LLM_PROVIDER" and .name != "BEDROCK_MODEL"
      and .name != "BEDROCK_FALLBACK_MODEL" and .name != "AWS_REGION"
      and .name != "BEDROCK_AUTH_MODE"))) as $filtered
  | .containerDefinitions[0].environment = ($filtered + [
      {"name": "LLM_PROVIDER", "value": "bedrock"},
      {"name": "BEDROCK_MODEL", "value": "us.anthropic.claude-haiku-4-5-20251001-v1:0"},
      {"name": "BEDROCK_FALLBACK_MODEL", "value": "us.anthropic.claude-haiku-4-5-20251001-v1:0"},
      {"name": "AWS_REGION", "value": "us-east-1"},
      {"name": "BEDROCK_AUTH_MODE", "value": "default"}
    ])
  # register-task-definition não aceita estes campos de volta:
  | del(.taskDefinitionArn, .revision, .status, .requiresAttributes,
        .compatibilities, .registeredAt, .registeredBy, .deregisteredAt)
' /tmp/current-task-def.json > /tmp/new-task-def.json

echo "== 3. Registrando nova revisão =="
NEW_ARN=$(aws ecs register-task-definition \
  --cli-input-json file:///tmp/new-task-def.json \
  --region "$REGION" \
  --query "taskDefinition.taskDefinitionArn" \
  --output text)

echo "Nova task definition: $NEW_ARN"

echo "== 4. Adicionando permissão de Bedrock na Task Role =="
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name bedrock-invoke-claude \
  --policy-document file://bedrock-invoke-policy.json

echo
echo "Pronto. Para rodar essa revisão:"
echo "aws ecs run-task --cluster clickpalmia-cluster \\"
echo "  --task-definition ${NEW_ARN##*/} \\"
echo "  --launch-type FARGATE \\"
echo "  --network-configuration \"awsvpcConfiguration={subnets=[subnet-08a235d2e57ee59f8],securityGroups=[sg-028d8d6bc1293f41d],assignPublicIp=ENABLED}\" \\"
echo "  --region us-east-1"
