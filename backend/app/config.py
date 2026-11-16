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
    # Padrão extra de origens, para as URLs de prévia da Vercel (uma por deploy),
    # ex.: ^https://miniscan-[a-z0-9-]+\.vercel\.app$
    origens_cors_regex: str | None = field(
        default_factory=lambda: os.getenv("MINISCAN_ORIGENS_CORS_REGEX") or None
    )
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", ""))
    # Chave de serviço: só existe no servidor, nunca vai para o front-end.
    supabase_chave_servico: str = field(
        default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    )
    bucket: str = field(default_factory=lambda: os.getenv("MINISCAN_BUCKET", "miniscan-files"))

    @property
    def persistencia_configurada(self) -> bool:
        return bool(self.supabase_url and self.supabase_chave_servico)


configuracoes = Configuracoes()
