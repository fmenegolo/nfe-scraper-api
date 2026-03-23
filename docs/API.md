# Referência da API

Base URL (exemplo): `http://seu-host:8000`

## Healthcheck

**GET /**

- Retorna:
  ```json
  { "status": "online" }
  ```

## Ingestão de NFe

**POST /ingest/**

- Content-Type: `multipart/form-data`
- Campo: `file` (UploadFile) – imagem contendo o QR Code da NFC-e.

### Respostas

- `200 OK`
  ```json
  {
    "status": "success",
    "chave": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "s3_raw": "bronze/nfce/2026/03/<chave>.html",
    "payload": {
      "store_name": "...",
      "cnpj": "...",
      "address": "...",
      "nfe_number": "...",
      "nfe_series": "...",
      "issuance_date_time": "...",
      "gross_value": 0.0,
      "discount_value": 0.0,
      "total_paid": 0.0,
      "payment_method": "...",
      "change_value": 0.0,
      "items": [
        {
          "name": "...",
          "quantity": 1.0,
          "unit": "UN",
          "unit_value": 10.0,
          "item_total": 10.0
        }
      ],
      "calculated_items_total": 10.0,
      "validation": "matched"
    }
  }
  ```

- `404 Not Found`
  - Quando o QR Code não é detectado na imagem.

- `413 Payload Too Large`
  - Quando o arquivo de imagem ultrapassa `MAX_UPLOAD_SIZE_MB`.

- `500 Internal Server Error`
  - Falha no scraping da SEFAZ ou na camada Bronze (MinIO/Postgres).

### Observações

- A API valida o tamanho máximo do arquivo antes de processar.
- O scraping usa Playwright com controle de concorrência (`PLAYWRIGHT_MAX_CONTEXTS`) para evitar sobrecarga.
- Em caso de reprocessar a mesma chave, o registro em Postgres é atualizado (idempotência via `ON CONFLICT`).
