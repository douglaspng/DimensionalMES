from __future__ import annotations

import json
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any


def agora_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def avaliar_alerta_critico(
    leitura: dict[str, Any],
    configuracao: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Retorna um alerta quando a leitura atinge um limite crítico."""
    variavel = leitura.get("variable")
    valor = leitura.get("value")
    definicao = configuracao.get(variavel, {})

    if valor is None:
        return None

    try:
        valor_numerico = float(valor)
    except (TypeError, ValueError):
        return None

    unidade = definicao.get("unit", "")
    limite_superior = definicao.get("critical_high")
    limite_inferior = definicao.get("critical_low")

    if limite_superior is not None and valor_numerico >= float(limite_superior):
        return {
            "tipo": "critico",
            "level": "critical",
            "variavel": variavel,
            "variable": variavel,
            "valor": valor_numerico,
            "value": valor_numerico,
            "limite": float(limite_superior),
            "unidade": unidade,
            "direcao": "alta",
            "mensagem": (
                f"{variavel} atingiu {valor_numerico} {unidade}. "
                f"Limite crítico: {limite_superior} {unidade}."
            ),
            "message": f"{variavel} acima do limite crítico de {limite_superior} {unidade}",
            "machine_id": leitura.get("machine_id", ""),
            "timestamp": leitura.get("timestamp") or agora_utc(),
        }

    if limite_inferior is not None and valor_numerico <= float(limite_inferior):
        return {
            "tipo": "critico",
            "level": "critical",
            "variavel": variavel,
            "variable": variavel,
            "valor": valor_numerico,
            "value": valor_numerico,
            "limite": float(limite_inferior),
            "unidade": unidade,
            "direcao": "baixa",
            "mensagem": (
                f"{variavel} atingiu {valor_numerico} {unidade}. "
                f"Limite crítico: {limite_inferior} {unidade}."
            ),
            "message": f"{variavel} abaixo do limite crítico de {limite_inferior} {unidade}",
            "machine_id": leitura.get("machine_id", ""),
            "timestamp": leitura.get("timestamp") or agora_utc(),
        }

    return None


def _configuracao_email() -> dict[str, Any]:
    return {
        "servidor": os.getenv("SMTP_SERVIDOR"),
        "porta": int(os.getenv("SMTP_PORTA", "587")),
        "usuario": os.getenv("SMTP_USUARIO"),
        "senha": os.getenv("SMTP_SENHA"),
        "remetente": os.getenv("EMAIL_REMETENTE") or os.getenv("SMTP_USUARIO"),
        "destinatario": os.getenv("EMAIL_DESTINATARIO"),
    }


def enviar_email_alerta(alerta: dict[str, Any]) -> None:
    """Envia um e-mail SMTP; credenciais nunca ficam no código ou no JSON."""
    configuracao = _configuracao_email()
    ausentes = [
        nome for nome, valor in configuracao.items()
        if nome != "porta" and not valor
    ]
    if ausentes:
        raise RuntimeError(
            "Configurações de e-mail ausentes: " + ", ".join(ausentes)
        )

    mensagem = EmailMessage()
    mensagem["Subject"] = f"[Dimensional MES] ALERTA CRÍTICO — {alerta['variavel']}"
    mensagem["From"] = configuracao["remetente"]
    mensagem["To"] = configuracao["destinatario"]
    mensagem.set_content(
        "Um alerta crítico foi identificado no Dimensional MES.\n\n"
        f"Variável: {alerta['variavel']}\n"
        f"Valor: {alerta['valor']} {alerta['unidade']}\n"
        f"Limite: {alerta['limite']} {alerta['unidade']}\n"
        f"Horário: {alerta['timestamp']}\n\n"
        f"Mensagem: {alerta['mensagem']}\n"
    )

    with smtplib.SMTP(configuracao["servidor"], configuracao["porta"], timeout=20) as smtp:
        smtp.starttls()
        smtp.login(configuracao["usuario"], configuracao["senha"])
        smtp.send_message(mensagem)


def _ler_controle(caminho: Path) -> dict[str, str]:
    if not caminho.exists():
        return {}
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
        return dados if isinstance(dados, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _salvar_controle(caminho: Path, dados: dict[str, str]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporario.replace(caminho)


def notificar_email_se_configurado(
    alerta: dict[str, Any],
    caminho_controle: str | Path,
    intervalo_minutos: int = 10,
) -> dict[str, Any]:
    """Envia uma vez por janela de tempo e nunca interrompe a ingestão."""
    caminho = Path(caminho_controle)
    chave = f"{alerta.get('variavel')}:{alerta.get('direcao', 'limite')}"
    controle = _ler_controle(caminho)
    ultimo_envio = controle.get(chave)

    if ultimo_envio:
        try:
            momento = datetime.fromisoformat(ultimo_envio.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) - momento < timedelta(minutes=intervalo_minutos):
                return {"enviada": False, "motivo": "cooldown", "chave": chave}
        except ValueError:
            pass

    configuracao = _configuracao_email()
    if not all(configuracao.get(nome) for nome in ("servidor", "usuario", "senha", "destinatario")):
        return {"enviada": False, "motivo": "smtp_nao_configurado", "chave": chave}

    try:
        enviar_email_alerta(alerta)
    except (OSError, smtplib.SMTPException, RuntimeError) as erro:
        return {"enviada": False, "motivo": f"falha: {erro}", "chave": chave}

    controle[chave] = agora_utc()
    _salvar_controle(caminho, controle)
    return {"enviada": True, "motivo": "enviada", "chave": chave}
