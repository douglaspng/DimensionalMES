"""Envia a telemetria do Dimensional MES para o cockpit no Lovable.

Uso (PowerShell):
    $env:LOVABLE_URL = "https://manus-to-lovable-pathway.lovable.app"
    $env:MES_INGEST_TOKEN = "o mesmo token cadastrado no Lovable"
    python .\\integracao\\enviar_lovable.py --arquivo .\\data\\telemetria.csv --intervalo 30

Lê o CSV gravado pelo pipeline (coreDimensional) e envia as últimas leituras.
Use --uma-vez para enviar só uma vez.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path

LIMITE = 60000


def ler_csv(caminho: Path) -> list[dict]:
    with caminho.open(newline="", encoding="utf-8") as arquivo:
        return list(csv.DictReader(arquivo))[-LIMITE:]


def enviar(url: str, token: str, leituras: list[dict]) -> dict:
    corpo = json.dumps({"leituras": leituras}).encode("utf-8")
    pedido = urllib.request.Request(
        url.rstrip("/") + "/api/public/mes/ingest",
        data=corpo,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + urllib.parse.quote(token, safe="")},
        method="POST",
    )
    with urllib.request.urlopen(pedido, timeout=60) as resposta:
        return json.loads(resposta.read().decode("utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arquivo", default="data/telemetria.csv")
    parser.add_argument("--intervalo", type=int, default=30, help="segundos entre envios")
    parser.add_argument("--uma-vez", action="store_true")
    args = parser.parse_args()
    url = os.environ.get("LOVABLE_URL", "https://manus-to-lovable-pathway.lovable.app")
    token = os.environ["MES_INGEST_TOKEN"]
    while True:
        try:
            print(enviar(url, token, ler_csv(Path(args.arquivo))))
        except Exception as erro:  # mantém o envio rodando
            print("Falha no envio:", erro)
        if args.uma_vez:
            break
        time.sleep(max(5, args.intervalo))


if __name__ == "__main__":
    main()
