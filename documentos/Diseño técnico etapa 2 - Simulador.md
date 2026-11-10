# Etapa 2, propuesta 2: Simulador de combinaciones (diseño técnico, versión 5)

## Conclusión
Tus cuatro entregables quedan como los pides:
- Sin embudo.
- **7.744 combinaciones**: SL y TP de 10 a 140,5 USD cada 1,5.
- Tus 19 columnas.
- Zonas sin solapamiento.
- Indicadores que puedes ver en NinjaTrader y que calcularé igual que tu gráfico, para que leas el valor en vivo y sepas qué combinación le corresponde.

Son mediciones históricas de tus señales. No soy asesor financiero con licencia; la pregunta 8 se responde con niveles de evidencia, no como recomendación de operar con dinero real.

## 1. Decisiones de esta versión

| Tema | Decisión |
|---|---|
| Combinaciones | De 20 a 281 ticks cada 3 ticks, es decir de 10 a 140,5 USD cada 1,5: 88 × 88 = 7.744 |
| Cierre por tiempo | En velas (3 a 10), como tu regla. En Te 2, 4 velas son 8 minutos. Archivos `..._cierre_4_velas` |
| Semanas | 14 pestañas, porque tus datos tienen 14 semanas (del 29-jun al 28-sep), no 10 |
| Zonas | **Sin solapamiento**: cada zona se mide sola para ver qué combinaciones le van mejor. Las de menos de 30 señales llevan la marca "Poca muestra" |
| Semanas y todas las zonas juntas | Con solapamiento, porque ahí sí se juntan las zonas |
| Horario del gráfico | 24 horas (ETH), el que NinjaTrader asigna por defecto a los índices del CME cuando el campo dice "Use instrument settings". Lo comprobaremos con tus valores |

## 2. Reglas de la simulación (aprobadas antes, sin cambios)
- **Entrada:** el motor verificado, en los 4 escenarios.
- **Solapamiento:** cuando aplica, la señal se pierde solo si sigues dentro de otra operación cuando el precio llega a la orden.
- **TP:** primer tick que pasa TP + 2 ticks; sale al precio TP.
- **SL:** sale al precio del tick que lo dispara −2 ticks.
- **Cierre por tiempo:** la vela de entrada es la primera; sale con el primer tick en o después del cierre de la vela K, −2 ticks.
- **Comisión:** 1,86 USD.
- **Entrada a mercado:** excluida hasta tener señales registradas sin borrar.

## 3. Entregables (en `salida\combinaciones\`)

**Columnas de todas las pestañas de los entregables 1 a 3:**
- Las que identifican la combinación: SL (ticks), TP (ticks), SL (USD), TP (USD).
- Tus 19: Revision Invalida, No Ejecutadas, Hora Entrada, Ventana Ejecucion, Ganancia Neta, Esperanza Matematica, Profit Factor, Win Rate, Payoff Ratio, Drawdown, Recovery Factor, Trades +, Trades −, Racha Max. (Trades −), Racha Max. (Dias −), Trades (Solapamiento), $ Peor Dia, Fecha Peor Dia, Prom. Tiempo Abierta.

**Definiciones:**
- Drawdown: la mayor caída del neto acumulado, por orden de cierre.
- Recovery Factor: Ganancia Neta / Drawdown.
- Payoff Ratio: ganancia media / pérdida media.
- Win Rate: porcentaje de operaciones con neto > 0.
- Racha de días: días seguidos con neto negativo.
- Hora Entrada y Ventana Ejecucion: promedios de las operaciones tomadas.
- Trades (Solapamiento): queda en 0 en las pestañas por zona.

### Entregable 1: `combinaciones_todas_cierre_4_velas.xlsx`
4 pestañas (Escenario 1 a 4) × 7.744 filas. Cierre a 4 velas, con solapamiento.

### Entregable 2: `combinaciones_zonas_cierre_4_velas.xlsx`
10 pestañas, una por Zona Reacción, × 7.744 filas. Escenario 1, cierre a 4 velas, sin solapamiento.

### Entregable 3: `combinaciones_semanas_cierre_4_velas.xlsx`
14 pestañas, una por semana (lunes a viernes), × 7.744 filas. Escenario 1, cierre a 4 velas. Añade:
- **Indicadores por señal:** una fila por señal ejecutada, con su semana y el valor de cada indicador al cierre de la vela de confirmación, que es lo que ves al decidir.
- **Resumen semanal:** promedio de cada indicador por semana.

**Indicadores, todos de serie en NinjaTrader 8**, calculados en el gráfico de la señal (1 o 2 minutos), con horario ETH:

| Indicador en NinjaTrader | Qué mide para ti |
|---|---|
| Average True Range (ATR), períodos 5 y 10 | Tamaño reciente de las velas |
| Range | Tamaño de la vela de confirmación |
| Current Day OHL (High − Low) | Cuánto se ha movido ya el día |
| Prior Day OHLC (High − Low) | Cuánto se movió ayer |
| Choppiness Index (14) | Si el mercado va en tendencia o en rango |
| Average Directional Index, ADX (14) | Fuerza de la tendencia |
| Volume frente a VOLMA (20) | Si la vela trae más volumen de lo normal |
| Hora de la señal | Minutos desde la apertura, visibles en el reloj |

**Tu nota sobre el ATR en la apertura es correcta.** Con horario ETH, las velas previas a las 9:30 son de premercado, más tranquilas, y el ATR arranca bajo justo en la apertura. Lo trato así:
- Cada indicador se analiza por separado en las señales de las primeras 10 velas y en las posteriores, para que veas desde qué vela es fiable.
- Mido cuántas velas tarda el ATR(5) y el ATR(10) en reflejar la volatilidad de la apertura. Con su fórmula, el ATR(5) se adapta antes que el ATR(10).
- Como referencia, incluyo el ATR NY desde la apertura, que no tiene ese problema pero no viene en NinjaTrader. Si resulta claramente mejor, propondría crear un indicador sencillo para tu gráfico en otra etapa.

**Fórmula, igual a la de NinjaTrader:** el rango verdadero es el mayor entre máximo − mínimo y la distancia de cada uno al cierre anterior, suavizado al estilo Wilder con 1/período ([ayuda de NinjaTrader](https://ninjatrader.com/support/helpGuides/nt8/average_true_range_atr.htm)). Para que el valor de arranque no influya, se calcula desde el inicio de la sesión anterior. **Tus archivos de ticks traen las sesiones completas**: el programa construirá una sola vez las velas de 1 y 2 minutos de todo el día y las guardará para reutilizarlas.

### Entregable 4: `analisis_combinaciones.xlsx`
El simulador calcula también los cierres de 3 a 10 velas en los 4 escenarios. Aquí solo van resumidos.

| Pestaña | Responde |
|---|---|
| **Cómo leer** | Qué responde cada pestaña, con una fila real explicada |
| P1 Cierre por tiempo | Por escenario y cierre de 3 a 10 velas: combinaciones positivas, cuántas siguen positivas fuera de muestra, mediana de Esperanza, mejor zona de SL/TP; además Te 1 frente a Te 2 y Buy frente a Sell |
| P2 Cierre por zona | Lo mismo para cada Zona Reacción |
| P3 Cierre por semana | Lo mismo para cada semana |
| P3 Indicadores | Qué combinaciones convienen según el valor de cada indicador (sección 4) |
| P4 Escenarios | Positivas por escenario; 3 frente a 7 ticks; retraso de 300 a 700 ms; deslizamiento de 3 a 6; por cierre |
| P5 Breakeven | Con y sin breakeven (+40, +60, +80, +100) para cada cierre: positivas, Esperanza, % cerradas en breakeven y respuesta sí o no con su porqué |
| P6 SL por tiempo | Lo mismo con el SL que se acerca al cierre de cada vela |
| P7 Reglas del día | Límite de pérdida y de ganancia diaria, máximo de operaciones, ventanas de horario y dejar de operar zonas, frente a la base |
| P8 Recomendación | Todas las formas medidas, con nivel Candidata, Confirmada o Validada, y las combinaciones candidatas |
| Ratios | Resultado con TP/SL < 1, = 1 y > 1 (objetivo de tu documento 1) |
| Otras salidas | Salida parcial con 2 contratos, trailing, stop por cierre de vela, salir si no reacciona |
| Por qué cambian los días | Qué indicadores anticipan el MFE y el MAE pre MFE |
| Validación | Agrupaciones falsas, PBO, contra el azar y contra la operación inversa |

**"Cuál es mejor" en P1 a P7:** número de combinaciones positivas, como pides, y además cuántas siguen positivas en semanas no usadas para elegirlas.

## 4. Pregunta 3: cómo medir indicadores contra combinaciones
1. **Relación:** cuánto se relaciona cada indicador con el MFE y el MAE pre MFE, por señal y por semana. Responde si anticipa el tamaño del recorrido.
2. **Tramos en las unidades que ves en NinjaTrader:**
   - Por ejemplo, "ATR(10) entre 20 y 30 puntos".
   - Tres tramos por indicador, con cortes calculados solo con semanas de entrenamiento.
   - Para cada tramo: la mejor zona de SL/TP y su Esperanza.
   - Es tu ejemplo: "el indicador muestra X, mejor esta combinación".
3. **Prueba fuera de muestra:**
   - Se elige el ATM de cada tramo con 13 semanas y se prueba en la que falta, 14 veces.
   - Se compara con usar un solo ATM y con tramos inventados al azar.
   - El indicador "sirve para elegir" solo si gana a ambos.

**Investigación:**
- Adaptar parámetros según el mercado existe como método ([Chan](https://epchan.blogspot.com/2021/04/conditional-parameter-optimization.html)).
- Las fuentes advierten del riesgo de sobreajustar el filtro y piden fijarlo antes de probar ([walk-forward](https://nexusfi.com/a/automation/walk-forward-analysis), [protocolo](https://arxiv.org/pdf/2603.09219)).
- No encontré estudios serios de ATR contra stops fijos en futuros intradía.

## 5. Base de evidencia preliminar (ya revisada contigo)
- Un ATM fijo dio fuera de muestra unos +1.870 USD (PF 1,14), casi todo en las primeras 7 semanas.
- Salida parcial y SL por tiempo fueron las mejores gestiones; breakeven, trailing y entrada límite empeoraron.
- Límite de pérdida diaria de 50 USD y saltar días con salto grande al abrir mejoraron la estabilidad. Son candidatas entre 35 reglas.
- Elegir ATM por zona o por ATR sube el resultado mirando atrás, pero no en semanas no vistas.

## 6. Código
```
proyecto\
  main.py                     comando: python main.py simular
  config.py                   cuadrícula, cierres 3–10, gestiones, reglas, indicadores, nombres de archivos
  simulador\velas_sesion.py   velas de 1 y 2 min de la sesión completa (se guardan una vez)
  simulador\indicadores.py    ATR, Range, Current Day OHL, Prior Day OHLC, Choppiness, ADX, VOLMA
  simulador\salidas.py        SL/TP, cierre por tiempo, breakeven, SL por tiempo, salidas extra
  simulador\metricas.py       solapamiento y tus 19 columnas
  simulador\reglas_dia.py     límites diarios, horarios y zonas
  simulador\validacion.py     fuera de muestra, agrupaciones falsas, PBO, azar e inversa
  simulador\analisis.py       pestañas del entregable 4
  simulador\reportes.py       los 4 archivos
  tests\test_simulador.py
```
- **Reutiliza:** `simular_entrada`, `cargar_dia`, el lector de archivos de ticks de la etapa 1, `_ejecutar_validacion` y `_medir_senal`.
- **Tiempo estimado:** de 10 a 20 minutos la primera vez, y menos después, porque las velas de sesión quedan guardadas.

## 7. Pruebas
- Cada salida con casos a mano y ticks que saltan.
- Cierre exacto en Te 1 y Te 2.
- Solapamiento sí o no, según el entregable.
- Las 19 columnas con un caso a mano.
- Fórmulas de ATR, Choppiness y ADX comparadas con casos conocidos.
- Que ningún indicador use velas posteriores a la confirmación.
- Que al elegir no se use la semana calificada.
- Igual resultado en compra y venta.

## 8. Decisiones que apruebas
1. Los 4 entregables de la sección 3, con 7.744 combinaciones.
2. Cierre en velas (3 a 10) y nombres `..._cierre_4_velas`.
3. Zonas sin solapamiento; semanas y todas las zonas con solapamiento.
4. Indicadores de NinjaTrader de la sección 3, en horario ETH, más el ATR NY como referencia.
5. Método de 3 pasos de la sección 4.

## 9. Verificación
- Mismas ejecuciones que MFE/MAE: 692 / 670 / 680 / 692.
- Una combinación reproducida a mano tick a tick.
- **Comparas en NinjaTrader** el ATR(5), ATR(10), Choppiness y ADX de 3 señales con los valores del archivo. Si no coinciden, primero se revisa el horario del gráfico.
- La suma de las 10 pestañas de zonas cuadra con la medición sin solapamiento.
- Pruebas nuevas y las 150 existentes.

## 10. Riesgo y siguiente paso
- **14 semanas no bastan para confirmar:** se reporta con niveles de evidencia.
- **En paralelo:** dejar de borrar señales no ejecutadas y registrar semanas de otras épocas.
