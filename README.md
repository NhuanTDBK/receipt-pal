# receipt-pal

Vietnamese receipt parsing bot powered by Telegram + Gemini Flash AI.

**Features:**
- 📸 Photo & 📄 PDF receipt parsing with Vietnamese OCR
- ✅ Confirm/edit/cancel flow with inline keyboard
- 💰 Receipt data model: items, prices, categories, food tags
- 📊 Spending stats by category + token usage tracking
- 🌐 Delivery app support (ShopeeFood, GrabFood, etc.)
- 📱 Telegram-first interface

---

## 🚀 Deployment

### Local Development (Docker Compose)

**Prerequisites:**
- Docker + Docker Compose
- PostgreSQL (via Docker) or existing instance
- Redis (optional; defaults to in-memory FSM)

**Setup:**

```bash
# 1. Create .env file
cp backend/.env.example backend/.env
$EDITOR backend/.env  # Set TELEGRAM_BOT_TOKEN, GEMINI_API_KEY, DATABASE_URL, etc.

# 2. Build and start services
docker compose build bot
docker compose up -d

# 3. Check logs
docker compose logs -f bot
```

**After code changes:**

```bash
# Rebuild and restart (preserves RocksDB photo cache)
docker compose build bot && docker compose up -d

# Or just restart if no dependencies changed
docker compose restart bot

# View logs
docker compose logs -f bot
```

### Production Deployment (VPS via Terraform)

The Terraform configuration in `infra/terraform/` deploys the full stack to any
SSH-accessible VPS.

**Prerequisites:**
- [Terraform](https://developer.hashicorp.com/terraform/install) ≥ 1.6
- `rsync` installed locally
- SSH access to the VPS (default: `vibe-vm` in SSH config or `/etc/hosts`)

**First-time setup:**

```bash
cd infra/terraform

# Copy and fill in your deployment config + secrets
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars

# Initialize and deploy
terraform init
terraform apply
```

Terraform will:
1. Install Docker (CE + Compose plugin) on the VPS if not present
2. Rsync `docker-compose.yml` and `backend/` source to `/opt/receipt-pal/`
3. Generate `.env` from your `terraform.tfvars` (secrets encrypted, never stored locally)
4. Run migrations and start the bot

**After code changes (e.g., after merging to `main`):**

```bash
# Push changes to origin first
git push origin main
git push origin --tags

# From infra/terraform/
terraform apply          # Auto-detects source changes and redeploys
```

**Manual deployment (if Terraform provisioning fails):**

```bash
# SSH into VPS
ssh -i ~/.ssh/id_rsa root@<VPS_IP>

# Navigate to app directory
cd /opt/receipt-pal

# Manually run deploy script
bash infra/terraform/scripts/deploy-receipt-pal.sh
```

**Useful commands:**

```bash
# SSH into VPS (using Terraform output)
cd infra/terraform
$(terraform output -raw ssh_command)

# Tail bot logs on VPS
$(terraform output -raw ssh_command) 'cd /opt/receipt-pal && docker compose logs -f bot'

# Check running containers on VPS
$(terraform output -raw ssh_command) 'cd /opt/receipt-pal && docker compose ps'

# Restart bot on VPS
$(terraform output -raw ssh_command) 'cd /opt/receipt-pal && docker compose restart bot'
```

---

## ✅ Testing

The backend test suite now lives under `backend/tests/` and is split into three layers:

- deterministic unit and smoke tests for doubles, handlers, generators, and runner wiring
- PostgreSQL-backed integration tests for search, analytics, and persistence helpers
- opt-in real-LLM verification tests that stay skipped unless explicitly enabled

Sample receipt fixtures are reused from `data/receipts/*.json`, and synthetic receipts are generated from `backend/tests/generators/`.

### Fast default run

Run the backend suite with skips for anything that needs extra services or real API access:

```bash
cd backend
pytest -q
```

This runs the deterministic tests immediately. Database-backed tests are skipped if the test database is unavailable. Real-LLM tests are always skipped unless opted in.

### PostgreSQL-backed integration tests

Point tests at a dedicated PostgreSQL database before running DB-backed coverage:

```bash
cd backend
export TEST_DATABASE_URL='postgresql+asyncpg://receipt_pal:receipt_pal@localhost:5432/receipt_pal_test'
pytest -q -m database
```

The suite creates missing tables automatically and truncates mapped tables between tests. Do not point `TEST_DATABASE_URL` at a non-test database.

### Opt-in real LLM verification

Real-model verification is intentionally off by default. Enable it only when you want to validate behavior against the live provider:

```bash
cd backend
export TEST_DATABASE_URL='postgresql+asyncpg://receipt_pal:receipt_pal@localhost:5432/receipt_pal_test'
export RUN_REAL_LLM_TESTS=1
export GEMINI_API_KEY='<real-key>'
pytest -q -m real_llm
```

Notes:

- If you use `GEMINI_API_KEY`, the test harness maps it through the OpenAI-compatible settings used by the app.
- Real-LLM tests are behavior-based, not exact-text snapshots. They check stable outcomes like parsed totals, merchant mentions, and category coverage.
- Expect these tests to be slower and potentially more variable than the deterministic suite.

## 📝 Versioning & Releases

Releases are tagged as `v<major>.<minor>.<patch>` on `main` branch.

**Creating a release:**

```bash
# Update CHANGELOG.md with changes
$EDITOR CHANGELOG.md

# Commit
git add CHANGELOG.md
git commit -m "chore: update CHANGELOG for v1.0.X"

# Create annotated tag (automatically triggers deployment via Terraform)
git tag -a v1.0.X -m "v1.0.X: <description>"

# Push commit + tag
git push origin main
git push origin v1.0.X

# Deploy via Terraform
cd infra/terraform
terraform apply
```

See [CHANGELOG.md](CHANGELOG.md) for version history.
