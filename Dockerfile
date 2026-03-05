FROM alpine:3.21 AS python-builder
RUN apk add --no-cache python3 py3-pip tzdata
COPY mail-sender/requirements.txt /tmp/requirements.txt
RUN pip3 install --break-system-packages -r /tmp/requirements.txt

FROM docker.n8n.io/n8nio/n8n
USER root
COPY --from=python-builder /usr/bin/python3 /usr/bin/python3
COPY --from=python-builder /usr/bin/python3.12 /usr/bin/python3.12
COPY --from=python-builder /usr/lib/python3.12 /usr/lib/python3.12
COPY --from=python-builder /usr/lib/libpython3.12.so.1.0 /usr/lib/libpython3.12.so.1.0
COPY --from=python-builder /usr/share/zoneinfo /usr/share/zoneinfo
RUN ln -sf libpython3.12.so.1.0 /usr/lib/libpython3.so && \
    mkdir -p /shared/attachments /shared/jobs && chown -R node:node /shared
USER node
