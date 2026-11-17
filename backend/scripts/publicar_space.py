"""Publica a API no Hugging Face Spaces (Docker), com HTTPS e 16 GB de RAM no plano gratuito.

Uso (de dentro de backend/), depois de entrar na conta com `uvx hf auth login`:

    uv run --no-project --with huggingface_hub python scripts/publicar_space.py \
        --space SEU_USUARIO/miniscan-api \
        --origens https://SEU-APP.vercel.app \
        --enviar-segredos

- Cria o Space (público, SDK Docker) se ainda não existir.
- Envia a pasta backend/ com o Dockerfile e o código. O .env, a .venv e os testes ficam de fora.
- Gera o README.md exigido pelo Spaces, com o cabeçalho de configuração.
- Com --enviar-segredos, lê SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY do backend/.env
  e cadastra como Secrets do Space (os valores nunca são impressos).
"""

import argparse
import sys
from pathlib import Path

from huggingface_hub import HfApi

BACKEND = Path(__file__).resolve().parents[1]
PORTA = 8000  # a mesma do Dockerfile (variável PORT com padrão 8000)

IGNORAR = [
    ".venv/**",
    ".env",
    ".env.*",
    "**/__pycache__/**",
    "*.pyc",
    ".pytest_cache/**",
    ".ruff_cache/**",
    "tests/**",
    "scripts/**",
    "README.md",  # substituído pelo README do Space, gerado abaixo
]

README_SPACE = f"""---
title: MiniScan API
emoji: 📄
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: {PORTA}
pinned: false
short_description: Recorte de documentos, filtros, OCR em português e PDF
---

# MiniScan API

API do MiniScan: detecção de cantos, correção de perspectiva, filtros, OCR em português
(PaddleOCR) e geração de PDF.

A documentação interativa fica em `/docs`. O código-fonte está no repositório do projeto,
na pasta `backend/`.
"""

SEGREDOS = ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")


def ler_env(caminho: Path) -> dict[str, str]:
    valores: dict[str, str] = {}
    if not caminho.exists():
        return valores
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publica a API do MiniScan no Hugging Face Spaces."
    )
    parser.add_argument(
        "--space", required=True, help="usuario/nome do Space, ex.: maria/miniscan-api"
    )
    parser.add_argument(
        "--origens",
        default="",
        help="Origens do front-end liberadas no CORS, separadas por vírgula (ex.: https://app.vercel.app)",
    )
    parser.add_argument(
        "--origens-regex",
        default="",
        help=r"Padrão de origens para as prévias da Vercel, ex.: ^https://miniscan-[a-z0-9-]+\.vercel\.app$",
    )
    parser.add_argument(
        "--enviar-segredos",
        action="store_true",
        help="Cadastra a URL e a chave secreta do Supabase (backend/.env) como Secrets do Space",
    )
    args = parser.parse_args()

    api = HfApi()
    print(f"Conta: {api.whoami()['name']}")
    api.create_repo(args.space, repo_type="space", space_sdk="docker", private=False, exist_ok=True)

    if args.origens:
        api.add_space_variable(args.space, "MINISCAN_ORIGENS_CORS", args.origens)
    if args.origens_regex:
        api.add_space_variable(args.space, "MINISCAN_ORIGENS_CORS_REGEX", args.origens_regex)

    if args.enviar_segredos:
        env = ler_env(BACKEND / ".env")
        faltando = [chave for chave in SEGREDOS if not env.get(chave)]
        if faltando:
            print(f"Faltam no backend/.env: {', '.join(faltando)}", file=sys.stderr)
            return 1
        for chave in SEGREDOS:
            api.add_space_secret(args.space, chave, env[chave])
        print("Secrets cadastrados:", ", ".join(SEGREDOS))

    api.upload_folder(
        repo_id=args.space,
        repo_type="space",
        folder_path=BACKEND,
        ignore_patterns=IGNORAR,
        commit_message="Publica a API do MiniScan",
    )
    api.upload_file(
        path_or_fileobj=README_SPACE.encode("utf-8"),
        path_in_repo="README.md",
        repo_id=args.space,
        repo_type="space",
        commit_message="Atualiza a descrição do Space",
    )

    usuario, nome = args.space.split("/")
    print(f"\nPublicado. O build leva alguns minutos: https://huggingface.co/spaces/{args.space}")
    print(
        f"Endereço da API (use no NEXT_PUBLIC_API_URL): https://{usuario}-{nome}.hf.space".lower()
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
