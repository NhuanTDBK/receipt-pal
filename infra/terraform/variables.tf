# ── SSH / VPS connection ────────────────────────────────────────────────────

variable "vps_host" {
  description = "Hostname or IP address of the target VPS (e.g. 'vibe-vm' from SSH config, or a public IP)"
  type        = string
  default     = "vibe-vm"
}

variable "vps_user" {
  description = "SSH user on the VPS"
  type        = string
  default     = "root"
}

variable "vps_ssh_port" {
  description = "SSH port on the VPS"
  type        = number
  default     = 22
}

variable "ssh_private_key_path" {
  description = "Path to the SSH private key used to connect to the VPS"
  type        = string
  default     = "~/.ssh/id_ed25519"
}

variable "app_dir" {
  description = "Absolute path on the VPS where the app will be deployed"
  type        = string
  default     = "/opt/receipt-pal"
}

# ── Database ─────────────────────────────────────────────────────────────────

variable "postgres_password" {
  description = "PostgreSQL password for the receipt_pal user"
  type        = string
  sensitive   = true
}

variable "postgres_db" {
  description = "PostgreSQL database name"
  type        = string
  default     = "receipt_pal"
}

variable "postgres_user" {
  description = "PostgreSQL username"
  type        = string
  default     = "receipt_pal"
}

# ── Telegram ─────────────────────────────────────────────────────────────────

variable "telegram_bot_token" {
  description = "Telegram Bot API token"
  type        = string
  sensitive   = true
}

variable "telegram_channel_id" {
  description = "Telegram channel ID or username (e.g. @receiptpal_bot)"
  type        = string
  default     = ""
}

# ── AI / LLM ─────────────────────────────────────────────────────────────────

variable "gemini_api_key" {
  description = "Google Gemini API key"
  type        = string
  sensitive   = true
}

variable "gemini_model" {
  description = "Gemini model name"
  type        = string
  default     = "gemini-2.0-flash-lite"
}

variable "openai_api_key" {
  description = "OpenAI API key (used as fallback / agents SDK)"
  type        = string
  sensitive   = true
  default     = ""
}

# ── Observability (optional) ─────────────────────────────────────────────────

variable "langfuse_public_key" {
  description = "Langfuse public key (leave empty to disable)"
  type        = string
  default     = ""
}

variable "langfuse_secret_key" {
  description = "Langfuse secret key (leave empty to disable)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "langfuse_base_url" {
  description = "Langfuse base URL"
  type        = string
  default     = "https://cloud.langfuse.com"
}

# ── Docker image / compose tuning ────────────────────────────────────────────

variable "app_image_name" {
  description = "Docker image name for the built app"
  type        = string
  default     = "receipt-pal-app"
}

variable "bot_mem_limit" {
  description = "Memory limit for the bot container"
  type        = string
  default     = "512m"
}

variable "postgres_mem_limit" {
  description = "Memory limit for postgres container"
  type        = string
  default     = "256m"
}
