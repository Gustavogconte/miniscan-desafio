// Testa como os cantos do servidor substituem a prévia ao vivo da câmera
// (src/lib/refinamento.ts). Rode com: npm test
import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { cantosDoLado, mudancasDoRefinamento } from "../src/lib/refinamento.ts";

const canto = (x, y) => ({ x, y });
const PREVIA = [canto(0.1, 0.1), canto(0.9, 0.1), canto(0.9, 0.9), canto(0.1, 0.9)];
const DO_SERVIDOR = [canto(0.12, 0.11), canto(0.88, 0.1), canto(0.9, 0.92), canto(0.11, 0.9)];
const FOTO_INTEIRA = [canto(0, 0), canto(1, 0), canto(1, 1), canto(0, 1)];
const ACHOU = { cantos: DO_SERVIDOR, detectado: true };
const NAO_ACHOU = { cantos: FOTO_INTEIRA, detectado: false };

describe("mudancasDoRefinamento", () => {
  it("troca a prévia pelos cantos do servidor quando ninguém mexeu", () => {
    assert.deepEqual(mudancasDoRefinamento({ cantos: PREVIA, processadas: {} }, PREVIA, ACHOU), {
      cantos: DO_SERVIDOR,
      cantosDetectados: DO_SERVIDOR,
      detectado: true,
      refinando: false,
    });
  });

  it("mantém o recorte de quem já arrastou um canto e guarda o do servidor na detecção automática", () => {
    const arrastado = [canto(0.2, 0.2), ...PREVIA.slice(1)];
    assert.deepEqual(mudancasDoRefinamento({ cantos: arrastado, processadas: {} }, PREVIA, ACHOU), {
      cantosDetectados: DO_SERVIDOR,
      detectado: true,
      refinando: false,
    });
  });

  it("fica com a prévia quando o servidor não acha a folha", () => {
    const pagina = { cantos: PREVIA, processadas: {} };
    assert.deepEqual(mudancasDoRefinamento(pagina, PREVIA, NAO_ACHOU), { refinando: false });
  });

  it("fica com a prévia quando o pedido falha", () => {
    const pagina = { cantos: PREVIA, processadas: {} };
    assert.deepEqual(mudancasDoRefinamento(pagina, PREVIA, null), { refinando: false });
  });

  it("não mexe numa página já recortada", () => {
    const recortada = { cantos: PREVIA, processadas: { bw: { url: "blob:x", blob: new Blob() } } };
    assert.deepEqual(mudancasDoRefinamento(recortada, PREVIA, ACHOU), { refinando: false });
  });
});

describe("cantosDoLado", () => {
  it("prefere o servidor quando ele acha o documento", () => {
    assert.equal(cantosDoLado(PREVIA, ACHOU), DO_SERVIDOR);
  });

  it("fica com a prévia (ou a moldura-guia) quando o servidor não acha", () => {
    assert.equal(cantosDoLado(PREVIA, NAO_ACHOU), PREVIA);
  });

  it("sem prévia, usa a resposta do servidor mesmo sem documento", () => {
    assert.equal(cantosDoLado(null, NAO_ACHOU), FOTO_INTEIRA);
  });

  it("sem prévia e sem servidor, devolve null para pedir de novo", () => {
    assert.equal(cantosDoLado(null, null), null);
  });
});
