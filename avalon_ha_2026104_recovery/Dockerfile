FROM python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/avalon-ha-recovery
COPY payload /opt/avalon-ha-recovery/payload
COPY runner.py /opt/avalon-ha-recovery/runner.py
LABEL io.hass.version="1.0.0" io.hass.type="app" io.hass.arch="aarch64" \
      org.opencontainers.image.title="Avalon temporary HA 2026.10.4 recovery" \
      avalon.scope="operator-only-one-shot"
ENTRYPOINT ["/usr/local/bin/python3", "-I", "-B", "/opt/avalon-ha-recovery/runner.py"]
