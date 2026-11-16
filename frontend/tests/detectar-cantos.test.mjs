// Testa a detecção de cantos do recorte ao vivo (public/workers/detectar-cantos.js)
// com o mesmo OpenCV.js que roda no navegador. Rode com: npm test
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { before, describe, it } from "node:test";

const require = createRequire(import.meta.url);
const { detectarCantosCv, ordenarCantos } = require("../public/workers/detectar-cantos.js");

let cv;
before(async () => {
  // Sem `await` no módulo: o `then` do Emscripten devolve o próprio módulo (laço infinito).
  const modulo = require("@techstark/opencv-js");
  await new Promise((resolver) => (modulo.Mat ? resolver() : (modulo.onRuntimeInitialized = resolver)));
  cv = modulo;
});

const LARGURA = 270;
const ALTURA = 360;

/** Folha clara inclinada sobre uma mesa (escura por padrão), com "linhas de texto". */
function fotoSintetica(cantosPx, fundo = [55, 55, 55, 255], cobrirCanto = false) {
  const foto = new cv.Mat(ALTURA, LARGURA, cv.CV_8UC4, new cv.Scalar(...fundo));
  const poligono = cv.matFromArray(4, 1, cv.CV_32SC2, cantosPx.flat());
  const lista = new cv.MatVector();
  lista.push_back(poligono);
  cv.fillPoly(foto, lista, new cv.Scalar(245, 245, 245, 255));
  for (let i = 0; i < 5; i++) {
    const y = 120 + i * 30;
    cv.line(foto, new cv.Point(95, y), new cv.Point(185, y + 6), new cv.Scalar(30, 30, 30, 255), 3);
  }
  if (cobrirCanto) {
    // "Dedo" cor de pele sobre o canto inferior esquerdo da folha.
    cv.ellipse(foto, new cv.Point(cantosPx[3][0], cantosPx[3][1]), new cv.Size(28, 46), 35, 0, 360, new cv.Scalar(205, 150, 120, 255), -1);
  }
  const pixels = new Uint8ClampedArray(foto.data);
  [foto, poligono, lista].forEach((m) => m.delete());
  return pixels;
}

describe("detectarCantosCv", () => {
  it("encontra a folha inclinada e devolve os cantos em ordem", () => {
    const cantosPx = [
      [45, 50],
      [228, 66],
      [240, 315],
      [33, 300],
    ];
    const resultado = detectarCantosCv(cv, fotoSintetica(cantosPx), LARGURA, ALTURA);
    assert.ok(resultado, "a folha deveria ter sido detectada");
    resultado.cantos.forEach((canto, i) => {
      assert.ok(Math.abs(canto.x - cantosPx[i][0] / (LARGURA - 1)) < 0.03, `x do canto ${i}`);
      assert.ok(Math.abs(canto.y - cantosPx[i][1] / (ALTURA - 1)) < 0.03, `y do canto ${i}`);
    });
    assert.ok(resultado.area > 0.4 && resultado.area < 0.7);
  });

  it("acha a folha branca numa mesa clara (pouco contraste)", () => {
    const cantosPx = [
      [45, 50],
      [228, 66],
      [240, 315],
      [33, 300],
    ];
    const resultado = detectarCantosCv(cv, fotoSintetica(cantosPx, [205, 212, 214, 255]), LARGURA, ALTURA);
    assert.ok(resultado, "a folha deveria ter sido detectada");
    resultado.cantos.forEach((canto, i) => {
      assert.ok(Math.abs(canto.x - cantosPx[i][0] / (LARGURA - 1)) < 0.03, `x do canto ${i}`);
      assert.ok(Math.abs(canto.y - cantosPx[i][1] / (ALTURA - 1)) < 0.03, `y do canto ${i}`);
    });
  });

  it("recupera o canto coberto por um dedo prolongando os lados", () => {
    const cantosPx = [
      [45, 50],
      [228, 66],
      [240, 315],
      [33, 300],
    ];
    const resultado = detectarCantosCv(cv, fotoSintetica(cantosPx, [55, 55, 55, 255], true), LARGURA, ALTURA);
    assert.ok(resultado, "a folha deveria ter sido detectada mesmo com o canto coberto");
    const escondido = resultado.cantos[3];
    assert.ok(Math.abs(escondido.x - cantosPx[3][0] / (LARGURA - 1)) < 0.04, "x do canto escondido");
    assert.ok(Math.abs(escondido.y - cantosPx[3][1] / (ALTURA - 1)) < 0.04, "y do canto escondido");
  });

  it("devolve null quando não há folha", () => {
    const vazia = new Uint8ClampedArray(LARGURA * ALTURA * 4).fill(120);
    assert.equal(detectarCantosCv(cv, vazia, LARGURA, ALTURA), null);
  });

  it("ignora quadriláteros pequenos demais", () => {
    const pequena = [
      [120, 150],
      [150, 152],
      [149, 190],
      [119, 188],
    ];
    assert.equal(detectarCantosCv(cv, fotoSintetica(pequena), LARGURA, ALTURA), null);
  });
});

describe("ordenarCantos", () => {
  it("ordena pontos embaralhados como sup. esq., sup. dir., inf. dir., inf. esq.", () => {
    const esperado = [
      { x: 0.1, y: 0.1 },
      { x: 0.9, y: 0.15 },
      { x: 0.85, y: 0.9 },
      { x: 0.05, y: 0.8 },
    ];
    assert.deepEqual(ordenarCantos([esperado[2], esperado[0], esperado[3], esperado[1]]), esperado);
  });
});
