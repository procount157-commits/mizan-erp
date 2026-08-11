# Mizan ERP — ميزان ERP

A professional, commercial ERP system built on **Odoo 18 Community**, targeting the UAE market and Arabic-speaking businesses.

---

## Architecture

| Component | Technology |
|---|---|
| ERP Engine | Odoo 18 Community |
| Database | PostgreSQL 16 |
| Container | Docker / Docker Compose |
| Custom Layer | `custom_addons/mizan_core` |
| Third-party | `third_party/OCA/` |

---

## Directory Structure

```
Mizan-ERP/
├── odoo/                    # Odoo 18 Community source (upstream, do not modify)
├── custom_addons/
│   └── mizan_core/          # Mizan custom module
│       ├── __init__.py
│       ├── __manifest__.py
│       ├── models/
│       │   └── models.py    # MizanContact, MizanTax, MizanInvoice, MizanInvoiceLine
│       ├── views/
│       │   └── views.xml    # List/form views + menus
│       ├── security/
│       │   └── ir.model.access.csv
│       └── controllers/     # Reserved for future HTTP routes
├── docker/
│   ├── Dockerfile           # FROM odoo:18.0 + git
│   ├── docker-compose.yml   # Odoo + PostgreSQL 16 services
│   └── odoo.conf            # Odoo configuration
├── third_party/
│   └── OCA/                 # OCA community addons (mounted at /mnt/oca_addons)
└── README.md
```

---

## mizan_core — Current Functionality

The `mizan_core` module provides the foundation of the Mizan ERP custom layer.

### Models

| Model | Technical Name | Description |
|---|---|---|
| Mizan Contact | `mizan.contact` | Customers, vendors, or both |
| Mizan Tax | `mizan.tax` | Output/Input VAT definitions |
| Mizan Invoice | `mizan.invoice` | Sales and purchase invoices |
| Mizan Invoice Line | `mizan.invoice.line` | Invoice line items |

### Menus

- **Mizan** (top-level)
  - Accounting → Invoices
  - Contacts
  - Taxes

---

## Docker Setup (Recommended)

### Prerequisites

- Docker Desktop (macOS ARM64 or Linux)
- Docker Compose v2

### First-time setup

```bash
cp docker/.env.example docker/.env
# Edit docker/.env and set a strong POSTGRES_PASSWORD
```

### Start

```bash
cd docker
docker compose up -d
```

Odoo will be available at: **http://localhost:8069**

### Stop

```bash
cd docker
docker compose down
```

### Rebuild after Dockerfile changes

```bash
cd docker
docker compose build --no-cache
docker compose up -d
```

### Container names

| Container | Service |
|---|---|
| `mizan-odoo` | Odoo 18 |
| `mizan-db` | PostgreSQL 16 |

---

## Install / Update mizan_core

### First install

```bash
docker exec mizan-odoo odoo -d mizan_dev -i mizan_core --stop-after-init
```

### Update after code changes

```bash
docker exec mizan-odoo odoo -d mizan_dev -u mizan_core --stop-after-init
```

Then restart Odoo:

```bash
cd docker
docker compose restart odoo
```

---

## Odoo Configuration

Configuration is at `docker/odoo.conf`.

| Setting | Value |
|---|---|
| `db_host` | `db` (internal Compose service name) |
| `db_port` | `5432` |
| `db_user` | set via `POSTGRES_USER` in `docker/.env` (default: `odoo`) |
| `db_password` | set via `POSTGRES_PASSWORD` in `docker/.env` — never stored in config |
| `addons_path` | `/opt/odoo/addons, /mnt/custom_addons, /mnt/oca_addons` |
| `data_dir` | `/var/lib/odoo` |
| `proxy_mode` | `False` — set to `True` only when behind a trusted reverse proxy |

---

## Development Rules

1. **Do NOT modify `odoo/`** — treat it as upstream vendor code
2. All custom functionality goes into `custom_addons/`
3. OCA modules go into `third_party/OCA/`
4. Use Odoo ORM; avoid raw SQL unless necessary
5. Do not introduce AI dependencies
6. Follow Odoo 18 module conventions
7. Keep all models in `custom_addons/mizan_core/` until the scope warrants splitting

---

## Git Workflow

```bash
# Check state before starting work
git status
git log --oneline -5

# After making changes
git add custom_addons/
git commit -m "feat: describe your change"
git push origin main
```

**Never force-push to `main`.**

---

## Roadmap (not yet implemented)

- UAE VAT support
- Corporate Tax support
- Chart of Accounts
- General Ledger / Trial Balance
- Multi-company
- User roles and permissions
- Arabic localization
