"""Leitura de QR codes com o OpenCV (para navegadores sem BarcodeDetector, como o Safari)."""

import cv2
import numpy as np

LADO_MINIMO = 640  # QR pequenos na foto são lidos melhor depois de ampliar


def _detector():
    # O detector baseado em ArUco (OpenCV 4.8+) acha QR inclinados e pequenos com mais robustez.
    if hasattr(cv2, "QRCodeDetectorAruco"):
        return cv2.QRCodeDetectorAruco()
    return cv2.QRCodeDetector()


def ler_qrcodes(imagem: np.ndarray) -> list[str]:
    """Textos de todos os QR codes legíveis na imagem, sem repetição, na ordem encontrada."""
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY) if imagem.ndim == 3 else imagem
    if min(cinza.shape) < LADO_MINIMO:
        fator = LADO_MINIMO / min(cinza.shape)
        cinza = cv2.resize(cinza, None, fx=fator, fy=fator, interpolation=cv2.INTER_CUBIC)

    detector = _detector()
    textos: list[str] = []
    try:
        ok, decodificados, _pontos, _ = detector.detectAndDecodeMulti(cinza)
        if ok:
            textos.extend(decodificados)
    except cv2.error:
        pass
    if not any(textos):
        texto, _pontos, _ = detector.detectAndDecode(cinza)
        textos.append(texto)
    return list(dict.fromkeys(t for t in textos if t))
