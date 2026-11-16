import cv2
import numpy as np
import pytest

from app.visao.bordas import CANTOS_PADRAO, detectar_cantos
from app.visao.filtros import aplicar_filtro
from app.visao.imagem import ImagemInvalidaError, decodificar_imagem
from app.visao.perspectiva import CantosInvalidosError, corrigir_perspectiva, ordenar_cantos
from tests.conftest import CANTOS_FOLHA_NORMALIZADOS


class TestOrdenarCantos:
    def test_ordena_pontos_embaralhados(self):
        esperado = np.array([[0.1, 0.1], [0.9, 0.15], [0.85, 0.9], [0.05, 0.8]], dtype=np.float32)
        embaralhado = esperado[[2, 0, 3, 1]]
        np.testing.assert_allclose(ordenar_cantos(embaralhado), esperado)

    def test_folha_girada_45_graus_nao_repete_pontos(self):
        losango = np.array([[0.5, 0.1], [0.9, 0.5], [0.5, 0.9], [0.1, 0.5]], dtype=np.float32)
        ordenados = ordenar_cantos(losango[::-1])
        assert len({tuple(ponto) for ponto in ordenados}) == 4


class TestDetectarCantos:
    def test_encontra_a_folha_inclinada(self, foto_documento):
        cantos, detectado = detectar_cantos(foto_documento)
        assert detectado
        np.testing.assert_allclose(cantos, CANTOS_FOLHA_NORMALIZADOS, atol=0.02)

    def test_sem_folha_devolve_imagem_inteira(self):
        foto_vazia = np.full((600, 400, 3), 120, dtype=np.uint8)
        cantos, detectado = detectar_cantos(foto_vazia)
        assert not detectado
        np.testing.assert_allclose(cantos, CANTOS_PADRAO)


class TestCorrigirPerspectiva:
    def test_gera_pagina_retangular_no_tamanho_da_folha(self, foto_documento):
        pagina = corrigir_perspectiva(foto_documento, CANTOS_FOLHA_NORMALIZADOS)
        altura, largura = pagina.shape[:2]
        # Lado maior entre os de cima/baixo (~690 px) e esquerda/direita (~830 px), menos o aparo.
        assert 660 < largura < 700
        assert 800 < altura < 840
        # As bordas da página retificada são papel claro, não a mesa escura.
        assert pagina[5:40, 5:40].mean() > 200
        assert pagina[-40:-5, -40:-5].mean() > 200

    @pytest.mark.parametrize(
        "cantos",
        [
            [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9]],  # só 3 pontos
            [[0.1, 0.1], [1.5, 0.1], [0.9, 0.9], [0.1, 0.9]],  # fora de 0..1
            [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3], [0.4, 0.4]],  # pontos alinhados
        ],
    )
    def test_rejeita_cantos_invalidos(self, foto_documento, cantos):
        with pytest.raises(CantosInvalidosError):
            corrigir_perspectiva(foto_documento, np.array(cantos, dtype=np.float32))


class TestFiltros:
    def test_original_mantem_a_imagem(self, pagina_plana):
        assert aplicar_filtro(pagina_plana, "original") is pagina_plana

    def test_cinza_tem_um_canal(self, pagina_plana):
        assert aplicar_filtro(pagina_plana, "grayscale").ndim == 2

    def test_preto_e_branco_e_binario(self, pagina_plana):
        resultado = aplicar_filtro(pagina_plana, "bw")
        assert set(np.unique(resultado)) <= {0, 255}

    def test_preto_e_branco_remove_sombra(self, pagina_plana):
        # Sombra forte em degradê sobre metade da página, como a da mão sobre o papel.
        sombreada = pagina_plana.astype(np.float32)
        sombreada[:, 400:] *= np.linspace(1.0, 0.45, 400, dtype=np.float32)[None, :, None]
        resultado = aplicar_filtro(sombreada.astype(np.uint8), "bw")
        # Papel na área sombreada (sem texto) continua branco.
        assert resultado[1000:1100, 600:780].mean() > 240

    def test_filtro_desconhecido(self, pagina_plana):
        with pytest.raises(ValueError):
            aplicar_filtro(pagina_plana, "sepia")


class TestDecodificarImagem:
    @pytest.mark.parametrize("dados", [b"", b"isto nao e uma imagem"])
    def test_rejeita_arquivo_invalido(self, dados):
        with pytest.raises(ImagemInvalidaError):
            decodificar_imagem(dados)


class TestCalibracaoPretoEBranco:
    def test_bloco_impar_de_no_minimo_35(self):
        from app.visao.filtros import _tamanho_bloco

        for lado in (300, 1200, 2400, 4000):
            bloco = _tamanho_bloco(np.zeros((lado, lado), np.uint8))
            assert bloco >= 35 and bloco % 2 == 1

    def test_papel_limpo_e_letras_sem_engrossar(self, pagina_plana):
        resultado = aplicar_filtro(pagina_plana, "bw", preservar_graficos=False)
        assert resultado[1000:1100, 100:700].min() == 255  # papel vazio sem pontos pretos
        tinta_original = (cv2.cvtColor(pagina_plana, cv2.COLOR_BGR2GRAY) < 128).sum()
        tinta_pb = (resultado < 128).sum()
        assert tinta_pb < tinta_original * 1.25  # o traço não engorda
