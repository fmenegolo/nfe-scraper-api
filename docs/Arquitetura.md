# Arquitetura & Fluxo de Dados

## Módulos Principais

- `vision.py`
  - Leitura de QR Code com OpenCV WeChat + PyZbar.
  - Limite de tamanho de upload e normalização de URL da SEFAZ.

- `scraper.py`
  - `BrowserManager` (singleton do Playwright).
  - `lifespan` do FastAPI para abrir/fechar o browser uma vez.
  - `scrape_nfe_content(url)`: captura o HTML da nota na SEFAZ.

- `parser.py`
  - `process_html_to_silver(html)`: extrai metadados, itens e totais do HTML.

- `storage.py`
  - `save_to_bronze(html, qr_key, silver_payload, url_origem)`:
    - Salva HTML no MinIO (`bronze/nfce/ano/mes/chave.html`).
    - Persiste em `bronze.nfe_raw` (Postgres) com:
      - `chave_acesso`, `s3_path_bronze`, `origem`
      - `url_origem`, `status_validacao`, `payload_json`.

- `api.py`
  - Instancia o `FastAPI` com `lifespan`.
  - Define os endpoints `/` e `/ingest/`.

- `main.py`
  - Apenas reexporta `app` de `api.py` para o Uvicorn (`uvicorn main:app`).

## Fluxo Bronze / Silver

1. Bronze (Raw)
   - HTML original da NFC-e no MinIO.
   - Metadados + `payload_json` no Postgres.

2. Silver (Refined)
   - JSON com:
     - Estabelecimento, números da nota, data/hora.
     - Totais, descontos, troco, forma de pagamento.
     - Lista de itens (produto, quantidade, unidade, valor unitário e total).
   - Campo `validation`:
     - `matched` quando soma dos itens ≈ valor alvo.
     - `discrepancy` quando há diferença relevante.
