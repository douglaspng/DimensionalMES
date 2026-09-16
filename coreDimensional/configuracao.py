from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConfiguracaoAplicacao:
    """Configurações carregadas do arquivo config/config.json."""

    diretorio_raiz: Path
    dados: dict[str, Any]

    @property
    def identificacao_maquina(self) -> str:
        return self.dados["machine_id"]

    @property
    def variaveis(self) -> dict[str, dict[str, Any]]:
        return self.dados.get("variables", {})

    @property
    def armazenamento(self) -> dict[str, Any]:
        return self.dados.get("storage", {})

    @classmethod
    def carregar(cls, caminho: str | Path) -> "ConfiguracaoAplicacao":
        caminho_configuracao = Path(caminho).resolve()
        with caminho_configuracao.open(encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
        # Na aplicação, o arquivo fica em projeto/config/config.json.
        # Nos testes, ele pode ficar diretamente na pasta temporária do projeto.
        diretorio_raiz = (
            caminho_configuracao.parent.parent
            if caminho_configuracao.parent.name.lower() == "config"
            else caminho_configuracao.parent
        )
        return cls(diretorio_raiz=diretorio_raiz, dados=dados)

    def caminho_dados(self, nome_arquivo: str) -> Path:
        diretorio_dados = self.diretorio_raiz / self.armazenamento.get("data_dir", "data")
        diretorio_dados.mkdir(parents=True, exist_ok=True)
        return diretorio_dados / nome_arquivo
