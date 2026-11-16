"""Modo livro: separa as duas páginas de um livro aberto fotografado de uma vez."""

import cv2
import numpy as np

from app.visao.perspectiva import validar_cantos_normalizados

LADO_ANALISE = 1000  # a lombada é procurada numa versão reduzida da página retificada
FAIXA_LOMBADA = (0.35, 0.65)  # a lombada fica perto do meio do livro aberto
CONTRASTE_MINIMO = 6  # sombra mínima (níveis de cinza) para confiar na lombada encontrada


def encontrar_lombada(retificada: np.ndarray) -> float:
    """Posição horizontal (0..1) da lombada na página retificada.

    A dobra do livro cria uma faixa vertical mais escura (sombra da curvatura).
    Procura a coluna mais escura perto do meio; sem sombra clara, divide ao meio.
    """
    cinza = cv2.cvtColor(retificada, cv2.COLOR_BGR2GRAY) if retificada.ndim == 3 else retificada
    largura = cinza.shape[1]
    perfil = cinza.mean(axis=0)
    janela = max(5, largura // 60)
    suave = np.convolve(perfil, np.ones(janela) / janela, mode="same")
    inicio, fim = (int(largura * f) for f in FAIXA_LOMBADA)
    faixa = suave[inicio:fim]
    if faixa.size == 0 or float(np.median(faixa) - faixa.min()) < CONTRASTE_MINIMO:
        return 0.5
    return float(inicio + int(np.argmin(faixa))) / (largura - 1)


def dividir_livro(
    imagem: np.ndarray, cantos_normalizados: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float]:
    """Devolve os cantos (normalizados, na foto original) da página esquerda e da direita.

    A lombada é localizada na página retificada e a linha de corte é levada de volta
    para a foto pela homografia inversa. Assim cada página é recortada direto da foto
    original, sem perder resolução.
    """
    altura, largura = imagem.shape[:2]
    cantos = validar_cantos_normalizados(cantos_normalizados)
    origem = cantos * np.array([largura - 1, altura - 1], dtype=np.float32)
    sup_esq, sup_dir, inf_dir, inf_esq = origem

    largura_ret = max(np.linalg.norm(inf_dir - inf_esq), np.linalg.norm(sup_dir - sup_esq))
    altura_ret = max(np.linalg.norm(sup_dir - inf_dir), np.linalg.norm(sup_esq - inf_esq))
    escala = min(1.0, LADO_ANALISE / max(largura_ret, altura_ret))
    w, h = max(2, round(largura_ret * escala)), max(2, round(altura_ret * escala))
    destino = np.array([[0, 0], [w - 1, 0], [w - 1, h - 1], [0, h - 1]], dtype=np.float32)
    matriz = cv2.getPerspectiveTransform(origem, destino)
    retificada = cv2.warpPerspective(imagem, matriz, (w, h))

    fracao = encontrar_lombada(retificada)
    x = fracao * (w - 1)
    linha = np.array([[[x, 0]], [[x, h - 1]]], dtype=np.float32)
    topo, base = cv2.perspectiveTransform(linha, np.linalg.inv(matriz)).reshape(2, 2)

    normalizar = np.array([largura - 1, altura - 1], dtype=np.float32)
    topo_n, base_n = np.clip(topo / normalizar, 0, 1), np.clip(base / normalizar, 0, 1)
    esquerda = np.array([cantos[0], topo_n, base_n, cantos[3]], dtype=np.float32)
    direita = np.array([topo_n, cantos[1], cantos[2], base_n], dtype=np.float32)
    return esquerda, direita, fracao
