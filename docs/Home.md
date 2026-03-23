# NFe Scraper API

API em FastAPI para ingestão de NFC-e a partir de imagens de QR Code (ex.: fotos do Telegram/WhatsApp), fazendo:

- Leitura robusta do QR Code (WeChat QR + PyZbar + filtros de imagem).
- Scraping da SEFAZ usando Playwright (Chromium headless).
- Armazenamento do HTML bruto no MinIO (camada Bronze).
- Registro de metadados e payload Silver em PostgreSQL.
- Retorno de um JSON “Silver” com itens, valores e validação da nota.

## Principais Tecnologias

- Backend: Python 3.10, FastAPI, Uvicorn
- Visão: OpenCV (wechat_qrcode), PyZbar
- Scraping: Playwright (Chromium headless)
- Storage: MinIO (compatível S3), PostgreSQL (asyncpg)
- Parsing: BeautifulSoup4

## Fluxo Resumido

1. Workflow (ex.: n8n) envia uma imagem via `POST /ingest/`.
2. A API decodifica o QR Code na imagem.
3. Playwright acessa a URL da SEFAZ e captura o HTML da nota.
4. O HTML é salvo no MinIO (Bronze) e metadados vão para o Postgres.
5. O HTML é parseado para um JSON Silver (itens, totais, pagamento).
6. A resposta HTTP devolve chave de acesso, caminho no MinIO e payload Silver.
