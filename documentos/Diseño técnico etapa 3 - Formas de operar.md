# Documento 5: todas las formas de operar y los escenarios principales de la nueva Matriz Recorrido/Escenarios

## Contexto
**El objetivo no es optimizar la estrategia ni buscar la forma de hacerla rentable.** Es medir **todas las formas posibles de ejecutar tus señales registradas**, con argumentos basados en mediciones:
1. organizar todas las formas;
2. descartar, argumentando, las que no den resultados positivos o no den valor a la ejecución;
3. dejar, argumentando, las que generan valor y salen positivas;
4. **mostrarte las formas candidatas para que apruebes la nueva Matriz Recorrido/Escenarios**;
5. con la Matriz aprobada, hacer el nuevo recorrido de cada señal, con cada combinación, en cada escenario, y generar los entregables.

**Este plan cubre los pasos 1 a 4 y se detiene ahí.** El paso 5 se diseña y se ejecuta después de que apruebes la Matriz.

No se elige "la mejor". Cada forma se juzga por sus mediciones. Pueden quedar muchas candidatas, y que formas distintas den resultados positivos es un argumento de robustez.

**De tu tabla "Como opero":**
- **Se varían:** distancia operativa, tiempo de colocación, ventana de ejecución, deslizamiento de entrada y cierre por tiempo.
- **No se varían:** vela de confirmación, disparo por Last y deslizamiento de salida.

No soy asesor financiero: esto mide tus datos históricos.

## Tus respuestas
| Tema | Decisión |
|---|---|
| Columna **M** (A, B, LA, LM, LP) | La decides al ver la vela de confirmación o la anterior, así que **se usa como regla**: es información disponible antes de entrar. Nunca se ha analizado |
| Solapamiento | NinjaTrader compensa compra y venta en la misma cuenta ([foro NT](https://forum.ninjatrader.com/forum/ninjatrader-8/strategy-development/1229603-net-position)). Variantes: 1 posición (actual) y varias posiciones en la misma dirección (hasta 2, 3 o sin límite). La señal contraria se pierde mientras haya una posición abierta |
| Noticias | Las de impacto alto en USD (carpeta roja en ForexFactory, 3 estrellas en Investing). Las fechas de jul–oct 2026 se cargan en `entrada/calendario_noticias.csv` (fecha, hora de Nueva York, nombre, impacto) y **tú las revisas antes de medir**. Si las páginas no permiten la consulta automática, te pido exportarlas |

**Reglas de noticias a medir:**
- No operar el día con noticia de impacto alto.
- No operar de 5 minutos antes a 15 minutos después de la noticia.
- Noticias de las 8:30 (antes de la apertura) frente a las de las 10:00 (dentro de tu hora).

**Dato relacionado:** las 10:00 de Nueva York caen en el minuto 30 tras la apertura. Antes, operar solo del minuto 20 al 40 dio −290 USD. Se comprobará si las noticias lo explican.

## 1. Estado de tus 16 puntos
| # | Punto | Estado | Argumento que ya existe o qué falta |
|---|---|---|---|
| 1 | ATM fijo, breakeven o mover el SL | **Medido** | El fijo gana. El breakeven empeora en todos los cierres; el SL por tiempo, el trailing y el stop al cierre de vela, también. *Falta repetirlo con el escenario principal (9 minutos)* |
| 2 | Con o sin solapamiento | **Parcial** | Con solapamiento se pierden 246 señales. *Falta medir varias posiciones en la misma dirección* |
| 3 | ATM por zona, con y sin solapamiento | **Parcial** | Elegido con semanas no vistas perdió frente a un ATM único (−429 frente a +1.018). *Falta tu procedimiento exacto: la combinación de cada zona aplicada a todas las señales, con y sin solapamiento* |
| 4 | Dejar de operar zonas, o zonas en un Te | **Parcial** | Quitar Trend ≥ 2do Pivot y V empata. *Falta zona × Te* |
| 5 | ATM según indicador o según la semana | **Medido (no)** | 10 indicadores y los cambios semanales no mejoraron fuera de muestra. *Falta: columna M, adaptación dentro del día y TP proporcional* |
| 6 | Cierre por tiempo | **Medido** | 9 minutos, empate con 8; 5 minutos claramente peor |
| 7 | Distancia de la orden | **Medido** | 3 ticks; empata con 7 en el ATM fijo y gana fuera de muestra |
| 8 | Tiempo de colocación | **Medido** | Más rápido es mejor: 200 ms frente a 600 ms, +411 USD |
| 9 | Ventana de ejecución | **Parcial** | Acortarla no mejora. Alargarla no se puede medir por las señales borradas |
| 10 | Deslizamiento: evitarlo o ajustar SL/TP | **Parcial** | Pasar de 3 a 6 ticks cuesta 480 USD. *Falta: SL/TP medidos desde el precio de la orden o desde el de entrada, y límite de deslizamiento* |
| 11 | Stop límite frente a stop a mercado | **Pendiente** | El 98 % de las entradas se llenan justo al precio de la orden; se espera un efecto pequeño |
| 12 | Prioridad entre zonas simultáneas | **Pendiente** | Hay 12 pares que entran en el mismo instante, más las órdenes pendientes que compiten |
| 13 | Prioridad Buy o Sell | **Pendiente** | Mismo caso que el 12 |
| 14 | Noticias | **Pendiente** | Con el calendario de tus fuentes |
| 15 | Descartar Buy o Sell según el mercado | **Pendiente** | Columna M (por ejemplo, Buy en estructura bajista), tendencia en temporalidad mayor (5, 15 minutos o diaria) e indicadores |
| 16 | Vigilar cuándo una combinación pierde ventaja | **Pendiente** | Alarma estadística sobre la esperanza reciente y pausa por curva de resultados ([evidencia mixta](https://www.luxalgo.com/library/concept/equity-curve-based-throttling/)) |

## 2. Formas nuevas que propongo
| Forma | Qué responde |
|---|---|
| **ATM y filtros según la columna M**, y M × Tipo | Tu propia lectura del mercado como regla (puntos 5, 15 y 16) |
| Según el OHLC de la orden (High o Low frente a Close) | Si las órdenes sobre el cierre rinden distinto |
| No operar si la orden está lejos del cierre de la vela (30, 60, 90 ticks) | Las órdenes lejanas exigen más recorrido; la distancia se conoce antes de colocar |
| SL/TP medidos desde el precio de la orden en vez de desde el de entrada | Tu punto 10: compensar el deslizamiento |
| Cierre por tiempo condicionado: si a los 9 minutos va ganando, SL a la entrada y unos minutos más | Dejar correr las que ya van bien |
| TP proporcional a la volatilidad con SL fijo | "A veces da menos TP" |
| Adaptación dentro del día: las primeras señales del día fijan el ATM de las siguientes | Leer el mercado con tus propias señales |
| Dos ATM a la vez (2 contratos) | Repartir el riesgo entre épocas en vez de adivinar cuándo cambiar |
| Trailing por velas y salida ante una señal contraria de tu registro | Salidas por estructura |
| Separación mínima entre señales y tamaño por riesgo constante | Señales que se estorban; suavizar las caídas ([practicantes](https://algomatictrading.substack.com/p/why-volatility-adjusted-sizing-matters)) |

**No medibles con los datos actuales:**
- Entrar a mercado o antes de la orden, y alargar la ventana: faltan las señales que borrabas.
- Volatilidad implícita (VIX o VXN): requiere que la descargues.

## 3. Cómo se mide y se decide
**Las mismas mediciones para todas las formas**, para que los argumentos sean comparables:
- Reglas comunes: costos completos (comisión 1,86 USD, deslizamiento de entrada y SL − 2), tus 14 semanas y tus 703 señales.
- Lo que cambia en cada forma es solo lo que esa forma define. El resto queda como en el escenario de referencia actual: orden a ±3 ticks, 200 ms, cierre a 9 minutos y re-entrada de 60 ticks.
- Mediciones de cada forma:
  - **Dentro** (todas las semanas).
  - **Fuera de muestra** (elegir con 13 semanas y medir en la que falta, 14 veces).
  - **Las dos mitades.**
  - **Semanas positivas.**
  - **Combinaciones Vecinas** (cuando hay SL/TP).
  - **Comparación con 100 carteras al azar.**
  - **Diferencia con la referencia**, como dato informativo y no como criterio para elegir.

**Combinar reglas (tu "mapas con escenarios distintos"):** distancia (3–7) × colocación (100, 200, 300, 600 ms) × cierre (7–11 min) × zonas (todas / sin Trend ≥ 2do Pivot ni V) = 200 combinaciones de reglas, cada una medida igual.

**Estado de cada forma, con su argumento escrito en números:**

**Qué es "dar valor a la ejecución":** frente al escenario de referencia actual, la forma mejora al menos una de estas medidas sin empeorar con claridad el neto fuera de muestra:
- neto fuera de muestra;
- resultado de la segunda mitad;
- caída máxima;
- semanas positivas.

"Empeorar con claridad" significa que la diferencia semana a semana con la referencia, remuestreando las 14 semanas, queda toda por debajo de cero.

| Estado | Criterio | Qué significa |
|---|---|---|
| **Candidata a la Matriz principal** | Positiva fuera de muestra, positiva en **ambas** mitades, mejor que la mediana de las carteras al azar, **da valor** y **no depende de una época más que la referencia** (ver sección 8) | Genera resultados positivos con evidencia en semanas no vistas y aporta algo a la ejecución |
| **En observación** | Positiva fuera de muestra pero negativa en una mitad, no mejor que el azar o más dependiente de una época que la referencia | Da positivo, pero los datos no alcanzan; se revisa con semanas nuevas |
| **Descartada** | Negativa fuera de muestra; positiva pero sin dar valor; **requiere 2 cuentas**; o **medición con sesgo** (salir con la señal contraria) | No aporta a la ejecución o no se puede operar/medir bien; el argumento queda escrito con números |
| **No Aplica** | No es una decisión sino un costo (deslizamiento de entrada) | Muestra cuánto cambia el resultado |
| **No Medida** | Falta un dato (calendario de noticias, señales no ejecutadas que se borraban, VIX/VXN) | Se indica qué dato haría falta y cómo conseguirlo |

*(Estados actualizados en la sección 8; antes había "Sensibilidad", "Requiere 2 cuentas" y "No medible".)*

**Propuesta de Matriz (tu paso 4):** las formas Candidatas, agrupadas por lo que tienen en común. Por ejemplo: "ATM fijo con TP menor que el SL, cierre de 8 a 10 minutos, distancia de 3 a 5 ticks". Cada grupo es una **columna propuesta** de la nueva Matriz Recorrido/Escenarios, con sus argumentos. **Tú apruebas, cambias o quitas columnas** antes del paso 5.

## 4. Archivos (en `proyecto\salida\formas\`)
- `analisis_formas.xlsx`:
  - **Conclusiones:** una fila por cada uno de tus 16 puntos y por cada forma nueva, con la respuesta, el argumento con números y el estado (ver los 5 estados de la sección 3). También muestra la tabla de estado de los 16 puntos (medido, parcial, pendiente), actualizada.
  - Catálogo.
  - Mapa de escenarios.
  - Detalle por grupo: entrada, salida, selección, posición y adaptación.
  - Cómo leer.
- `propuesta_matriz.xlsx`: la Matriz Recorrido/Escenarios **propuesta**, con cada grupo de formas candidatas como columna, en el mismo formato que tu tabla, y una fila de argumentos por columna. Es lo que apruebas. Incluye además la pestaña **Matriz recomendada** (sección 8).
- `resumen_escenarios.xlsx`: todos los escenarios medidos en una sola tabla comparable, con su estado y su motivo (sección 8).

**Después de tu aprobación (paso 5, en un diseño aparte):** el nuevo recorrido de cada señal, con las 7.744 combinaciones, en cada escenario de la Matriz aprobada, con los mismos entregables del entregable principal (escenarios, zonas, semanas y análisis con conclusiones).

## 5. Código
- `simulador/formas.py` (nuevo): cada forma como salida, filtro, prioridad o posición. Reutiliza:
  - `simular_entrada` y `Escenario` (`medicion/entrada.py`);
  - `crear_operacion` y `fijo_minutos` (`simulador/operaciones.py`, `simulador/salidas.py`);
  - `tomar_sin_solape`, `semanal`, `fuera_de_muestra` y `combinaciones_vecinas` (`simulador/metricas.py`);
  - `aplicar` (`simulador/reglas_dia.py`) e `indicadores_serie` (`simulador/indicadores.py`);
  - las columnas y la pestaña Matriz de `simulador/principal_escenarios.py`.
- `simulador/estado_formas.py` (nuevo): aplica los criterios de estado y escribe el argumento de cada forma con sus números.
- `simulador/posiciones.py` (nuevo): N posiciones en la misma dirección y señal contraria perdida.
- `entrada/calendario_noticias.csv`: lo revisas antes de usarlo.
- `main.py`: comando `python main.py formas`. Lo existente no cambia.
- **Pruebas** de cada forma nueva, de los criterios de estado (casos Se queda, En observación y Descartada), de la prioridad entre señales simultáneas, de las posiciones múltiples y de que ningún filtro use datos posteriores a la señal.

## 6. Verificación
- La base del mapa reproduce los +3.775,64 USD del entregable principal.
- Una forma nueva recalculada a mano tick a tick.
- Todas las pruebas pasan.
- **Tiempo de ejecución estimado:** de 30 a 60 minutos.
- Commit y subida a tu GitHub al terminar, si lo apruebas entonces.

## 7. Riesgos
- Con 14 semanas, varias formas quedarán "En observación" porque los datos no alcanzan para afirmar ni descartar. Se dirá así, con el número de semanas que haría falta.
- Probar muchas formas hace que alguna salga positiva por azar. Por eso se exige ganar en semanas no vistas, en ambas mitades y frente al azar, y no solo en el total.
- Las formas de 2 contratos se marcan aparte, porque cambian el riesgo por operación.

## 8. Actualizaciones aprobadas después de la primera medición

### 8.1 Pestaña "Matriz recomendada" (`propuesta_matriz.xlsx`)
Sugerencia de 5 escenarios, cada uno con un mecanismo distinto, en el formato Recorrido/Escenarios, con sus métricas y el porqué de cada uno:

| Escenario | Forma del catálogo |
|---|---|
| E1 Referencia | ATM fijo (referencia) |
| E2 Stop al cierre de vela | Stop al cierre de vela |
| E3 Sin Buy en estructura bajista | No operar Buy en estructura bajista (B) |
| E4 Sin Trend ≥ 2do Pivot | Dejar de operar Trend ≥ 2do Pivot |
| E5 Corte temprano | Corte temprano: a los 4 min, si va 60 ticks o más en contra, salir |

Es una sugerencia: **la Matriz principal la aprueba el trader**. Si alguno de los 5 deja de ser Candidata, la pestaña lo avisa arriba ("Aviso") y en la fila Estado; no se cambia automáticamente. El comando `python main.py recomendada` reconstruye la pestaña desde el catálogo ya medido.

### 8.2 Archivo `resumen_escenarios.xlsx`
Una fila por escenario medido: las formas de operar del catálogo y las 200 combinaciones del mapa de reglas (325 en total).

| Columna | Qué significa |
|---|---|
| Escenario, Tipo, Descripción | Qué se midió y qué cambia frente a la referencia |
| Combinaciones positivas | De todas las combinaciones SL/TP (o parámetros) del escenario, cuántas ganaron en las 14 semanas |
| **Combinaciones + 2 mitades** | De todas las combinaciones, cuántas ganaron en las semanas 1–7 **y** en las 8–14 |
| Top 20 (ganancia, 1ª y 2ª mitad, positivas en ambas mitades, drawdown, operaciones, vecinas positivas) | Promedios de las 20 combinaciones de mayor ganancia en las 14 semanas. Es optimista: se eligen después de ver los resultados |
| Fuera de muestra (USD) | Se elige la combinación con 13 semanas (meseta 5 × 5) y se mide en la semana apartada, 14 veces; la suma de los 14 resultados. Es el número más honesto para comparar |
| Diferencia con la referencia (USD) | Fuera de muestra del escenario − Fuera de muestra de la referencia (+3.701,5). Informativa: no decide el estado |
| Estado | Uno de los 5 estados de la sección 3 |
| Por qué (motivo del estado) | El motivo con números. En las candidatas, aviso si es variante de otra (misma idea en una sola Te, mismos parámetros que la referencia, colocación más rápida, variantes del corte temprano) para no contarla dos veces |

Orden: Candidata, En observación, Descartada, No Aplica, No Medida; dentro de cada estado, por Fuera de muestra de mayor a menor. Se quitó la columna "Recomendación": el estado ya no depende de cuántos escenarios tenga la Matriz principal.

### 8.3 Criterio nuevo para Candidata: no depender de una época más que la referencia
Proporción = Combinaciones + 2 mitades ÷ Combinaciones positivas. Una forma es Candidata solo si su proporción **no es menor que la de la referencia** (28 %: 904 de 3.242). Si es menor, pasa a En observación con el motivo "depende más de una época".
- Se probó primero un umbral fijo del 50 %, pero la propia referencia no lo cumplía; el trader eligió el criterio relativo.
- Las formas sin tabla de combinaciones (ATM por grupo, por semana o dentro del día) no tienen esta proporción: el criterio no aplica y el motivo lo dice.

### 8.4 Estados especiales reasignados
| Caso | Antes | Ahora |
|---|---|---|
| Deslizamiento de entrada (0 a 6 ticks) | Sensibilidad | No Aplica |
| Un ATM por Zona Reacción sin solapamiento | Requiere 2 cuentas | Descartada (requiere 2 cuentas) |
| Salir con la señal contraria del registro | No medible | Descartada (sesgo) |
| Noticias de impacto alto (calendario vacío) | No medible | No Medida |
| Alargar la ventana de ejecución (fila nueva) | Solo en Conclusiones | No Medida (faltan señales no ejecutadas) |
| Entrar a mercado o antes de la orden (fila nueva) | Solo en Conclusiones | No Medida (faltan señales no ejecutadas) |
| ATM o filtro según VIX/VXN (fila nueva) | Solo en Conclusiones | No Medida (falta descargar la serie) |

### 8.5 Resultado de la medición con los criterios actuales
| Estado | Formas de operar | Mapa de reglas |
|---|---|---|
| Candidata a la Matriz principal | 10 | 47 |
| En observación | 26 | 21 |
| Descartada | 79 | 132 |
| No Aplica | 6 | — |
| No Medida | 4 | — |

Formas candidatas: la referencia; dejar de operar Trend ≥ 2do Pivot (y su variante en Te 1); stop al cierre de vela; dejar de operar I. Fuerte (y su variante en Te 1); dejar de operar 1er Vela en Te 1; pausa si las últimas 20 operaciones suman negativo; no operar si la orden está a más de 30 o de 90 ticks del cierre de la vela. E3 y E5 de la Matriz recomendada quedan En observación (23 % y 22 % frente al 28 % de la referencia).

### 8.6 Código
- `simulador/estado_formas.py`: estados `CANDIDATA`, `OBSERVACION`, `DESCARTADA`, `NO_APLICA`, `NO_MEDIDA`; `proporcion_ambas` y `consistencia` (criterio 8.3) dentro de `decidir`.
- `simulador/formas.py`: `resumen_top` cuenta `ambas_todas`; estados forzados reasignados; `Catalogo.no_medidas` agrega las 3 filas nuevas.
- `simulador/resumen_escenarios.py`: tabla y "Cómo leer el resumen".
- `simulador/matriz_recomendada.py`: pestaña Matriz recomendada y aviso de no candidatas.
- Pruebas: `tests/test_formas.py`, `tests/test_resumen_escenarios.py`, `tests/test_matriz_recomendada.py`.
- Tiempo real de `python main.py formas`: unos 10 minutos.

### 8.7 Grupos de escenarios y combinaciones utilizables
Muchas filas del resumen son variantes de la misma idea (mesetas). Para contar **ideas** y no filas al armar la Matriz principal:

**Columna "Grupo"** en "Resumen escenarios". Se asigna por reglas fijas sobre el nombre (`resumen_escenarios.grupo`):

| Escenarios | Grupo |
|---|---|
| "ATM fijo (referencia)" y las filas del mapa con zonas "Todas" | Referencia y su meseta |
| Filas del mapa "Sin Trend ≥ 2do Pivot ni V" y "Dejar de operar Trend ≥ 2do Pivot y V" | Sin Trend ≥ 2do Pivot ni V y su meseta |
| "Dejar de operar X" y sus variantes "en Te 1/2" | Dejar de operar X |
| Variantes de parámetros de un mismo mecanismo (corte temprano, cierre condicionado, breakeven, stop límite, varias posiciones, separación mínima, órdenes lejanas, pausa, ATM por zona, prioridad, ventana, deslizamiento) | Un grupo por mecanismo |
| El resto (incluidos los filtros por indicador y por columna M, que quitan señales distintas) | Su propio nombre |

**Pestaña "Grupos":** una fila por idea con:
- escenarios por estado;
- Fuera de muestra mínimo y máximo;
- % de positivas que ganan en ambas mitades;
- mejor escenario;
- y tres columnas de combinaciones:
  - **Combinaciones utilizables:** las combinaciones SL/TP (o de parámetros) que ganan en el total, en ambas mitades **y en cada mes** en **todos los escenarios Candidata del grupo**. Es la zona de ATM que funciona venga la variante que venga. Si el grupo no tiene candidatas o sus candidatas no tienen tabla de combinaciones, "No aplica".
  - **Combinación de referencia del grupo:** de las utilizables, la de mayor neto mínimo entre los escenarios del grupo, con cuántas de sus vecinas en la cuadrícula SL × TP también son utilizables.
  - **Elecciones fuera de muestra dentro de la zona:** de las combinaciones elegidas sin ver cada semana (14 por candidata), cuántas caen dentro de la zona. Es la prueba de que la zona no es solo optimismo de mirar las 14 semanas.

**Meses:** cada semana (lunes a viernes) va al mes de su miércoles:
- julio: 29 jun – 31 jul (5 semanas);
- agosto: 3 – 28 ago (4 semanas);
- septiembre: 31 ago – 2 oct (5 semanas).

**Pestaña "Combinaciones utilizables":** una fila por **combinación utilizable × escenario candidato de su grupo**. La combinación se repite en cada escenario candidato de su grupo, siempre con los resultados de **ese** escenario. Columnas:
- Grupo y Escenario;
- SL y TP, en ticks y en USD; las formas con otra tabla de parámetros, como "Stop al cierre de vela", llevan la columna "Parámetro" en su lugar;
- las columnas del entregable principal (`COLUMNAS_20`: Ganancia Neta, Profit Factor, Drawdown…);
- la 1ª y la 2ª mitad, y cada mes.

Va ordenada por grupo (como en la pestaña Grupos), luego por escenario (Fuera de muestra de mayor a menor) y luego por Ganancia Neta. Para ver una combinación en todos los escenarios de su grupo, se filtra por SL y TP.

**Límite:** una meseta o una zona es un argumento de robustez a los parámetros con los mismos datos. No prueba que la idea funcione en semanas nuevas.

**Código:**
- `formas.resumen_top` guarda por combinación el neto total, por mitad y por mes, sus etiquetas y las elecciones fuera de muestra (`por_combinacion`).
- `formas.meses_de_semanas` asigna cada semana a su mes.
- `formas.consistente` marca las combinaciones que ganan en el total, en las mitades y en cada mes de un escenario.
- `_columnas_consistentes` guarda las columnas del entregable solo de esas combinaciones. Solo ellas pueden ser utilizables, así que se ahorra memoria. Revision Invalida y No Ejecutadas salen de las mediciones de cada escenario.
- `resumen_escenarios.grupo`, `utilizables` y `tabla_grupos` arman las pestañas.
- Pruebas en `tests/test_grupos.py`.
