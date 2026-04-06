FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends iptables dnsutils && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/plugin
COPY run_tool.py /opt/plugin/run_tool.py
COPY plugin.py /opt/plugin/plugin.py
RUN chmod 0555 /opt/plugin/run_tool.py /opt/plugin/plugin.py
