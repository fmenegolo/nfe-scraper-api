# Instalação & Deploy

## Variáveis de Ambiente

A API lê todas as configs via `os.getenv`:

### MinIO

- `MINIO_ENDPOINT` – ex.: `minio:9000` ou `seu-ip:9000`
- `MINIO_ACCESS_KEY` – usuário
- `MINIO_SECRET_KEY` – senha
- `MINIO_BUCKET_NAME` – bucket (default: `bronze`)
- `MINIO_SECURE` – `true` para HTTPS, `false` para HTTP (default: `false`)

### PostgreSQL

- `POSTGRES_HOST` – host/serviço (default: `localhost`)
- `POSTGRES_PORT` – porta (default: `5432`)
- `POSTGRES_USER` – usuário (default: `user`)
- `POSTGRES_PASSWORD` – senha (default: `password`)
- `POSTGRES_DB` – database (default: `nfe_database`)

### Comportamento

- `PLAYWRIGHT_MAX_CONTEXTS` – máx. de abas Playwright em paralelo (default: `4`)
- `MAX_UPLOAD_SIZE_MB` – tamanho máximo da imagem em MB (default: `5`)
- `LOG_LEVEL` – `DEBUG`, `INFO`, `WARNING`, `ERROR` (default: `INFO`)
- `OPENCV_MODELS_DIR` – diretório dos modelos WeChat QR (default: `./opencv_models`)

## Docker (exemplo)

```bash
docker run -d \
  --name nfe-scraper \
  -p 8000:8000 \
  -e MINIO_ENDPOINT="seu-ip:9000" \
  -e MINIO_ACCESS_KEY="seu-user" \
  -e MINIO_SECRET_KEY="sua-senha" \
  -e MINIO_BUCKET_NAME="bronze" \
  -e MINIO_SECURE="false" \
  -e POSTGRES_HOST="postgres" \
  -e POSTGRES_PORT="5432" \
  -e POSTGRES_USER="user" \
  -e POSTGRES_PASSWORD="password" \
  -e POSTGRES_DB="nfe_database" \
  -e PLAYWRIGHT_MAX_CONTEXTS="4" \
  -e MAX_UPLOAD_SIZE_MB="5" \
  -e LOG_LEVEL="INFO" \
  ghcr.io/fmenegolo/nfe-scraper-api:latest
```

> No CasaOS, configure essas variáveis na seção de “Environment” do app.
