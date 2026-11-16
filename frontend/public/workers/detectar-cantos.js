/*
 * Detecção dos 4 cantos da folha com OpenCV.js — o mesmo pipeline do backend
 * (backend/app/visao/bordas.py), rodando no navegador para o recorte ao vivo.
 *
 * Arquivo JavaScript puro, carregado por importScripts no Web Worker e também
 * pelos testes em Node. Recebe pixels RGBA de um quadro já reduzido (~360 px).
 */

var AREA_MINIMA_RELATIVA = 0.12;
var CONTORNOS_AVALIADOS = 10;
var TOLERANCIA_APROXIMACAO = 0.02;

function ordenarCantos(pontos) {
  var cx = 0;
  var cy = 0;
  pontos.forEach(function (p) {
    cx += p.x / 4;
    cy += p.y / 4;
  });
  // Ordena pelo ângulo em volta do centro (sentido horário na tela) e começa pelo
  // ponto com menor x + y: superior esquerdo, superior direito, inferior direito, inferior esquerdo.
  var horario = pontos.slice().sort(function (a, b) {
    return Math.atan2(a.y - cy, a.x - cx) - Math.atan2(b.y - cy, b.x - cx);
  });
  var inicio = 0;
  horario.forEach(function (p, i) {
    if (p.x + p.y < horario[inicio].x + horario[inicio].y) inicio = i;
  });
  return horario.slice(inicio).concat(horario.slice(0, inicio));
}

/**
 * @returns {{cantos: {x:number,y:number}[], area: number} | null} cantos normalizados (0..1)
 */
function detectarCantosCv(cv, pixels, largura, altura) {
  var mats = [];
  function guardar(mat) {
    mats.push(mat);
    return mat;
  }
  try {
    var rgba = guardar(cv.matFromImageData({ data: pixels, width: largura, height: altura }));
    var cinza = guardar(new cv.Mat());
    cv.cvtColor(rgba, cinza, cv.COLOR_RGBA2GRAY);
    var suavizada = guardar(new cv.Mat());
    cv.GaussianBlur(cinza, suavizada, new cv.Size(5, 5), 0);
    var bordas = guardar(new cv.Mat());
    cv.Canny(suavizada, bordas, 50, 150);
    // Fechamento morfológico: une bordas quebradas quando a folha está sobre fundo claro.
    var nucleo = guardar(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(5, 5)));
    var fechadas = guardar(new cv.Mat());
    cv.morphologyEx(bordas, fechadas, cv.MORPH_CLOSE, nucleo, new cv.Point(-1, -1), 2);

    var contornos = new cv.MatVector();
    var hierarquia = guardar(new cv.Mat());
    cv.findContours(fechadas, contornos, hierarquia, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE);

    var candidatos = [];
    for (var i = 0; i < contornos.size(); i++) {
      var contorno = contornos.get(i);
      candidatos.push({ indice: i, area: cv.contourArea(contorno) });
      contorno.delete();
    }
    candidatos.sort(function (a, b) {
      return b.area - a.area;
    });

    var areaMinima = AREA_MINIMA_RELATIVA * largura * altura;
    var resultado = null;
    for (var j = 0; j < Math.min(CONTORNOS_AVALIADOS, candidatos.length); j++) {
      if (candidatos[j].area < areaMinima) break;
      var atual = contornos.get(candidatos[j].indice);
      var aproximado = new cv.Mat();
      cv.approxPolyDP(atual, aproximado, TOLERANCIA_APROXIMACAO * cv.arcLength(atual, true), true);
      var convexo = aproximado.rows === 4 && cv.isContourConvex(aproximado);
      if (convexo) {
        var pontos = [];
        for (var k = 0; k < 4; k++) {
          pontos.push({
            x: Math.min(1, Math.max(0, aproximado.data32S[k * 2] / (largura - 1))),
            y: Math.min(1, Math.max(0, aproximado.data32S[k * 2 + 1] / (altura - 1))),
          });
        }
        resultado = { cantos: ordenarCantos(pontos), area: candidatos[j].area / (largura * altura) };
      }
      aproximado.delete();
      atual.delete();
      if (resultado) break;
    }
    contornos.delete();
    return resultado;
  } finally {
    mats.forEach(function (m) {
      m.delete();
    });
  }
}

if (typeof module === "object" && module.exports) {
  module.exports = { detectarCantosCv: detectarCantosCv, ordenarCantos: ordenarCantos };
}
