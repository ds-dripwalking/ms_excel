# Excel Marketplace Service — Project Knowledge Graph

## 🎯 CRITICAL RULE: Always Query Graph Before Reading Files

This project uses **Graphify knowledge graph** (`graphify-out/graph.json`) as the **primary source of truth** for architecture, component relationships, and code structure.

### ⚠️ Mandatory Workflow

**BEFORE** reading any source files, **ALWAYS** execute these commands via bash:

```bash
# 1. Explain specific component
graphify explain "<component_id>"

# 2. Search by concept (English only!)
graphify query "<concept>"

# 3. Trace connections between components
graphify path "<component_1>" "<component_2>"
```

**Why?** This saves 70-90% tokens. The graph contains 770 nodes and 1433 edges representing the entire project structure.

---

## 📁 Project Structure

### Backend (FastAPI + Python + Celery)
```
backend/
├── app/
│   ├── api/              # REST endpoints
│   ├── services/         # Business logic
│   │   ├── moysklad/    # МойСклад API integration
│   │   ├── channels/    # Storage adapters (S3, Yandex Disk)
│   │   └── jwt/         # JWT authentication
│   ├── models/           # SQLAlchemy models
│   ├── schemas/          # Pydantic schemas
│   ├── crypto/           # Encryption utilities
│   └── core/             # Core utilities
├── tests/                # pytest tests
└── alembic/              # Database migrations
```

### Frontend (Vue3 + TypeScript)
```
frontend/
├── src/
│   ├── components/       # Vue components
│   ├── views/            # Page views
│   ├── stores/           # Pinia stores
│   └── composables/      # Vue composables
├── package.json          # Dependencies (Vue, Pinia, PrimeVue)
└── tsconfig.json         # TypeScript config
```

### Infrastructure
```
nginx/                    # Nginx configuration
docker-compose.yml        # Docker orchestration
Makefile                  # Build commands
docs/                     # Documentation
```

---

## 🔑 Key Components

### МойСклад Integration
- **API Client**: `backend_app_services_moysklad_api_client_moyskladclient`
- **Errors**: `MoyskladAPIError`, `MoyskladRateLimitError`, `MoyskladUnauthorizedError`
- **Models**: `backend_app_models_vendor_moyskladaccount`, `backend_app_models_vendor_moyskladtoken`
- **Rate Limiting**: `_rate_limit_wait()`

### Storage Channels (S3/Yandex Disk)
- **Base Adapter**: `backend_app_services_channels_base_basestorageadapter`
- **S3 Objects**: `backend_app_services_channels_s3_compatible_s3object`
- **Yandex Disk**: `backend_app_services_channels_yandex_disk_yandexdiskerror`
- **Common Errors**: `StorageError`, `AuthError`, `QuotaExceededError`

### Authentication & Security
- **JWT Validation**: `backend_app_services_jwt_auth_jwtvalidationerror`
- **Secret Management**: `backend_app_crypto_secretstr`
- **Account Status**: `backend_app_models_vendor_accountstatus`

### Excel Export Core Functions
- `_build_product_row()` — Build Excel row from product data
- `_extract_custom_fields()` — Extract custom fields from МойСклад
- `_get_assortment()` — Fetch product assortment
- `_get_stock_data()` — Get stock levels
- `_get_price_types()` — Fetch price types
- `_create_file()` — Create Excel file

### Celery Tasks (Background Jobs)
- TODO: Task scheduler implementation
- TODO: Rate limiting for МойСклад API
- TODO: Background Excel generation

---

## 📊 Graphify Command Reference

### Basic Commands

| Purpose | Command |
|---------|---------|
| Explain component | `graphify explain "backend_app_services_moysklad_api_client_moyskladclient"` |
| Search concept | `graphify query "moysklad"` |
| Find path | `graphify path "backend_app_services_moysklad_api_client_moyskladclient" "backend_app_models_vendor_moyskladaccount"` |
| Update graph | `graphify update .` |
| Force rebuild | `graphify extract . --code-only --force` |

### Advanced Commands

```bash
# Get all МойСклад-related components
graphify query "moysklad"

# Find storage adapters
graphify query "storage adapter"

# Explain rate limiting
graphify explain "_rate_limit_wait"

# Find Excel export flow
graphify path "_get_assortment" "_create_file"

# Re-cluster communities
graphify cluster-only .
```

### Example Workflow

**Task**: Understand how Excel export from МойСклад works

**Step 1** — Query the graph:
```bash
graphify explain "backend_app_services_moysklad_api_client_moyskladclient"
graphify query "excel export"
graphify path "_get_assortment" "_build_product_row"
```

**Step 2** — Read only the relevant files based on graph results:
- `backend/app/services/moysklad/api_client.py` (API integration)
- `backend/app/services/channels/base.py` (storage adapter)
- Core Excel generation functions

**Step 3** — Implement changes with full context.

---

## 🚀 Development Commands

### Backend
```bash
cd backend
python -m pytest tests/                    # Run tests
python -m uvicorn app.main:app --reload    # Start dev server
alembic upgrade head                       # Apply migrations
celery -A app.celery worker --loglevel=info  # Start Celery worker
```

### Frontend
```bash
cd frontend
npm install
npm run dev                                # Start dev server (Vite)
npm run build                              # Build for production
npm run type-check                         # TypeScript validation
```

### Docker
```bash
docker-compose up -d                       # Start all services
docker-compose down                        # Stop all services
docker-compose logs -f backend            # View backend logs
```

### Make Commands
```bash
make help                                  # Show available commands
make build                                 # Build Docker images
make test                                  # Run all tests
make migrate                               # Run database migrations
```

---

## 💡 Token-Saving Rules

### ✅ DO
- Query the graph **first** before reading files
- Use `graphify explain` for understanding individual components
- Use `graphify path` to trace relationships
- Read `graphify-out/GRAPH_REPORT.md` for architecture overview
- Open `graphify-out/graph.html` for visual exploration

### ❌ DON'T
- Read entire directories without querying the graph first
- Use generic searches like "find all МойСклад code"
- Ignore the graph and read files sequentially
- Ask models to "read all files in backend/"

---

## 🔄 Auto-Update System

The graph updates automatically via Git hooks:

| Git Action | Graphify Action |
|------------|----------------|
| `git commit` | Rebuilds affected parts |
| `git checkout` | Rebuilds for new branch |
| `git pull` | **Manual**: run `graphify update .` |

### Recommended Alias
```bash
git config --global alias.gpull '!git pull && graphify update .'
```

Now `git gpull` pulls and updates the graph in one command.

---

## 📂 Important Files

| File | Purpose |
|------|---------|
| `graphify-out/graph.json` | Complete knowledge graph |
| `graphify-out/GRAPH_REPORT.md` | Architecture report |
| `graphify-out/graph.html` | Interactive visualization |
| `graphify-out/manifest.json` | File metadata |
| `.graphifyignore` | Files to exclude from graph |
| `docker-compose.yml` | Docker orchestration |
| `Makefile` | Build automation |

---

## 🛠 Troubleshooting

### Graph query returns "No matching nodes found"
- Use **English** for queries (node labels are in English)
- Try exact component IDs: `graphify explain "backend_app_services_moysklad_api_client_moyskladclient"`
- Check available nodes: `python3 -c "import json; g=json.load(open('graphify-out/graph.json')); [print(n['id']) for n in g['nodes'][:20]]"`

### Graph is outdated
```bash
graphify update . --force
```

### Need to rebuild from scratch
```bash
graphify extract . --code-only --force
graphify cluster-only .
```

### МойСклад API rate limiting
- Check `_rate_limit_wait()` implementation
- Review `MoyskladRateLimitError` handling
- Verify Celery task configuration

---

## 📚 Resources

- **Full Graph Report**: `graphify-out/GRAPH_REPORT.md`
- **Visual Graph**: Open `graphify-out/graph.html` in browser
- **МойСклад API Docs**: https://dev.moysklad.ru/doc/api/remap/1.2/
- **Graphify Docs**: https://github.com/Graphify-Labs/graphify
- **Freebuff Docs**: https://freebuff.com

---

## 🎯 Summary

**Before ANY code changes:**
1. Query the graph: `graphify explain` / `graphify query` / `graphify path`
2. Read only the files the graph points to
3. Make changes with full architectural context

**Result**: 70-90% token savings + better understanding of МойСклад integration, storage channels, and Excel export flow.
