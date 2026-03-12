terraform {
  required_version = ">= 1.6"
  required_providers {
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

locals {
  repo_root = "${path.module}/../.."

  # Re-deploy whenever docker-compose or any backend source file changes.
  source_hash = sha256(join("", [
    filesha256("${local.repo_root}/docker-compose.yml"),
    sha256(join("", [for f in sort(fileset("${local.repo_root}/backend", "**")) :
      try(filesha256("${local.repo_root}/backend/${f}"), "")
      if !can(regex("(\\.pyc|__pycache__|/\\.venv/|\\.egg-info)", f))
    ])),
  ]))

  # Root-level .env consumed by docker-compose variable interpolation.
  compose_env = <<-EOT
    POSTGRES_PASSWORD=${var.postgres_password}
    POSTGRES_DB=${var.postgres_db}
    POSTGRES_USER=${var.postgres_user}
    APP_IMAGE_NAME=${var.app_image_name}
    BOT_MEM_LIMIT=${var.bot_mem_limit}
    RESTART_POLICY=unless-stopped
  EOT

  # backend/.env consumed by the Python app via pydantic-settings.
  app_env = <<-EOT
    DATABASE_URL=postgresql+asyncpg://${var.postgres_user}:${var.postgres_password}@host.docker.internal:5432/${var.postgres_db}
    REDIS_URL=redis://redis:6379
    TELEGRAM_BOT_TOKEN=${var.telegram_bot_token}
    TELEGRAM_CHANNEL_ID=${var.telegram_channel_id}
    GEMINI_API_KEY=${var.gemini_api_key}
    MODEL=${var.gemini_model}
    OPENAI_API_KEY=${var.openai_api_key}
    OPENAI_AGENTS_DISABLE_TRACING=1
    LANGFUSE_PUBLIC_KEY=${var.langfuse_public_key}
    LANGFUSE_SECRET_KEY=${var.langfuse_secret_key}
    LANGFUSE_BASE_URL=${var.langfuse_base_url}
  EOT

  ssh_opts = "-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -p ${var.vps_ssh_port} -i ${pathexpand(var.ssh_private_key_path)}"
}

# ── 1. Sync source code to the VPS ───────────────────────────────────────────

resource "null_resource" "sync_source" {

  triggers = {
    source_hash = local.source_hash
  }

  # Create app directory
  connection {
    type        = "ssh"
    host        = var.vps_host
    user        = var.vps_user
    port        = var.vps_ssh_port
    private_key = file(pathexpand(var.ssh_private_key_path))
  }

  provisioner "remote-exec" {
    inline = ["mkdir -p ${var.app_dir}/backend"]
  }

  # Rsync docker-compose.yml
  provisioner "local-exec" {
    command = <<-EOT
      rsync -az ${local.ssh_opts} \
        ${local.repo_root}/docker-compose.yml \
        ${var.vps_user}@${var.vps_host}:${var.app_dir}/
    EOT
  }

  # Rsync backend source (exclude build artifacts and secrets)
  provisioner "local-exec" {
    command = <<-EOT
      rsync -az --delete \
        --exclude='.venv/' \
        --exclude='__pycache__/' \
        --exclude='*.pyc' \
        --exclude='.env' \
        --exclude='*.egg-info/' \
        --exclude='.pytest_cache/' \
        --exclude='dist/' \
        ${local.ssh_opts} \
        ${local.repo_root}/backend/ \
        ${var.vps_user}@${var.vps_host}:${var.app_dir}/backend/
    EOT
  }
}

# ── 2. Write .env files and deploy ───────────────────────────────────────────

resource "null_resource" "deploy" {
  depends_on = [null_resource.sync_source]

  triggers = {
    source_hash = local.source_hash
    # Also redeploy if any secret changes.
    config_hash = sha256(join("", [local.compose_env, local.app_env]))
  }

  connection {
    type        = "ssh"
    host        = var.vps_host
    user        = var.vps_user
    port        = var.vps_ssh_port
    private_key = file(pathexpand(var.ssh_private_key_path))
  }

  # Write root .env for docker-compose variable substitution
  provisioner "remote-exec" {
    inline = [
      "cat > ${var.app_dir}/.env << 'ENVEOF'",
      "${local.compose_env}",
      "ENVEOF",
    ]
  }

  # Write backend/.env for pydantic-settings
  provisioner "remote-exec" {
    inline = [
      "cat > ${var.app_dir}/backend/.env << 'ENVEOF'",
      "${local.app_env}",
      "ENVEOF",
    ]
  }

  # Build and start the stack
  provisioner "remote-exec" {
    inline = [
      "cd ${var.app_dir}",
      "docker compose build --pull",
      "docker compose up -d --remove-orphans",
      "docker compose ps",
    ]
  }
}
