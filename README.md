# receipt-pal
Receipt Free Hand

## Deploy to VPS via Terraform

The Terraform configuration in `infra/terraform/` deploys the full stack to any
SSH-accessible VPS (the default target is `vibe-vm` from your SSH config).

### Prerequisites
- [Terraform](https://developer.hashicorp.com/terraform/install) ≥ 1.6
- `rsync` installed locally
- SSH access to the VPS (`vibe-vm` resolvable via `~/.ssh/config` or `/etc/hosts`)

### First-time setup

```bash
cd infra/terraform

# Copy and fill in your secrets
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars

terraform init
terraform apply
```

Terraform will:
1. Install Docker (CE + Compose plugin) on the VPS if not already present
2. Rsync `docker-compose.yml` and `backend/` source to `/opt/receipt-pal/`
3. Write `.env` files from your `terraform.tfvars` (secrets never touch disk locally)
4. Run `docker compose build && docker compose up -d`

### Re-deploy after code changes

```bash
terraform apply          # detects source changes via content hash
```

### Useful one-liners

```bash
# SSH into the VPS
$(terraform output -raw ssh_command)

# Tail bot logs
$(terraform output -raw ssh_command) 'cd /opt/receipt-pal && docker compose logs -f bot'
```
