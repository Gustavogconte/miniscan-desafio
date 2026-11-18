"""Leitura das configurações por variáveis de ambiente."""

from app.config import Configuracoes


def test_threads_onnx_vem_da_variavel(monkeypatch):
    monkeypatch.setenv("MINISCAN_THREADS_ONNX", "1")
    assert Configuracoes().threads_onnx == 1


def test_threads_onnx_sem_variavel_ou_invalida_usa_o_padrao(monkeypatch):
    monkeypatch.delenv("MINISCAN_THREADS_ONNX", raising=False)
    assert Configuracoes().threads_onnx == 0
    monkeypatch.setenv("MINISCAN_THREADS_ONNX", "metade")
    assert Configuracoes().threads_onnx == 0
