FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends iptables netcat-openbsd && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/plugin
COPY run_tool.py /opt/plugin/run_tool.py
COPY plugin.py /opt/plugin/plugin.py
RUN chmod +x /opt/plugin/run_tool.py
