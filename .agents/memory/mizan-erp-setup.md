---
name: Mizan ERP project setup
description: Architecture decisions and run commands for the Mizan ERP Odoo 18 project
---

# Mizan ERP Project Setup

## What it is
Commercial ERP/SaaS product built on Odoo 18 Community. NOT an AI product.
Arabic brand: ميزان ERP. Target market: UAE accounting/ERP.

## Non-negotiable rules
- Do NOT modify `odoo/` core — treat as upstream vendor code
- All custom code in `custom_addons/` as Odoo modules
- Database: PostgreSQL 16 only
- No AI features, LLMs, or AI agents
- Docker is the canonical runtime; docker-compose in `docker/`

## Docker networking
Standard Compose network (NOT network_mode: host).
`db_host = db` (Compose service name). PostgreSQL NOT published on host.
Odoo exposed on host port 8069 only.

**Why:** host networking removes container isolation and doesn't work consistently on macOS Docker Desktop.

## Credentials policy
DB credentials come exclusively from `docker/.env` (gitignored).
`docker/.env.example` is committed as a template.
`db_user` and `db_password` passed to Odoo at runtime via CLI args (`--db_user`, `--db_password`), NOT stored in `odoo.conf`.

**Why:** prevents credential leakage in source control.

## proxy_mode
Set to False by default. Only enable in `odoo.conf` when Odoo is behind a trusted reverse proxy (nginx, Caddy).

**Why:** when directly on port 8069, proxy_mode causes Odoo to trust forwarded headers from any caller.

## mizan_core models
- `mizan.contact` — customers/vendors, with tax number field
- `mizan.tax` — VAT rate definitions (output/input)
- `mizan.invoice` — sales/purchase invoices, draft/posted/cancelled states
- `mizan.invoice.line` — computed subtotal/tax_amount/total; tax_amount string is "Tax Amount" (not "Tax")

## Run commands
```
cp docker/.env.example docker/.env  # first time only
cd docker && docker compose up -d
docker exec mizan-odoo odoo -d mizan_dev -i mizan_core --stop-after-init
docker exec mizan-odoo odoo -d mizan_dev -u mizan_core --stop-after-init
```
