"""Fotos sintéticas difíceis de documento, parecidas com as de celular.

Cada cenário devolve (foto BGR, cantos verdadeiros normalizados). Servem para medir a
detecção de bordas em condições reais: mesa clara, textura de madeira, sombra,
texto denso, desfoque, compressão JPEG e folha ocupando quase a foto inteira.
"""

import cv2
import numpy as np

LARGURA, ALTURA = 1080, 1440  # foto em pé, proporção 3:4 como a câmera do celular


def _pagina(rng: np.random.Generator, largura=850, altura=1100, cor=(238, 240, 236)) -> np.ndarray:
    """Folha com cabeçalho, parágrafos densos e uma tabela, como um documento comum."""
    pagina = np.full((altura, largura, 3), cor, np.uint8)
    cv2.putText(pagina, "DECLARACAO", (70, 120), cv2.FONT_HERSHEY_DUPLEX, 2.0, (25, 25, 25), 4)
    y = 200
    while y < altura - 120:
        x = 70
        while x < largura - 90:
            palavra = int(rng.integers(30, 110))
            cv2.line(pagina, (x, y), (min(x + palavra, largura - 70), y), (45, 45, 45), 6)
            x += palavra + int(rng.integers(12, 22))
        y += 34 if rng.random() > 0.12 else 70
    return pagina


def _fundo(tipo: str, rng: np.random.Generator) -> np.ndarray:
    if tipo == "escuro":
        base = np.full((ALTURA, LARGURA, 3), (55, 55, 60), np.float32)
    elif tipo == "madeira":
        xx = np.arange(LARGURA, dtype=np.float32)[None, :]
        yy = np.arange(ALTURA, dtype=np.float32)[:, None]
        veios = 18 * np.sin(xx / 9 + 6 * np.sin(yy / 140)) + 10 * np.sin(xx / 3.1)
        base = np.dstack([90 + veios, 130 + veios, 170 + veios]).astype(np.float32)
    elif tipo == "mesa_clara":  # bege claro: pouco contraste com o papel
        base = np.full((ALTURA, LARGURA, 3), (196, 206, 214), np.float32)
    elif tipo == "tecido":
        base = np.full((ALTURA, LARGURA, 3), (120, 95, 80), np.float32)
        base += rng.normal(0, 22, base.shape).astype(np.float32)
    else:
        raise ValueError(tipo)
    base += rng.normal(0, 6, base.shape).astype(np.float32)
    return np.clip(base, 0, 255)


def _fotografar(pagina, fundo, cantos_px, sombra=0.0, desfoque=0, jpeg=80, seed=0):
    h, w = pagina.shape[:2]
    origem = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    matriz = cv2.getPerspectiveTransform(origem, np.float32(cantos_px))
    folha = cv2.warpPerspective(pagina, matriz, (LARGURA, ALTURA)).astype(np.float32)
    mascara = cv2.warpPerspective(np.ones((h, w), np.float32), matriz, (LARGURA, ALTURA))[..., None]
    mascara = cv2.GaussianBlur(mascara, (3, 3), 0)[..., None] if mascara.ndim == 2 else mascara
    foto = fundo * (1 - mascara) + folha * mascara
    if sombra:
        # Sombra da mão/celular: degradê forte sobre um lado da foto inteira.
        xx = np.linspace(0, 1, LARGURA, dtype=np.float32)[None, :, None]
        yy = np.linspace(0, 1, ALTURA, dtype=np.float32)[:, None, None]
        foto *= 1 - sombra * np.clip(1.4 * xx + 0.6 * yy - 0.7, 0, 1)
    foto += np.random.default_rng(seed).normal(0, 4, foto.shape)
    foto = np.clip(foto, 0, 255).astype(np.uint8)
    if desfoque:
        foto = cv2.GaussianBlur(foto, (desfoque, desfoque), 0)
    foto = cv2.imdecode(
        cv2.imencode(".jpg", foto, [cv2.IMWRITE_JPEG_QUALITY, jpeg])[1], cv2.IMREAD_COLOR
    )
    return foto, np.float32(cantos_px) / np.float32([LARGURA - 1, ALTURA - 1])


INCLINADA = [[170, 210], [905, 260], [960, 1250], [120, 1200]]
QUASE_RETA = [[120, 140], [960, 150], [970, 1300], [110, 1290]]
OCUPA_TUDO = [[25, 30], [1050, 45], [1060, 1410], [15, 1395]]  # folha quase encostando nas bordas
PEQUENA_AO_LONGE = [[330, 420], [760, 440], [780, 1010], [310, 990]]


def cenarios() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(7)
    pagina = _pagina(rng)
    return {
        "mesa_escura": _fotografar(pagina, _fundo("escuro", rng), INCLINADA),
        "madeira": _fotografar(pagina, _fundo("madeira", rng), INCLINADA, seed=1),
        "mesa_clara": _fotografar(pagina, _fundo("mesa_clara", rng), INCLINADA, seed=2),
        "mesa_clara_sombra": _fotografar(
            pagina, _fundo("mesa_clara", rng), QUASE_RETA, sombra=0.45, seed=3
        ),
        "madeira_sombra_desfoque": _fotografar(
            pagina, _fundo("madeira", rng), INCLINADA, sombra=0.35, desfoque=7, jpeg=60, seed=4
        ),
        "tecido": _fotografar(pagina, _fundo("tecido", rng), QUASE_RETA, seed=5),
        "ocupa_quase_tudo": _fotografar(pagina, _fundo("madeira", rng), OCUPA_TUDO, seed=6),
        "pequena_ao_longe": _fotografar(pagina, _fundo("tecido", rng), PEQUENA_AO_LONGE, seed=7),
    }


def erro_maximo(detectados: np.ndarray, verdadeiros: np.ndarray) -> float:
    """Maior distância entre um canto detectado e o verdadeiro (fração da diagonal)."""
    escala = np.float32([LARGURA, ALTURA]) / np.hypot(LARGURA, ALTURA)
    return float(np.max(np.linalg.norm((detectados - verdadeiros) * escala, axis=1)))


def _ondular(foto_sem_onda: np.ndarray, amplitude: float = 9.0) -> np.ndarray:
    """Entorta levemente a imagem (papel não perfeitamente plano): bordas deixam de ser retas."""
    yy, xx = np.mgrid[0:ALTURA, 0:LARGURA].astype(np.float32)
    mapa_x = xx + amplitude * np.sin(yy / 95)
    mapa_y = yy + amplitude * np.sin(xx / 120)
    return cv2.remap(foto_sem_onda, mapa_x, mapa_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def cenarios_dificeis() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    rng = np.random.default_rng(11)
    pagina = _pagina(rng)
    base = cenarios()

    ondulada, verdade_ondulada = _fotografar(pagina, _fundo("madeira", rng), INCLINADA, seed=8)
    ondulada = _ondular(ondulada)

    com_dedo, verdade_dedo = _fotografar(pagina, _fundo("tecido", rng), QUASE_RETA, seed=9)
    # Polegar (cor de pele) cobrindo o canto inferior esquerdo da folha.
    cv2.ellipse(com_dedo, (150, 1270), (95, 160), 35, 0, 360, (120, 150, 205), -1)
    cv2.ellipse(com_dedo, (150, 1270), (95, 160), 35, 0, 360, (95, 120, 170), 6)

    dobrada, verdade_dobrada = _fotografar(pagina, _fundo("escuro", rng), QUASE_RETA, seed=10)
    # Canto superior direito dobrado para dentro: um triângulo cinza no lugar da ponta.
    canto = np.int32([[960, 150], [880, 148], [962, 235]])
    cv2.fillPoly(dobrada, [canto], (55, 55, 60))
    cv2.fillPoly(dobrada, [np.int32([[880, 148], [962, 235], [890, 230]])], (205, 205, 200))

    return {
        **base,
        "borda_ondulada": (ondulada, verdade_ondulada),
        "dedo_no_canto": (com_dedo, verdade_dedo),
        "canto_dobrado": (dobrada, verdade_dobrada),
    }


def _fundo_ocre(cor_bgr, rng: np.random.Generator, veios: bool) -> np.ndarray:
    base = np.full((ALTURA, LARGURA, 3), cor_bgr, np.float32)
    if veios:  # madeira clara / MDF: veios suaves da mesma cor
        xx = np.arange(LARGURA, dtype=np.float32)[None, :]
        yy = np.arange(ALTURA, dtype=np.float32)[:, None]
        base += (6 * np.sin(xx / 11 + 4 * np.sin(yy / 160)))[..., None]
    base += rng.normal(0, 5, base.shape).astype(np.float32)
    return np.clip(base, 0, 255)


def _luz_quente(foto: np.ndarray, intensidade: float = 0.12) -> np.ndarray:
    """Lâmpada amarelada: tira azul e põe vermelho, deixando o papel branco meio bege."""
    quente = foto.astype(np.float32) * np.float32([1 - intensidade, 1.0, 1 + intensidade * 0.4])
    return np.clip(quente, 0, 255).astype(np.uint8)


def cenarios_ocre() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Fundos ocre/bege parecidos com o papel: o caso mais difícil para a detecção."""
    rng = np.random.default_rng(21)
    pagina = _pagina(rng)
    madeira_clara, v1 = _fotografar(
        pagina, _fundo_ocre((150, 195, 225), rng, True), INCLINADA, seed=21
    )
    mdf_bege, v2 = _fotografar(pagina, _fundo_ocre((175, 205, 222), rng, True), QUASE_RETA, seed=22)
    ocre, v3 = _fotografar(pagina, _fundo_ocre((95, 160, 205), rng, False), INCLINADA, seed=23)
    bege_quente, v4 = _fotografar(
        pagina, _fundo_ocre((185, 210, 228), rng, False), QUASE_RETA, sombra=0.3, seed=24
    )
    return {
        "madeira_clara": (madeira_clara, v1),
        "mdf_bege": (mdf_bege, v2),
        "ocre": (ocre, v3),
        "bege_luz_quente_sombra": (_luz_quente(bege_quente), v4),
    }


def _como_video(foto: np.ndarray, desfoque: int = 5) -> np.ndarray:
    """Quadro de vídeo de celular: 720p, desfocado, comprimido, depois ampliado de volta."""
    altura, largura = foto.shape[:2]
    reduzida = cv2.resize(foto, (540, 720), interpolation=cv2.INTER_AREA)
    reduzida = cv2.GaussianBlur(reduzida, (desfoque, desfoque), 0)
    reduzida = cv2.imdecode(
        cv2.imencode(".jpg", reduzida, [cv2.IMWRITE_JPEG_QUALITY, 55])[1], cv2.IMREAD_COLOR
    )
    return cv2.resize(reduzida, (largura, altura), interpolation=cv2.INTER_LINEAR)


def cenarios_ocre_dificeis() -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Papel bege quase da cor da mesa, como sai num quadro de vídeo do celular."""
    rng = np.random.default_rng(31)
    pagina_bege = _pagina(rng, cor=(205, 222, 232))  # papel sob luz quente
    cenarios = {}
    for nome, fundo, cantos, sombra in [
        (
            "bege_sobre_mdf_video",
            (180, 208, 226),
            QUASE_RETA,
            0.0,
        ),  # brilho ~10 níveis abaixo do papel
        ("bege_sobre_ocre_video", (140, 190, 222), INCLINADA, 0.0),
        ("bege_sobre_madeira_clara_sombra", (170, 200, 222), INCLINADA, 0.3),
    ]:
        foto, verdade = _fotografar(
            pagina_bege,
            _fundo_ocre(fundo, rng, True),
            cantos,
            sombra=sombra,
            seed=len(cenarios) + 31,
        )
        cenarios[nome] = (_como_video(foto), verdade)
    return cenarios
