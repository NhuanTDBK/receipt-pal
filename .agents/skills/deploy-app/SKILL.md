---
name: deploy-app
description: Deploy receipt-pal to production VPS with changelog notes
---

# deploy-app Skill

Automates the full release cycle: commit → tag → CHANGELOG → push → VPS deploy.

## Steps

### 0. Prepare
- run `ruff check .` and `black .` to ensure code quality and formatting
- run `ruff format .` to auto-fix any issues

### 1. Verify readiness
- Must be on `main` branch with changes committed
- Check latest tag: `git tag --sort=-version:refname | head -3`
- Determine next version (`vX.Y.Z` — patch for fixes, minor for features)

### 2. Update CHANGELOG.md
- Add a new `## [vX.Y.Z] — YYYY-MM-DD` section at the top
- Include only non-empty sections: `### Added`, `### Changed`, `### Fixed`, `### Removed`
- Reference story spec if exists: `docs/stories/<story-file>.md`
- Commit: `git add CHANGELOG.md && git commit -m "chore: update CHANGELOG for vX.Y.Z ..."`

### 3. Create annotated tag on `main`
```bash
git tag -a vX.Y.Z -m "vX.Y.Z: <one-line summary>

- key change 1
- key change 2"
```

### 4. Push to remote
```bash
git push origin main && git push origin vX.Y.Z
```

### 5. Deploy to VPS via Terraform
Pick tag in the context of the deploy command, e.g. `deploy-app vX.Y.Z`. This will update the Terraform config to deploy the specified version.
IF not mentioned, it defaults to the latest tag.
<!-- ```bash
cd infra/terraform
terraform plan -lock=false -out=tfplan
terraform apply -lock=false "tfplan"
```

> **Why `-lock=false`?** The local state backend on macOS can leave a stale
> `.terraform.tfstate.lock.info` after a crashed session. Since only one operator
> runs deploys, skipping the lock is safe. Delete any stale lock file first:
> `rm -f infra/terraform/.terraform.tfstate.lock.info`

**Fallback — -->
 Manual SSH (if Terraform is broken):**
```bash
ssh -i ~/.ssh/id_rsa root@<VPS_IP> \
  "cd /opt/receipt-pal && git pull && bash infra/terraform/scripts/deploy-receipt-pal.sh"
```

### 6. Verify
```bash
ssh -i ~/.ssh/id_rsa root@<VPS_IP> \
  "cd /opt/receipt-pal && docker compose logs --tail=30 bot"
```

Bot is healthy when logs show `Run polling for bot @receiptpal_bot`.
