/*
 * Web Worker do recorte ao vivo: carrega o OpenCV.js uma vez e responde a cada
 * quadro da câmera com os cantos da folha (ou null). Roda fora da thread principal
 * para a câmera e a interface não travarem.
 */
/* global cv, detectarCantosCv */
self.importScripts("/vendor/opencv-4.12.0.js", "/workers/detectar-cantos.js");

// Não usar `await cv`: o módulo do Emscripten tem um `then` que devolve ele mesmo,
// e o await entra em laço infinito. O sinal confiável é o onRuntimeInitialized.
var pronto = new Promise(function (resolver) {
  if (cv.Mat) return resolver();
  cv.onRuntimeInitialized = resolver;
}).then(function () {
  self.postMessage({ tipo: "pronto" });
});

self.onmessage = async function (evento) {
  await pronto;
  var dados = evento.data;
  var inicio = performance.now();
  var resultado = null;
  try {
    resultado = detectarCantosCv(cv, new Uint8ClampedArray(dados.pixels), dados.largura, dados.altura);
  } catch {
    resultado = null; // quadro problemático: trata como "sem folha"
  }
  self.postMessage({ tipo: "cantos", resultado: resultado, ms: performance.now() - inicio });
};
