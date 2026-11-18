// Testa a escolha dos cantos de cada lado do cartão entre o servidor e a moldura-guia
// (src/lib/deteccao.ts). Rode com: npm test
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { cantosDoLado } from "../src/lib/deteccao.ts";

const canto = (x, y) => ({ x, y });
const GUIA = [canto(0.07, 0.3), canto(0.93, 0.3), canto(0.93, 0.6), canto(0.07, 0.6)];
const DO_SERVIDOR = [canto(0.12, 0.31), canto(0.88, 0.29), canto(0.9, 0.62), canto(0.11, 0.6)];
const FOTO_INTEIRA = [canto(0, 0), canto(1, 0), canto(1, 1), canto(0, 1)];
const ACHOU = { cantos: DO_SERVIDOR, detectado: true };
const NAO_ACHOU = { cantos: FOTO_INTEIRA, detectado: false };

describe("cantosDoLado", () => {
  it("prefere o servidor quando ele acha o documento", () => {
    assert.equal(cantosDoLado(GUIA, ACHOU), DO_SERVIDOR);
  });

  it("fica com a moldura-guia quando o servidor não acha", () => {
    assert.equal(cantosDoLado(GUIA, NAO_ACHOU), GUIA);
  });

  it("fica com a moldura-guia quando o pedido falha", () => {
    assert.equal(cantosDoLado(GUIA, null), GUIA);
  });

  it("sem moldura (foto da galeria), usa a resposta do servidor mesmo sem documento", () => {
    assert.equal(cantosDoLado(null, NAO_ACHOU), FOTO_INTEIRA);
  });

  it("sem moldura e sem servidor, devolve null para pedir de novo", () => {
    assert.equal(cantosDoLado(null, null), null);
  });
});
