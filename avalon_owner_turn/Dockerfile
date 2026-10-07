FROM python@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /opt/avalon-owner-turn
COPY payload /opt/avalon-owner-turn/payload
COPY runner.py /opt/avalon-owner-turn/runner.py
LABEL io.hass.version="1.0.0" io.hass.type="app" io.hass.arch="aarch64" \
      org.opencontainers.image.title="Avalon temporary OwnerTurn update" \
      avalon.scope="operator-only-one-shot"
ENTRYPOINT ["/usr/local/bin/python3", "-I", "-B", "/opt/avalon-owner-turn/runner.py"]
