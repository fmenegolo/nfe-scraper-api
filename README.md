# 🛰️ NFe Scraper API (Vision AI & Data Ingestion)
API de alta performance desenvolvida com FastAPI para automação do ciclo de vida de Notas Fiscais Eletrônicas (NFe). O sistema realiza desde a decodificação de imagens de baixa qualidade via Visão Computacional até a persistência em ambientes de Data Lake (MinIO) e Bancos de Dados (PostgreSQL).
🧠 Diferenciais Técnicos

### 1. **Visão Computacional Híbrida**
- A API utiliza uma abordagem de duas camadas para garantir a leitura do QR Code, mesmo em fotos tremidas ou com iluminação ruim (comum em envios via Telegram/WhatsApp):
    - Camada de Ataque (WeChatQR): Utiliza o detector da engine do WeChat (OpenCV Contrib) baseado em Redes Neurais para localizar QR Codes complexos.
    - Camada de Defesa (PyZbar + Filtros): Se a IA falhar, o sistema aplica 9 variantes de filtros (CLAHE, Otsu Thresholding, Sharpening, Gaussian Blur) para tentar "limpar" a imagem antes da decodificação.


### 2. **Singleton Browser Management**
- Diferente de scrapers comuns que abrem e fecham o navegador a cada requisição, esta API utiliza o Playwright com um Singleton Browser Manager:
    - O navegador é lançado apenas uma vez no startup da API (Lifespan).
    - Cada nota fiscal abre apenas um novo Browser Context (aba anônima), reduzindo drasticamente o uso de CPU e RAM no servidor.

### 3. **Organização Automática em Data Lake (S3)**
- O sistema extrai a chave de 44 dígitos da nota para organizar os arquivos no MinIO seguindo uma estrutura de pastas lógica:
    - bronze/qrcode/{ano}/{mes}/{chave}.html

### 4. **Arquitetura de Dados (Medallion System)**
A API já realiza o pré-processamento seguindo as melhores práticas de Data Engineering:
🥉 Camada Bronze (Raw): O HTML original é persistido no MinIO e os metadados (chave de acesso, timestamp, origem) são registrados no PostgreSQL via asyncpg. O uso de ON CONFLICT garante a idempotência dos dados (sem duplicidade).
🥈 Camada Silver (Refined): Um parser robusto em BeautifulSoup4 extrai:
Dados do estabelecimento (CNPJ, Endereço).
Totais da nota (Valor bruto, descontos, troco, método de pagamento).
Itens detalhados (Nome, Qtd, Unidade, Valor Unitário).
🧪 Validação de Integridade: O sistema calcula a soma real dos itens e compara com o valor total da SEFAZ (calculated_items_total vs gross_value), sinalizando qualquer discrepância de arredondamento ou leitura.

### 5. **Resiliência e Parsing**
Regex-Driven Extraction: Extração de número, série e data de emissão via expressões regulares diretamente do bloco de informações da nota.
Normalização Monetária: Tratamento automático de separadores decimais e de milhar brasileiros para conversão em float (padrão SQL/Python).
Fallback de Chave: Em caso de falha na leitura da chave de 44 dígitos, o sistema utiliza um sistema de pastas cronológico baseado na data de ingestão para garantir que nenhum dado seja perdido.

##🛠️ Stack Tecnológica
Backend: Python 3.10 / FastAPI / Uvicorn.
Vision: OpenCV (WeChatQR Model) & PyZbar.
Crawler: Playwright (Chromium Headless).
Storage: MinIO (S3 Compatible) & PostgreSQL (via asyncpg).
Parsing: BeautifulSoup4 (LXML).

###🏗️ Estrutura do Projeto
```text
.
├── main.py              # Coração da API e Lógica de Processamento
├── Dockerfile           # Receita para build da imagem (Playwright + OpenCV)
├── requirements.txt     # Dependências fixadas para estabilidade
├── opencv_models/       # Modelos Prototxt e Caffemodel do WeChatQR
└── .github/workflows/   # CI/CD: Build automático para ghcr.io
```

##🚀 Como Rodar
Via Docker (Recomendado)
A imagem está consolidada e disponível via GitHub Container Registry:
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
    -e OPENCV_MODELS_DIR="/app/opencv_models" \
    ghcr.io/fmenegolo/nfe-scraper-api:latest
```

### Variáveis de Ambiente

Obrigatórias/relevantes para produção (todas lidas em `main.py` via `os.getenv`):

- `MINIO_ENDPOINT` – endpoint do MinIO (ex.: `minio:9000` ou `seu-ip:9000`).
- `MINIO_ACCESS_KEY` – usuário de acesso ao MinIO.
- `MINIO_SECRET_KEY` – senha/chave de acesso ao MinIO.
- `MINIO_BUCKET_NAME` – bucket onde o HTML bruto será salvo (default: `bronze`).
- `MINIO_SECURE` – `true` se usar HTTPS no MinIO, `false` caso contrário (default: `false`).
- `POSTGRES_HOST` – host ou service name do PostgreSQL (default: `localhost`).
- `POSTGRES_PORT` – porta do PostgreSQL (default: `5432`).
- `POSTGRES_USER` – usuário do banco (default: `user`).
- `POSTGRES_PASSWORD` – senha do banco (default: `password`).
- `POSTGRES_DB` – nome do database (default: `nfe_database`).

Variáveis adicionais de comportamento:

- `PLAYWRIGHT_MAX_CONTEXTS` – número máximo de contextos/abas Playwright em paralelo (default: `4`).
- `MAX_UPLOAD_SIZE_MB` – tamanho máximo permitido para upload de imagens em MB (default: `5`).
- `LOG_LEVEL` – nível de log (`DEBUG`, `INFO`, `WARNING`, `ERROR`) (default: `INFO`).
- `OPENCV_MODELS_DIR` – diretório onde estão os modelos WeChat QR (`detect.prototxt`, etc.). Default: pasta `opencv_models` ao lado do `main.py` (no container, `/app/opencv_models`).

### 🔌 Endpoints Principais

- `POST /ingest/` – Recebe uma imagem (UploadFile), decodifica o QR Code, faz o scraping na SEFAZ, salva o HTML bruto no MinIO (camada Bronze) e registra metadados no Postgres. Também retorna um payload já parseado (camada Silver) com itens e totais.
- `GET /` – Endpoint de healthcheck simples, retorna `{ "status": "online" }`.

#### ⚖️ Licença e Uso
Desenvolvido para fins de Engenharia de Dados. O uso deste software deve respeitar os termos de serviço dos portais da SEFAZ.
