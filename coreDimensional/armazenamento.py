from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


CAMPOS_TELEMETRIA = [
    "timestamp", "source_timestamp", "machine_id", "node_id", "variable",
    "value", "unit", "status_code", "is_anomaly", "alert_level"
]
CAMPOS_INVALIDOS = ["timestamp", "node_id", "variable", "value", "reason"]


class Armazenamento:
    def __init__(self, diretorio_dados: str | Path):
        self.diretorio_dados = Path(diretorio_dados)
        self.diretorio_dados.mkdir(parents=True, exist_ok=True)

    def adicionar_csv(self, nome_arquivo: str, linha: dict[str, Any], campos: list[str]) -> Path:
        caminho = self.diretorio_dados / nome_arquivo
        arquivo_existente = caminho.exists() and caminho.stat().st_size > 0
        with caminho.open("a", newline="", encoding="utf-8") as arquivo:
            escritor = csv.DictWriter(arquivo, fieldnames=campos, extrasaction="ignore")
            if not arquivo_existente:
                escritor.writeheader()
            escritor.writerow({campo: linha.get(campo, "") for campo in campos})
        return caminho

    def adicionar_telemetria(self, leitura: dict[str, Any], nome_arquivo: str = "telemetria.csv") -> Path:
        return self.adicionar_csv(nome_arquivo, leitura, CAMPOS_TELEMETRIA)

    def adicionar_invalida(self, leitura: dict[str, Any], motivo: str, nome_arquivo: str = "leituras_invalidas.csv") -> Path:
        return self.adicionar_csv(nome_arquivo, {**leitura, "reason": motivo}, CAMPOS_INVALIDOS)

    def salvar_json_seguro(self, nome_arquivo: str, dados: Any) -> Path:
        caminho = self.diretorio_dados / nome_arquivo
        temporario = caminho.with_suffix(caminho.suffix + ".tmp")
        with temporario.open("w", encoding="utf-8") as arquivo:
            json.dump(dados, arquivo, ensure_ascii=False, indent=2, default=str)
            arquivo.write("\n")
        temporario.replace(caminho)
        return caminho

    def ler_json(self, nome_arquivo: str, padrao: Any) -> Any:
        caminho = self.diretorio_dados / nome_arquivo
        if not caminho.exists():
            return padrao
        with caminho.open(encoding="utf-8") as arquivo:
            return json.load(arquivo)

    def atualizar_estado_atual(self, leitura: dict[str, Any], conexao: dict[str, str] | None = None) -> Path:
        estado = self.ler_json("estado_atual.json", {"machine_id": leitura["machine_id"], "variables": {}, "alerts": []})
        estado["timestamp"] = leitura["timestamp"]
        estado["machine_id"] = leitura["machine_id"]
        estado.setdefault("variables", {})[leitura["variable"]] = {
            "value": leitura["value"], "unit": leitura["unit"],
            "timestamp": leitura["timestamp"], "status_code": leitura["status_code"]
        }
        if conexao:
            estado["connection"] = conexao
        return self.salvar_json_seguro("estado_atual.json", estado)
