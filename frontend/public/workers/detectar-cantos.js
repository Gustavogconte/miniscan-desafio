/*
 * Detecção dos 4 cantos da folha com OpenCV.js — o mesmo algoritmo do backend
 * (backend/app/visao/bordas.py), rodando no navegador para o recorte ao vivo.
 *
 * 1. Candidatos por três caminhos: Canny normal, Canny sensível (bordas fracas,
 *    mesa clara) e segmentação pelo brilho do papel (Otsu).
 * 2. Cada contorno vira um quadrilátero pela envoltória convexa; se ela tiver mais
 *    de 4 lados (dedo no canto, canto dobrado, papel ondulado), os 4 lados mais
 *    longos são prolongados até se cruzarem, recuperando o canto escondido.
 * 3. Vence o maior candidato com borda contínua nos 4 lados, medindo só o
 *    gradiente perpendicular a cada lado (descarta o bloco de texto).
 *
 * Arquivo JavaScript puro, carregado por importScripts no Web Worker e também
 * pelos testes em Node. Recebe pixels RGBA de um quadro já reduzido (~360 px).
 */

var AREA_MINIMA_RELATIVA = 0.1;
var CONTORNOS_POR_ESTRATEGIA = 6;
var LIMIARES_CANNY = [
  [50, 150],
  [20, 60],
];
var TOLERANCIAS_APROXIMACAO = [0.01, 0.015, 0.02, 0.03, 0.04, 0.05];
var GRADIENTE_MINIMO = 8;
var APOIO_MINIMO = 0.7;
var BUSCA_PERPENDICULAR = 3;
var MARGEM_DOS_CANTOS = 0.12;
var CRESCIMENTO_MAXIMO = 1.35;
var AMOSTRAS_POR_LADO = 60;

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

function areaPoligono(pontos) {
  var soma = 0;
  for (var i = 0; i < pontos.length; i++) {
    var a = pontos[i];
    var b = pontos[(i + 1) % pontos.length];
    soma += a.x * b.y - b.x * a.y;
  }
  return Math.abs(soma) / 2;
}

function ehConvexo(pontos) {
  var sinal = 0;
  for (var i = 0; i < pontos.length; i++) {
    var a = pontos[i];
    var b = pontos[(i + 1) % pontos.length];
    var c = pontos[(i + 2) % pontos.length];
    var cruzado = (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x);
    if (Math.abs(cruzado) < 1e-9) continue;
    var atual = cruzado > 0 ? 1 : -1;
    if (sinal === 0) sinal = atual;
    else if (atual !== sinal) return false;
  }
  return sinal !== 0;
}

function pontosDoMat(mat) {
  var pontos = [];
  for (var i = 0; i < mat.rows; i++) pontos.push({ x: mat.data32S[i * 2], y: mat.data32S[i * 2 + 1] });
  return pontos;
}

/** Ponto onde a reta p1-p2 cruza a reta p3-p4 (null se forem quase paralelas). */
function intersecao(p1, p2, p3, p4) {
  var d1x = p2.x - p1.x;
  var d1y = p2.y - p1.y;
  var d2x = p4.x - p3.x;
  var d2y = p4.y - p3.y;
  var denominador = d1x * d2y - d1y * d2x;
  if (Math.abs(denominador) < 1e-6 * Math.hypot(d1x, d1y) * Math.hypot(d2x, d2y)) return null;
  var t = ((p3.x - p1.x) * d2y - (p3.y - p1.y) * d2x) / denominador;
  return { x: p1.x + t * d1x, y: p1.y + t * d1y };
}

/** Prolonga os 4 lados mais longos do polígono até se cruzarem (recupera cantos escondidos). */
function quatroLadosMaisLongos(poligono) {
  var n = poligono.length;
  var indices = [];
  for (var i = 0; i < n; i++) indices.push(i);
  var comprimento = function (i) {
    var a = poligono[i];
    var b = poligono[(i + 1) % n];
    return Math.hypot(b.x - a.x, b.y - a.y);
  };
  var escolhidos = indices
    .sort(function (a, b) {
      return comprimento(b) - comprimento(a);
    })
    .slice(0, 4)
    .sort(function (a, b) {
      return a - b;
    });
  var cantos = [];
  for (var k = 0; k < 4; k++) {
    var a = escolhidos[k];
    var b = escolhidos[(k + 1) % 4];
    var ponto = intersecao(poligono[a], poligono[(a + 1) % n], poligono[b], poligono[(b + 1) % n]);
    if (!ponto) return null;
    cantos.push(ponto);
  }
  return cantos;
}

function quadrilatero(cv, contorno) {
  var envoltoria = new cv.Mat();
  var aproximado = new cv.Mat();
  try {
    cv.convexHull(contorno, envoltoria, false, true);
    var areaEnvoltoria = cv.contourArea(envoltoria);
    var perimetro = cv.arcLength(envoltoria, true);
    for (var i = 0; i < TOLERANCIAS_APROXIMACAO.length; i++) {
      cv.approxPolyDP(envoltoria, aproximado, TOLERANCIAS_APROXIMACAO[i] * perimetro, true);
      var poligono = pontosDoMat(aproximado);
      if (poligono.length < 4) return null;
      var quad = poligono.length === 4 ? poligono : quatroLadosMaisLongos(poligono);
      if (!quad || !ehConvexo(quad)) continue;
      var area = areaPoligono(quad);
      if (area >= areaEnvoltoria * 0.9 && area <= areaEnvoltoria * CRESCIMENTO_MAXIMO) return quad;
    }
    return null;
  } finally {
    envoltoria.delete();
    aproximado.delete();
  }
}

/** Fração de pontos com borda perpendicular forte, no lado mais fraco do quadrilátero. */
function apoioDeBorda(quad, gx, gy, largura, altura) {
  var menor = 1;
  for (var i = 0; i < 4; i++) {
    var a = quad[i];
    var b = quad[(i + 1) % 4];
    var dx = b.x - a.x;
    var dy = b.y - a.y;
    var tamanho = Math.hypot(dx, dy) + 1e-6;
    var nx = -dy / tamanho;
    var ny = dx / tamanho;
    var fortes = 0;
    for (var s = 0; s < AMOSTRAS_POR_LADO; s++) {
      var t = MARGEM_DOS_CANTOS + ((1 - 2 * MARGEM_DOS_CANTOS) * s) / (AMOSTRAS_POR_LADO - 1);
      var bx = a.x + t * dx;
      var by = a.y + t * dy;
      var intensidade = 0;
      for (var d = -BUSCA_PERPENDICULAR; d <= BUSCA_PERPENDICULAR; d++) {
        var x = Math.min(largura - 1, Math.max(0, Math.round(bx + d * nx)));
        var y = Math.min(altura - 1, Math.max(0, Math.round(by + d * ny)));
        var indice = y * largura + x;
        intensidade = Math.max(intensidade, Math.abs(gx[indice] * nx + gy[indice] * ny));
      }
      if (intensidade > GRADIENTE_MINIMO) fortes++;
    }
    menor = Math.min(menor, fortes / AMOSTRAS_POR_LADO);
  }
  return menor;
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

    // Sobel 3x3 dividido por 4: aproximadamente a diferença de brilho através da borda.
    var matGx = guardar(new cv.Mat());
    var matGy = guardar(new cv.Mat());
    cv.Sobel(suavizada, matGx, cv.CV_32F, 1, 0, 3, 0.25);
    cv.Sobel(suavizada, matGy, cv.CV_32F, 0, 1, 3, 0.25);
    var gx = matGx.data32F;
    var gy = matGy.data32F;

    var nucleo = guardar(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(5, 5)));
    var nucleoGrande = guardar(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(15, 15)));
    var semPonto = new cv.Point(-1, -1);
    var mascaras = [];
    LIMIARES_CANNY.forEach(function (limiar) {
      var bordas = guardar(new cv.Mat());
      cv.Canny(suavizada, bordas, limiar[0], limiar[1]);
      cv.morphologyEx(bordas, bordas, cv.MORPH_CLOSE, nucleo, semPonto, 2);
      mascaras.push({ imagem: bordas, modo: cv.RETR_LIST });
    });
    // Papel é mais claro que quase toda mesa: Otsu separa a folha; o fechamento grande
    // preenche as linhas de texto para a folha virar uma mancha só.
    var claro = guardar(new cv.Mat());
    cv.threshold(suavizada, claro, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
    cv.morphologyEx(claro, claro, cv.MORPH_CLOSE, nucleoGrande);
    cv.morphologyEx(claro, claro, cv.MORPH_OPEN, nucleo);
    mascaras.push({ imagem: claro, modo: cv.RETR_EXTERNAL });

    var areaMinima = AREA_MINIMA_RELATIVA * largura * altura;
    var melhor = null;
    var melhorArea = 0;
    mascaras.forEach(function (mascara) {
      var contornos = new cv.MatVector();
      var hierarquia = new cv.Mat();
      cv.findContours(mascara.imagem, contornos, hierarquia, mascara.modo, cv.CHAIN_APPROX_SIMPLE);
      var lista = [];
      for (var i = 0; i < contornos.size(); i++) {
        var contorno = contornos.get(i);
        lista.push({ indice: i, area: cv.contourArea(contorno) });
        contorno.delete();
      }
      lista.sort(function (a, b) {
        return b.area - a.area;
      });
      lista.slice(0, CONTORNOS_POR_ESTRATEGIA).forEach(function (item) {
        var atual = contornos.get(item.indice);
        var envoltoria = new cv.Mat();
        cv.convexHull(atual, envoltoria, false, true);
        var areaEnvoltoria = cv.contourArea(envoltoria);
        envoltoria.delete();
        if (areaEnvoltoria >= areaMinima) {
          var quad = quadrilatero(cv, atual);
          if (quad) {
            var area = areaPoligono(quad);
            if (area > melhorArea && apoioDeBorda(quad, gx, gy, largura, altura) >= APOIO_MINIMO) {
              melhor = quad;
              melhorArea = area;
            }
          }
        }
        atual.delete();
      });
      contornos.delete();
      hierarquia.delete();
    });

    if (!melhor) return null;
    var normalizados = melhor.map(function (p) {
      return {
        x: Math.min(1, Math.max(0, p.x / (largura - 1))),
        y: Math.min(1, Math.max(0, p.y / (altura - 1))),
      };
    });
    return { cantos: ordenarCantos(normalizados), area: melhorArea / (largura * altura) };
  } finally {
    mats.forEach(function (m) {
      m.delete();
    });
  }
}

if (typeof module === "object" && module.exports) {
  module.exports = { detectarCantosCv: detectarCantosCv, ordenarCantos: ordenarCantos };
}
