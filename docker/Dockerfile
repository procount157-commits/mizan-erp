# Pinned to the build the client databases were created on: "18.0" alone
# pulls whatever nightly is current, and a newer build on an older database
# is how a field the code expects turns out not to exist.
FROM odoo:18.0-20260908

USER root

RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Required by the OCA barcode generator addons.
RUN pip3 install --no-cache-dir --break-system-packages python-barcode

# Required by OCA mis_builder, which supplies the balance sheet and profit &
# loss statements that Odoo Community does not ship at all.
RUN pip3 install --no-cache-dir --break-system-packages openupgradelib

# HTTP/2 for Apple's push service (mizan_mobile): APNs speaks nothing else.
# anyio pinned: newer ones demand a typing_extensions above the one Debian
# installed, and pip cannot replace a Debian package.
RUN pip3 install --no-cache-dir --break-system-packages "httpx[http2]==0.28.1" "anyio==4.4.0"

USER odoo
