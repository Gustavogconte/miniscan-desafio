// Nome sugerido para o documento (src/lib/titulo.ts). Rode com: npm test
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { semAcentos, sugerirTitulo, tipoDoCartao } from "../src/lib/titulo.ts";

const hoje = new Date(2026, 10, 19);

describe("sugerirTitulo", () => {
  it("usa o título que a API achou na primeira página", () => {
    const paginas = [{ textoOcr: "...", tituloOcr: "CONTRATO DE LOCAÇÃO" }, { textoOcr: "", tituloOcr: "Outra" }];
    assert.equal(sugerirTitulo(paginas, hoje), "CONTRATO DE LOCAÇÃO");
  });

  it("sem título, fica Documento com a data", () => {
    assert.equal(sugerirTitulo([{ textoOcr: "", tituloOcr: "" }], hoje), "Documento 19/11/2026");
    assert.equal(sugerirTitulo([], hoje), "Documento 19/11/2026");
  });

  it("no RG ou CNH, usa o tipo do documento", () => {
    const pagina = { cartao: {}, textoOcr: "CARTEIRA NACIONAL DE HABILITAÇÃO", tituloOcr: "REPÚBLICA FEDERATIVA" };
    assert.equal(sugerirTitulo([pagina], hoje), "CNH");
  });
});

describe("tipoDoCartao", () => {
  it("reconhece a CNH, mesmo com a palavra IDENTIDADE no campo do RG", () => {
    assert.equal(tipoDoCartao("Doc. Identidade / Órg. Emissor\nCarteira Nacional de Habilitacao"), "CNH");
  });

  it("reconhece o RG antigo e a carteira de identidade nova", () => {
    assert.equal(tipoDoCartao("REGISTRO GERAL 12.345.678-9"), "RG");
    assert.equal(tipoDoCartao("CARTEIRA DE IDENTIDADE NACIONAL"), "RG");
  });

  it("reconhece a CNH pelo Departamento de Trânsito quando o OCR erra HABILITAÇÃO", () => {
    assert.equal(tipoDoCartao("DEPARTAMENTO NACIONAL DE TRÂNSITO\nCARTEIRA NACIONAL DE HABILlTACA0\nDOC. IDENTIDADE"), "CNH");
  });

  it("sem as palavras, fica RG ou CNH", () => {
    assert.equal(tipoDoCartao(""), "RG ou CNH");
  });
});

describe("semAcentos", () => {
  it("tira os acentos e mantém as letras", () => {
    assert.equal(semAcentos("Habilitação, Ação e Trânsito"), "Habilitacao, Acao e Transito");
  });
});
