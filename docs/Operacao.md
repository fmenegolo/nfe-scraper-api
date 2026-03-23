# Operação & Troubleshooting

## Logs

- Os logs usam `logging` com formato JSON-like por linha.
- Controle de nível via `LOG_LEVEL` (`INFO` recomendado em produção).
- Erros de scraping e parsing aparecem com stack trace (logger.exception).

## Problemas Comuns

### 1. QR Code não detectado

- Verificar qualidade da imagem (foco, recorte).
- Verificar se o tamanho não estourou `MAX_UPLOAD_SIZE_MB`.
- Conferir logs de `vision.py` (mensagens de falha no WeChat/PyZbar).

### 2. Erro na SEFAZ (scraping)

- Logs: mensagens de `scraper.py` com status HTTP da SEFAZ.
- Possíveis causas:
  - Instabilidade no site da SEFAZ.
  - Mudança de layout (HTML diferente).

### 3. Problemas com MinIO / Postgres

- Erro retorna `500` com mensagem genérica.
- Detalhes aparecem apenas nos logs:
  - Falha de conexão
  - Permissões / credenciais
- Conferir variáveis de ambiente de MinIO e Postgres.

### 4. Alto consumo de recursos

- Ajustar `PLAYWRIGHT_MAX_CONTEXTS` para controlar o número de abas em paralelo.
- Ajustar `LOG_LEVEL` para reduzir ruído em produção.
