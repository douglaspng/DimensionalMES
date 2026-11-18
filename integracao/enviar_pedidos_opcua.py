"""
Coletor de Pedidos Smart 4.0 Modular via OPC UA para o Dimensional MES.

Lê as tags da célula real e envia para:
https://dimensiona-mes.lovable.app/api/public/mes/pedidos

Requisitos:
    pip install asyncua requests
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import urllib.parse
from datetime import datetime, timezone
import requests
from asyncua import Client

# ==============================================================================
# 1. CONFIGURAÇÃO DA CONEXÃO
# ==============================================================================
# Endpoint OPC UA da célula Smart 4.0 (ajuste com o IP do CLP da bancada)
OPCUA_SERVER_URL = os.getenv("OPCUA_SERVER_URL", "opc.tcp://192.168.150.30:4840")

# URL do Dimensional MES e Token de Segurança
LOVABLE_URL = os.getenv("LOVABLE_URL", "https://dimensiona-mes.lovable.app").rstrip("/")
MES_INGEST_TOKEN = os.getenv("MES_INGEST_TOKEN", "")

INTERVALO_LEITURA_SEGUNDOS = 5  # frequência de varredura do CLP

# ==============================================================================
# 2. MAPEAMENTO DAS TAGS (NODE-IDS DO CLP)
# Substitua pelos NodeIDs reais obtidos no UaExpert ou documentação do CLP
# ==============================================================================
NODE_IDS = {
    # Identificação do Pedido
    "pedido_id": "ns=2;s=Smart40.Pedido.ID",              # Ex: string ou int
    "andares": "ns=2;s=Smart40.Pedido.NumAndares",        # int: 1, 2 ou 3
    "cor_bloco": "ns=2;s=Smart40.Pedido.CorBloco",        # string ou int
    "lamina_1": "ns=2;s=Smart40.Pedido.CorLamina1",       # string ou int
    "lamina_2": "ns=2;s=Smart40.Pedido.CorLamina2",       # string ou int
    "lamina_3": "ns=2;s=Smart40.Pedido.CorLamina3",       # string ou int
    "estacao_atual": "ns=2;s=Smart40.Processo.Estacao",   # int: 0 a 4

    # (Opcional) Sensores de Inspeção Real de Cor (caso a estação já tenha lido)
    "inspecao_ativa": "ns=2;s=Smart40.Inspecao.Concluida", # bool
    "insp_cor_bloco": "ns=2;s=Smart40.Inspecao.CorBloco",
    "insp_lamina_1": "ns=2;s=Smart40.Inspecao.CorLamina1",
    "insp_lamina_2": "ns=2;s=Smart40.Inspecao.CorLamina2",
    "insp_lamina_3": "ns=2;s=Smart40.Inspecao.CorLamina3",
}

# ==============================================================================
# 3. MAPEAMENTO DE CORES E ESTAÇÕES
# ==============================================================================
# Se o CLP enviar números inteiros para as cores, defina aqui a conversão:
MAPA_CORES = {
    1: "vermelho", "1": "vermelho", "vermelho": "vermelho", "red": "vermelho",
    2: "azul",     "2": "azul",     "azul": "azul",         "blue": "azul",
    3: "verde",    "3": "verde",    "verde": "verde",       "green": "verde",
    4: "amarelo",  "4": "amarelo",  "amarelo": "amarelo",   "yellow": "amarelo",
    5: "branco",   "5": "branco",   "branco": "branco",     "white": "branco",
    6: "preto",    "6": "preto",    "preto": "preto",       "black": "preto",
}

# Estações cadastradas no Dimensional MES:
# 0 = Armazém
# 1 = Processamento
# 2 = Montagem de lâminas
# 3 = Inspeção de cor
# 4 = Expedição


def normalizar_cor(valor: any) -> str:
    """Converte o código ou nome da cor para o padrão aceito pelo MES."""
    if valor is None:
        return "branco"
    chave = str(valor).strip().lower()
    return MAPA_CORES.get(chave, MAPA_CORES.get(valor, "branco"))


def enviar_pedidos_lovable(pedidos: list[dict]) -> bool:
    """Envia o lote de pedidos formatados para a API do Dimensional MES."""
    if not MES_INGEST_TOKEN:
        print("[ERRO] Variável de ambiente MES_INGEST_TOKEN não configurada!")
        return False

    url = f"{LOVABLE_URL}/api/public/mes/pedidos"
    token_encoded = urllib.parse.quote(MES_INGEST_TOKEN, safe="")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token_encoded}",
    }

    try:
        response = requests.post(url, json={"pedidos": pedidos}, headers=headers, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Pedido enviado com sucesso! Aceitos: {res_data.get('aceitos')} | Rejeitados: {res_data.get('rejeitados')}")
            return True
        else:
            print(f"[FALHA HTTP {response.status_code}]: {response.text}")
            return False
    except Exception as e:
        print(f"[ERRO DE CONEXÃO COM O MES]: {e}")
        return False


async def coletar_pedido_opcua(client: Client) -> dict | None:
    """Lê os nós configurados no servidor OPC UA da máquina."""
    try:
        # Lê cada nó do dicionário
        leituras = {}
        for campo, node_id in NODE_IDS.items():
            try:
                node = client.get_node(node_id)
                leituras[campo] = await node.read_value()
            except Exception:
                leituras[campo] = None

        pedido_id = str(leituras.get("pedido_id") or "").strip()
        if not pedido_id or pedido_id == "0":
            # Nenhum pedido em execução na bancada
            return None

        andares = int(leituras.get("andares") or 1)
        andares = max(1, min(3, andares))  # Garante entre 1 e 3

        cor_bloco = normalizar_cor(leituras.get("cor_bloco"))
        laminas = [
            normalizar_cor(leituras.get("lamina_1")),
            normalizar_cor(leituras.get("lamina_2")),
            normalizar_cor(leituras.get("lamina_3")),
        ][:andares]

        estacao = int(leituras.get("estacao_atual") or 0)
        estacao = max(0, min(4, estacao))  # Garante entre 0 e 4

        # Monta a estrutura da receita solicitada
        payload_pedido = {
            "id": pedido_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "receita": {
                "andares": andares,
                "cor_bloco": cor_bloco,
                "laminas": laminas,
            },
            "estacao": estacao,
        }

        # Se houver inspeção concluída pela estação 3/4, anexa o resultado
        if leituras.get("inspecao_ativa"):
            payload_pedido["inspecao"] = {
                "andares": andares,
                "cor_bloco": normalizar_cor(leituras.get("insp_cor_bloco")),
                "laminas": [
                    normalizar_cor(leituras.get("insp_lamina_1")),
                    normalizar_cor(leituras.get("insp_lamina_2")),
                    normalizar_cor(leituras.get("insp_lamina_3")),
                ][:andares],
            }

        return payload_pedido

    except Exception as e:
        print(f"[ERRO AO LER TAGS OPC UA]: {e}")
        return None


async def main():
    print("=" * 60)
    print("Iniciando Coletor Dimensional MES - Smart 4.0 Modular")
    print(f"OPC UA Server: {OPCUA_SERVER_URL}")
    print(f"MES Endpoint:  {LOVABLE_URL}/api/public/mes/pedidos")
    print("=" * 60)

    while True:
        try:
            print(f"Conectando ao OPC UA em {OPCUA_SERVER_URL}...")
            async with Client(url=OPCUA_SERVER_URL) as client:
                print("Conectado ao CLP com sucesso!")
                ultimo_envio = None

                while True:
                    pedido = await coletar_pedido_opcua(client)
                    if pedido:
                        # Envia ao MES e evita floods repetidos se nada mudou
                        enviar_pedidos_lovable([pedido])
                    else:
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] Aguardando pedido ativo no CLP...")

                    await asyncio.sleep(INTERVALO_LEITURA_SEGUNDOS)

        except (ConnectionRefusedError, asyncio.TimeoutError) as e:
            print(f"[FALHA DE CONEXÃO COM CLP]: Servidor indisponível ({e}). Tentando em 10s...")
            await asyncio.sleep(10)
        except Exception as e:
            print(f"[ERRO INESPERADO]: {e}. Reiniciando em 5s...")
            await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nColetor finalizado pelo operador.")