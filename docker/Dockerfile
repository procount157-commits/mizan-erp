FROM odoo:18.0

USER root

RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Required by the OCA barcode generator addons.
RUN pip3 install --no-cache-dir --break-system-packages python-barcode

# Required by OCA mis_builder, which supplies the balance sheet and profit &
# loss statements that Odoo Community does not ship at all.
RUN pip3 install --no-cache-dir --break-system-packages openupgradelib

USER odoo
