/*
 * Detecção dos 4 cantos da folha com OpenCV.js — o mesmo algoritmo do backend
 * (backend/app/visao/bordas.py), rodando no navegador para o recorte ao vivo.
 *
 * 1. Candidatos pelo brilho (Canny normal, Canny sensível e Otsu: o papel é claro)
 *    e pela cor (Canny e Otsu na saturação: o papel é pouco saturado), o que resolve
 *    mesa ocre, bege ou madeira clara quase do mesmo brilho do papel.
 * 2. Cada contorno vira um quadrilátero pela envoltória convexa; se ela tiver mais
 *    de 4 lados (dedo no canto, canto dobrado, papel ondulado), os 4 lados mais
 *    longos são prolongados até se cruzarem, recuperando o canto escondido.
 * 3. Vence o maior candidato com borda contínua nos 4 lados, medindo só o
 *    gradiente perpendicular a cada lado (descarta o bloco de texto), somando brilho
 *    e cor, com limiar que sobe em superfícies muito texturizadas.
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
var APOIO_MINIMO = 0.8;
var BUSCA_PERPENDICULAR = 4;
var FATOR_RUIDO = 2;
var MARGEM_DOS_CANTOS = 0.12;
var CRESCIMENTO_MAXIMO = 1.35;
// Continuidade no vídeo: um candidato perto da folha do quadro anterior é preferido
// e precisa de menos apoio de borda para continuar valendo, o que evita o contorno
// "pular" para outro objeto num quadro ruim (desfoque, reflexo, exposição).
var DISTANCIA_CONTINUIDADE = 0.06;
var APOIO_PARA_MANTER = 0.6;
var BONUS_CONTINUIDADE = 1.3;

function distanciaMaxima(a, b) {
  var maior = 0;
  for (var i = 0; i < 4; i++) maior = Math.max(maior, Math.hypot(a[i].x - b[i].x, a[i].y - b[i].y));
  return maior;
}
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

/**
 * Fração de pontos com borda perpendicular forte, no lado mais fraco do quadrilátero.
 * `campos` são os gradientes {gx, gy} do brilho e da saturação, somados em cada ponto.
 */
function apoioDeBorda(quad, campos, largura, altura, limiar) {
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
        var soma = 0;
        for (var c = 0; c < campos.length; c++) {
          soma += Math.abs(campos[c].gx[indice] * nx + campos[c].gy[indice] * ny);
        }
        intensidade = Math.max(intensidade, soma);
      }
      if (intensidade > limiar) fortes++;
    }
    menor = Math.min(menor, fortes / AMOSTRAS_POR_LADO);
  }
  return menor;
}

/**
 * @returns {{cantos: {x:number,y:number}[], area: number} | null} cantos normalizados (0..1)
 */
/**
 * @param anterior cantos normalizados da folha no quadro anterior (opcional), para dar
 *   continuidade no vídeo.
 */
function detectarCantosCv(cv, pixels, largura, altura, anterior) {
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

    // Saturação (HSV): o papel é pouco saturado; madeira, ocre e bege são mais.
    var rgb = guardar(new cv.Mat());
    cv.cvtColor(rgba, rgb, cv.COLOR_RGBA2RGB);
    var hsv = guardar(new cv.Mat());
    cv.cvtColor(rgb, hsv, cv.COLOR_RGB2HSV);
    var canaisHsv = new cv.MatVector();
    cv.split(hsv, canaisHsv);
    var saturacaoBruta = canaisHsv.get(1);
    var saturacao = guardar(new cv.Mat());
    cv.GaussianBlur(saturacaoBruta, saturacao, new cv.Size(5, 5), 0);
    saturacaoBruta.delete();
    canaisHsv.delete();

    // Sobel 3x3 dividido por 4: aproximadamente a diferença através da borda.
    var campos = [suavizada, saturacao].map(function (canal) {
      var gxMat = guardar(new cv.Mat());
      var gyMat = guardar(new cv.Mat());
      cv.Sobel(canal, gxMat, cv.CV_32F, 1, 0, 3, 0.25);
      cv.Sobel(canal, gyMat, cv.CV_32F, 0, 1, 3, 0.25);
      return { gx: gxMat.data32F, gy: gyMat.data32F };
    });

    // Limiar relativo à textura da própria foto (mediana do gradiente, amostrada):
    // numa superfície muito texturizada, qualquer quadrilátero teria "borda" em todo lado.
    var magnitudes = [];
    for (var p = 0; p < largura * altura; p += 7) {
      var m = 0;
      for (var c = 0; c < campos.length; c++) m += Math.hypot(campos[c].gx[p], campos[c].gy[p]);
      magnitudes.push(m);
    }
    magnitudes.sort(function (a, b) {
      return a - b;
    });
    var limiar = Math.max(GRADIENTE_MINIMO, FATOR_RUIDO * magnitudes[Math.floor(magnitudes.length / 2)]);

    var nucleo = guardar(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(5, 5)));
    var nucleoGrande = guardar(cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(15, 15)));
    var semPonto = new cv.Point(-1, -1);
    var mascaras = [];
    var cannys = LIMIARES_CANNY.map(function (l) {
      return { canal: suavizada, limiares: l };
    }).concat([{ canal: saturacao, limiares: LIMIARES_CANNY[1] }]);
    cannys.forEach(function (item) {
      var bordas = guardar(new cv.Mat());
      cv.Canny(item.canal, bordas, item.limiares[0], item.limiares[1]);
      cv.morphologyEx(bordas, bordas, cv.MORPH_CLOSE, nucleo, semPonto, 2);
      mascaras.push({ imagem: bordas, modo: cv.RETR_LIST });
    });
    // Papel é mais claro que quase toda mesa (Otsu no brilho) e menos saturado que mesa
    // de madeira, ocre ou bege (Otsu invertido na saturação). O fechamento grande
    // preenche as linhas de texto para a folha virar uma mancha só.
    [
      { canal: suavizada, tipo: cv.THRESH_BINARY },
      { canal: saturacao, tipo: cv.THRESH_BINARY_INV },
    ].forEach(function (item) {
      var mancha = guardar(new cv.Mat());
      cv.threshold(item.canal, mancha, 0, 255, item.tipo + cv.THRESH_OTSU);
      cv.morphologyEx(mancha, mancha, cv.MORPH_CLOSE, nucleoGrande);
      cv.morphologyEx(mancha, mancha, cv.MORPH_OPEN, nucleo);
      mascaras.push({ imagem: mancha, modo: cv.RETR_EXTERNAL });
    });

    var areaMinima = AREA_MINIMA_RELATIVA * largura * altura;
    var melhor = null;
    var melhorArea = 0;
    var melhorNota = 0;
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
            var continua =
              anterior &&
              distanciaMaxima(
                ordenarCantos(
                  quad.map(function (p) {
                    return { x: p.x / (largura - 1), y: p.y / (altura - 1) };
                  }),
                ),
                anterior,
              ) < DISTANCIA_CONTINUIDADE;
            var nota = area * (continua ? BONUS_CONTINUIDADE : 1);
            var apoioMinimo = continua ? APOIO_PARA_MANTER : APOIO_MINIMO;
            if (nota > melhorNota && apoioDeBorda(quad, campos, largura, altura, limiar) >= apoioMinimo) {
              melhor = quad;
              melhorArea = area;
              melhorNota = nota;
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
