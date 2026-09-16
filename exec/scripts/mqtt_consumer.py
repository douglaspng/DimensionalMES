from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dimensional_mes import AppConfig, DimensionalMES


def main() -> None:
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise SystemExit("Instale as dependências com: pip install -r requirements.txt") from exc

    root = Path(__file__).resolve().parents[1]
    app = DimensionalMES(AppConfig.load(root / "config.json"))
    host = os.getenv("MQTT_HOST", "localhost")
    port = int(os.getenv("MQTT_PORT", "1883"))
    topic = os.getenv("MQTT_TOPIC", "dimensional-mes/machine/telemetry")

    def on_connect(client, userdata, flags, reason_code, properties=None):
        print(f"MQTT conectado: {reason_code}")
        client.subscribe(topic)

    def on_message(client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            result = app.ingest(payload)
            if not result["accepted"]:
                print(f"Leitura rejeitada: {result['reason']}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            print(f"Mensagem MQTT inválida: {exc}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, 60)
    print(f"Aguardando mensagens em {topic} ({host}:{port})")
    client.loop_forever()


if __name__ == "__main__":
    main()
