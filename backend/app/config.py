"""Configurações da API lidas de variáveis de ambiente."""

import os
from dataclasses import dataclass, field

TAMANHO_MAXIMO_ARQUIVO = 15 * 1024 * 1024  # mesmo limite do bucket miniscan-files
MAXIMO_PAGINAS_PDF = 50


def _ler_origens_cors() -> list[str]:
    valor = os.getenv("MINISCAN_ORIGENS_CORS", "http://localhost:3000")
    return [origem.strip() for origem in valor.split(",") if origem.strip()]


@dataclass(frozen=True)
class Configuracoes:
    origens_cors: list[str] = field(default_factory=_ler_origens_cors)


configuracoes = Configuracoes()
