// Regras do visualizador de páginas (src/lib/visualizador.ts). Rode com: npm test
// O Node 22 lê o TypeScript direto (só remove os tipos), sem build.
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { fonteDaImagem, indiceDepoisDeExcluir, rotuloDaPagina } from "../src/lib/visualizador.ts";

describe("fonteDaImagem", () => {
  const pagina = { id: "1", src: "tratada.jpg", srcOriginal: "foto.jpg" };

  it("mostra a página tratada por padrão", () => {
    assert.equal(fonteDaImagem(pagina, false), "tratada.jpg");
  });

  it("mostra a foto original quando pedida", () => {
    assert.equal(fonteDaImagem(pagina, true), "foto.jpg");
  });

  it("fica na versão tratada quando não há foto original", () => {
    assert.equal(fonteDaImagem({ id: "2", src: "unica.jpg" }, true), "unica.jpg");
  });
});

describe("rotuloDaPagina", () => {
  it("numera a partir de 1", () => {
    assert.equal(rotuloDaPagina(0, 3), "Página 1 de 3");
  });

  it("acrescenta o detalhe", () => {
    assert.equal(rotuloDaPagina(2, 3, "P&B"), "Página 3 de 3 · P&B");
  });

  it("aceita outro nome, como na revisão das fotos do lote", () => {
    assert.equal(rotuloDaPagina(0, 2, undefined, "Foto"), "Foto 1 de 2");
  });
});

describe("indiceDepoisDeExcluir", () => {
  it("fica no mesmo lugar ao excluir uma página do meio", () => {
    assert.equal(indiceDepoisDeExcluir(1, 4), 1);
  });

  it("volta uma ao excluir a última", () => {
    assert.equal(indiceDepoisDeExcluir(3, 4), 2);
  });

  it("devolve null quando não sobra nenhuma", () => {
    assert.equal(indiceDepoisDeExcluir(0, 1), null);
  });
});
