FROM odoo:18.0

USER root

RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

USER odoo
