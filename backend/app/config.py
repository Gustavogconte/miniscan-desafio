"""Configurações da API lidas de variáveis de ambiente."""

import os
from dataclasses import dataclass, field

TAMANHO_MAXIMO_ARQUIVO = 15 * 1024 * 1024  # mesmo limite do bucket miniscan-files
MAXIMO_PAGINAS_PDF = 50
# Teto do corpo inteiro da requisição (todos os arquivos somados). Sem ele, uma
# requisição com dezenas de arquivos de 15 MB derrubaria a API por falta de memória.
TAMANHO_MAXIMO_REQUISICAO = 100 * 1024 * 1024
# Teto de qualquer corpo que não seja upload de arquivos (o JSON do /entrar e do
# /cadastrar tem poucas centenas de bytes).
TAMANHO_MAXIMO_REQUISICAO_SEM_ARQUIVO = 64 * 1024


def _ler_origens_cors() -> list[str]:
    valor = os.getenv("MINISCAN_ORIGENS_CORS", "http://localhost:3000")
    return [origem.strip() for origem in valor.split(",") if origem.strip()]


def _ler_threads_onnx() -> int:
    """Threads do onnxruntime no OCR e no detector de cantos; 0 = uma por núcleo da máquina."""
    valor = os.getenv("MINISCAN_THREADS_ONNX", "").strip()
    return int(valor) if valor.isdigit() else 0


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
    # Num contêiner limitado a 1 CPU, use 1. O onnxruntime enxerga todos os núcleos da
    # máquina e abre uma thread para cada, que ficam disputando o mesmo núcleo: com 5
    # pessoas ao mesmo tempo, o OCR de uma página passou de 3 s para mais de 60 s.
    threads_onnx: int = field(default_factory=_ler_threads_onnx)

    @property
    def persistencia_configurada(self) -> bool:
        return bool(self.supabase_url and self.supabase_chave_servico)


configuracoes = Configuracoes()
