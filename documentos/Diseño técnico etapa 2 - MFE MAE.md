# Etapa 2, propuesta 1: Medición MFE/MAE (evaluación y diseño técnico, versión 5)

## Conclusión
**Recomiendo tu medición como base.** Tu regla de combinaciones funciona: sus casos positivos y negativos fueron exactos en todas las pruebas. Solo le faltaba usar el MAE para resolver un caso más. Propongo añadir también una referencia contra el azar, una lectura en proporción a la volatilidad y una tabla para el ATM variable. Los dos archivos de salida están detallados en la sección 9.

## Respuestas a tus dos puntos

### El caso dudoso: mantengo la categoría, y este es el motivo
Lo que dices es cierto para el **MFE**: el MAE pre MFE siempre ocurre antes del MFE. Pero el **TP normalmente es menor que el MFE**, así que el precio pudo tocar el TP mucho antes. El orden que conocemos es "peor en contra → mejor a favor", y el TP puede estar antes de ese "peor en contra".

**Ejemplo real, señal 688** (1-oct, Sell, V, SL 120 y TP 80, 4 min). Entrada 13:42:00.500 en 30769,00:

| Hora | Qué pasó | Ticks |
|---|---|---|
| 13:43:05.160 | Tocó el TP en 30749,00 | +80 |
| 13:45:08.832 | Tocó el SL en 30799,00 | −120 |
| 13:45:56.752 | Llegó al MFE | +135 |

MAE pre MFE es 122 y MFE es 135, así que tu regla no permite clasificarla: por orden del recorrido parecería negativa, y en realidad **el TP llegó primero: fue positiva**. De las 57 dudosas de 120/80, 5 son como esta. Con 40/40 a 4 min son 76 de 291.

Solo si TP = MFE exacto se cumple tu orden. **Propongo mantener la columna "Dudosas" separada**, porque contarlas como negativas añadiría un error que cambia con cada combinación: 9 % en 120/80 y 26 % en 40/40. El simulador las resuelve tick a tick.

Sobre un mismo tick tocando ambos: no puede pasar, porque un tick tiene un solo precio. Sí se puede dar en el mismo milisegundo, y ahí decide el orden del archivo.

### Qué es lo del azar, en simple
**La pregunta:** en la apertura de NY el precio se mueve mucho todos los días. Si una señal hizo MFE de 75 ticks en 4 minutos, ¿eso es por tu señal, o cualquier entrada a esa hora habría hecho algo parecido?

**Cómo se calcula, con tu señal 552** (entrada a las 14:00:48.548; a 4 min dio MFE 75, MAE pre MFE 46 y MAE 63):
1. Se toman 20 días distintos, al azar.
2. En cada uno se entra a la misma hora, 14:00:48, sin mirar nada.
3. Se elige Buy o Sell como lanzando una moneda.
4. Entrada = precio de ese momento ± 3 ticks, igual que tus escenarios.
5. Se miden MFE, MAE pre MFE y MAE exactamente igual.

Cuatro de esas 20 entradas:

| Día | Dirección | MFE (4 min) | MAE pre MFE | MAE |
|---|---|---|---|---|
| 21-jul | Sell | 340 | 37 | 37 |
| 7-jul | Buy | 127 | 32 | 206 |
| 15-jul | Buy | 102 | 53 | 53 |
| 10-sep | Buy | 216 | 34 | 34 |

Comparar una sola señal no dice nada. Se repite con las 692 ejecutadas y se comparan los totales: entradas sin ningún criterio también dan recorridos grandes, porque la apertura se mueve mucho.

**Qué aporta:** separa lo que hace el mercado de lo que aporta tu entrada. Si en 3 minutos el 67 % de tus señales llega a 57 ticks y el azar a 52, tu señal añade unos 5 ticks; los otros 52 los da el mercado a esa hora. Es la única forma de medir con números lo que dices en tu documento 1, que el mercado reacciona en la dirección esperada.

**Qué no hace:** no filtra señales, no cambia tus resultados y no toca `resultados_mfe_mae.xlsx`. Solo añade unas columnas de referencia en la pestaña "Recorridos". Si al verlo prefieres quitarlo, sale sin afectar nada más; mi recomendación es dejarlo.

## 1. Qué mide y cómo aporta al proyecto
Sí te hago entender. Cada señal ejecutada se recorre tick a tick desde su **Hora Entrada y Precio Entrada** hasta **Hora Entrada + X minutos**, para X de 1 a 10:

| Medida | Qué es | Dónde se mide |
|---|---|---|
| **MFE (X min)** | Máximo recorrido a favor | Toda la ventana de X minutos |
| **Hora MFE (X min)** | Hora del **primer** tick que llegó a ese MFE | |
| **MAE pre MFE (X min)** | Máximo recorrido en contra | Solo desde la entrada hasta Hora MFE (X min) |
| **MAE (X min)** | Máximo recorrido en contra | Toda la ventana de X minutos |

**Ejemplo real, tu señal del ejemplo 2, a 4 minutos.** Buy, entrada a las 14:00:48.548 en 29020,50; ventana hasta las 14:04:48.548.
- **MFE (4 min) = 75 ticks:** el precio más alto fue 29039,25, alcanzado por primera vez a las 14:01:58.896.
- **MAE pre MFE (4 min) = 46 ticks:** lo peor entre las 14:00:48.548 y las 14:01:58.896.
- **MAE (4 min) = 63 ticks:** lo peor de los 4 minutos; ocurrió a las 14:03:04.052, después del MFE.

**Cómo aporta a tus objetivos:**

| Tu objetivo | Qué lo responde |
|---|---|
| Qué SL requieren tus zonas | MAE pre MFE y MAE, por zona y temporalidad |
| Qué TP pueden dar | MFE, por zona y temporalidad |
| Qué pasa al ejecutarse las señales | Tabla de recorridos y ventana de tiempo |
| Cómo adaptarse si sube o baja la volatilidad | Semanas y rangos de ATR NY |
| Qué ratios y combinaciones considerar | Tu regla de SL/TP, antes del simulador |
| Riesgo de sobreajuste del simulador | Contrastar sus combinaciones con estos recorridos |

## 2. Tu regla de combinaciones, con tus datos
La apliqué a SL/TP 120/80 a 4 min (Escenario 1, 692 ejecutadas). Tomé 120/80 como ticks, es decir 60/40 USD; si lo pensabas en USD, la tabla lo permite filtrar.

| Caso | Condición | Señales | ¿Exacto? |
|---|---|---|---|
| **Positiva** (tu regla) | MAE pre MFE < SL y MFE ≥ TP | **352** | Sí |
| **Negativa** (tu regla) | MAE pre MFE ≥ SL y MFE < TP | **16** | Sí |
| **Negativa después del máximo** (añadido) | MAE pre MFE < SL, MFE < TP y MAE ≥ SL | **161** | Sí |
| **Sin tocar SL ni TP** (añadido) | MAE pre MFE < SL, MFE < TP y MAE < SL | **106** | Sí |
| **Dudosa** (añadido) | MAE pre MFE ≥ SL y MFE ≥ TP | **57** | No se puede saber con estas medidas |

Lo comprobé contra el orden real de los ticks en 949.424 casos (7 temporalidades, 196 combinaciones, 692 señales): los cuatro primeros casos no fallaron nunca.

- **Tu regla deja dos casos abiertos.** Uno se resuelve con tu tercera medida, el MAE: 161 señales tocaron el SL después del máximo y sin él quedarían sin clasificar. Las dos negativas se reportan separadas para que veas cada una.
- **El caso dudoso no se puede resolver con estas medidas.** Tocó ambos, y el TP pudo llegar antes que el SL (ver la señal 688 arriba). Se reporta aparte. Lo resuelve el simulador; en tus datos la mayoría (84 %) tocó primero el SL.

## 3. Mi posición: qué mantengo y qué cambié
| Punto | Posición | Por qué |
|---|---|---|
| MFE/MAE es descriptivo | **Cambié, tienes razón** | Argumento válido |
| Tu regla SL/TP | **Cambié: es útil y exacta**; dije que no se debía usar | Dato nuevo: 0 fallos en sus casos |
| Comparar contra el azar | **Mantengo** | Sin referencia no se sabe qué es propio de tus señales |
| Las combinaciones contra recorridos reducen el sobreajuste | **Discrepo en parte** | Detectan combinaciones sin lógica, pero usan los mismos datos; no es validación independiente |
| Disparo con Last y deslizamiento fijo | **De acuerdo** | Abajo |

## 4. Criterios (en orden de prioridad)
1. Lecturas ciertas sobre tus señales, no sobre el mercado en general.
2. Fidelidad a los ticks y a tu operativa.
3. Responder tus objetivos, incluido ATM variable.
4. Que aguante el tamaño de muestra.
5. Reutilizar el motor en el simulador; sencillez.

## 5. Investigación y datos
**Buscado:** órdenes stop en CME y NinjaTrader, análisis con MFE/MAE, medidas de volatilidad intradía, triple barrera, efecto de stops y trailing.

**Encontrado:**
- CME activa el stop con operaciones reales y lo rechaza si no está más allá del último precio ([tipos de orden](https://cmegroupclientsite.atlassian.net/wiki/x/MAHJAg), [rechazos](https://cmegroupclientsite.atlassian.net/wiki/spaces/EPICSANDBOX/pages/457324354/Futures+and+Options+Reject+Codes)). Con Last salen las mismas 692 ejecuciones que con Bid/Ask.
- Es práctica habitual dividir MFE y MAE por la volatilidad, y compararlos con una entrada al azar ([edge ratio](https://daytrading.com/edge-ratio)).
- La volatilidad reciente anticipa la siguiente ([HAR](https://metricgate.com/docs/har-rv-realized-volatility-model/)).
- Si el precio no tiene memoria, los stops no mejoran el resultado esperado ([Kaminski y Lo](https://dspace.mit.edu/handle/1721.1/114876)). No encontré evidencia para intradía en futuros.

**Descartado:** calcular el deslizamiento con Bid/Ask, porque exige suponer una latencia; modelos que filtren señales, porque 14 semanas son pocas.

**No pude verificar:** tu deslizamiento real.

**Señales contra azar** (mismo minuto de otro día, dirección aleatoria, mismo deslizamiento). Al 67 %, señal / azar, en ticks:

| Minutos | MFE | MAE pre MFE | MAE |
|---|---|---|---|
| 3 | 57 / 52 | 52 / 52 | 127 / 132 |
| 5 | 75 / 68 | 68 / 67 | 158 / 167 |
| 10 | 104 / 93 | 91 / 88 | 223 / 231 |

Va en la dirección que esperas, pero las diferencias de medianas tienen márgenes que incluyen el cero: con 14 semanas no se puede afirmar ni descartar tu ventaja.

**Proporción al ATR NY:** entre la primera y la segunda mitad de tus datos, el MFE a 5 min cambia −37 % en ticks y −10 % en proporción; el MAE, −28 % y −7 %.

**MAE pre MFE según el MFE alcanzado (10 min):** con todas las señales, p50 de 55; si el MFE fue menor de 50, 17; entre 50 y 200, 59 a 68. Las que casi no se movieron bajan el dato.

**Después de ir a favor (10 min):** de las que llegaron a +20 ticks, 93 % volvió a la entrada; a +60, 77 %; a +120, 53 %. Es clave para el breakeven, que ninguna de tus propuestas mide.

**ATR de la apertura de NY** (promedio del tamaño de las velas de 1 min desde la apertura, en lugar de las últimas 10). Correlación semanal con MFE / MAE pre MFE / MAE a 5 min: misma semana 0,87 / 0,79 / 0,66; semana anterior 0,57 / 0,41 / 0,70. Antes de entrar, señal por señal, supera al ATR(10): 0,36 frente a 0,27 con el MFE. La eficiencia de Kaufman ("fuerza") no se relaciona con los recorridos y se descarta.

| ATR NY día anterior | Señales | MFE p50 / p75 | MAE pre MFE p50 / p90 | MAE p50 / p90 |
|---|---|---|---|---|
| Bajo (hasta 110) | 231 | 95 / 149 | 40 / 121 | 80 / 216 |
| Medio (110–148) | 220 | 127 / 210 | 41 / 137 | 109 / 306 |
| Alto (más de 148) | 229 | 134 / 205 | 50 / 159 | 128 / 335 |

## 6. Alternativas
| Opción | Ventajas | Desventajas / riesgos | Coste |
|---|---|---|---|
| A. Tu medición tal cual | Clara, en ticks | No distingue señal de mercado; mezcla épocas; sin ATM variable | Bajo |
| **B. Tu medición + referencia azar + proporción ATR NY + MAE pre por MFE + después de ir a favor (recomendada)** | Lecturas ciertas y adaptables | Más tablas que leer | Bajo-medio |
| C. Solo en proporción al ATR NY | Más estable | Pierdes los ticks, que es como operas | Medio |
| D. Solo simulador | Va directo a la rentabilidad | No explica por qué funciona una combinación | Bajo |
| E. Curvas de alcance | Lectura intuitiva | Misma información que tus percentiles | Bajo |

## 7. Evaluación de tu propuesta
| # | Problema | Solución |
|---|---|---|
| 1 | Sin referencia, se atribuyen a las señales recorridos del mercado | Columnas junto a entradas al azar |
| 2 | Ticks fijos entre épocas | Lectura también en proporción al ATR NY |
| 3 | MAE pre MFE mezcla señales que casi no se movieron | Tabla por nivel de MFE |
| 4 | Tu regla deja dos casos abiertos | Usar MAE y separar "dudosas" |
| 5 | No mide ATM variable | Tabla "después de ir a favor" |
| 6 | E4 contra E1 solo desplaza MFE −3 y MAE +3 | Se genera, sin análisis |
| 7 | 12 min recorridos, columnas hasta 10 | Recorrer 10 min |
| 8 | Precio igual a la orden y reintento sin definir | Igual bloquea (CME); reintento espera la demora |
| 9 | Ejemplo 1: entrada a las .252, antes de colocar a las .300 | Con tu regla sale a las .384; MFE y MAE coinciden |
| 10 | Celdas vacías y nombres | Vacías también si no se ejecuta; "Hora Entrada", "Precio Entrada" |

**Fortalezas:** MAE pre MFE es lo más valioso porque guarda el orden de los hechos, y permite clasificar combinaciones sin simular. Las 10 temporalidades muestran cuándo llega lo mejor.

## 8. Revisión por roles y conflictos
- **Trader:** lo decisivo es cuánto aguantar y cuándo salir; el dato del breakeven cambia la operativa.
- **Estadístico:** márgenes por día, porque las señales de un mismo día se parecen. Canal (11), 1er Vela (VC) (10) y Rango (20) se marcan.
- **Programador:** motor de entradas separado para reutilizarlo en el simulador.
- **Conflicto 1:** el trader quiere reglas por rango de ATR NY; el estadístico ve solo 13 comparaciones semanales. **Recomiendo tablas, sin reglas todavía.**
- **Conflicto 2:** más tablas son más mantenimiento, pero sin referencia el análisis engaña. **Prioriza el estadístico.**

## 9. Diseño técnico

### Entrada de cada señal, en cada escenario
1. Calcular Precio OP y validarlo con el cierre de "Hora UTC".
2. Al cierre + la demora del escenario, mirar el último Last.
3. Si no ha llegado a la orden, se coloca. Si llegó o la pasó, no se puede colocar.
4. Sin colocar: esperar a que el Last vuelva al otro lado, aguardar la demora y repetir. Si antes se alejó más de 45 ticks a favor desde la orden: "No Ejecutada OP".
5. Disparo: primer Last igual o más allá de la orden, antes de Hora UTC + 1 o 2 velas según la zona.
6. Precio Entrada = Precio OP ± deslizamiento; Hora Entrada = hora del tick que dispara.

### Archivo 1: `salida\mfe_mae\resultados_mfe_mae.xlsx`
**Pestañas:** Escenario 1, Escenario 2, Escenario 3, Escenario 4. **Una fila por cada señal registrada**, en el mismo orden del registro.

| Bloque | Columnas | Formato |
|---|---|---|
| Tu registro (18) | Fecha ... OHLC, igual que `registro_señales.xlsx` | Mismo formato |
| Revisión | Revision: "Valida", "Invalida R", "Invalida T", "Invalida OP" | Texto |
| Entrada | Precio OP · Ejecucion ("Ejecutada", "No Ejecutada", "No Ejecutada OP") · Hora Entrada · Precio Entrada · Tiempo Ejecucion | Precio con 2 decimales · hora h:mm:ss.000 a. m./p. m. |
| Por cada X de 1 a 10 (40) | MFE (X min) · Hora MFE (X min) · MAE pre MFE (X min) · MAE (X min) | Ticks enteros · hora con milésimas |
| Contexto (3, añadidas) | ATR NY hasta la señal · ATR NY día anterior · Volumen 1ª hora día anterior | Número |

**Celdas vacías:** si Revision es inválida, todo lo posterior. Si no se ejecutó, desde Hora Entrada en adelante; Precio OP sí aparece.

**Ejemplo de fila (Escenario 1, tu ejemplo 2):**

| ID | Revision | Precio OP | Ejecucion | Hora Entrada | Precio Entrada | Tiempo Ejecucion | MFE (1) | Hora MFE (1) | MAE pre MFE (1) | MAE (1) | ... | MFE (4) | Hora MFE (4) | MAE pre MFE (4) | MAE (4) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 552 | Valida | 29019.75 | Ejecutada | 2:00:48.548 p. m. | 29020.50 | 0:00:48.548 | 57 | 2:01:47.672 p. m. | 46 | 46 | ... | 75 | 2:01:58.896 p. m. | 46 | 63 |

### Archivo 2: `salida\mfe_mae\analisis_mfe_mae.xlsx`
Tablas calculadas sobre las señales ejecutadas, con filtros en cada encabezado.

| Pestaña | Filas | Columnas | Qué responde |
|---|---|---|---|
| Resumen | Escenario | Registradas, válidas, ejecutadas, no ejecutadas, no ejecutadas OP | Cuántas entran a la medición |
| Recorridos | Escenario × Minutos × % de señales (50, 60, 67, 75, 80, 90) | MFE "llegó al menos a", MAE pre MFE y MAE "no pasó de", en ticks y frente al azar | Tu ejemplo del 67 % |
| Combinaciones | Escenario × Minutos × SL × TP (20 a 280 ticks, cada 20) | SL y TP también en USD, Positivas, Negativas, Negativas tras el máximo, Sin tocar, Dudosas | Tu regla; filtras p. ej. SL 120, TP 80, 4 min |
| Ventana de tiempo | Escenario × Minutos | Medianas, segundos hasta el MFE, % con MFE igual al de 10 min, % con MAE mayor que MAE pre MFE | Qué ventana rinde más |
| Escenarios | E1 vs E2 y E1 vs E3 × Minutos | Señales en ambos, perdidas, diferencia de medianas | Qué cambia en cada escenario |
| Semanas | Semana × Minutos | Señales, ATR NY, volumen, MFE, MAE pre MFE, MAE con margen de error | Cómo cambia el mercado |
| Por grupo | Zona, Tipo, Te × Minutos | Señales, marca de poca muestra, percentiles | Qué hace cada zona |
| MAE pre por MFE | Minutos × nivel de MFE | Señales, percentiles de MAE pre MFE | Qué hubo que aguantar |
| Rangos ATR NY | Bajo, Medio, Alto × Minutos | Señales y percentiles | Tu tabla por rangos |
| Proporción | Minutos × mitad de la muestra | Medianas en ticks y en proporción al ATR NY | Qué lectura es estable |
| Después de ir a favor | Nivel +L | % que llega, % que vuelve a entrada | Breakeven y ATM variable |

**Ejemplo de fila de "Combinaciones":** Escenario 1 · 4 min · SL 120 · TP 80 · 60 USD · 40 USD · Positivas 352 · Negativas 16 · Negativas tras el máximo 161 · Sin tocar 106 · Dudosas 57.

**Ejemplo de fila de "Recorridos":** Escenario 1 · 3 min · 67 % · MFE 57 (azar 52) · MAE pre MFE 52 (azar 52) · MAE 127 (azar 132).

### Código
```
proyecto\
  main.py                 → nuevo comando: python main.py medir (valida y luego mide)
  config.py               → escenarios, horizontes, cuadrícula SL/TP y límite de 45 ticks
  medicion\entrada.py     → coloca, reintenta y dispara; lo reutiliza el simulador
  medicion\recorrido.py   → MFE, Hora MFE, MAE pre MFE, MAE
  medicion\volatilidad.py → ATR de la apertura y volumen
  medicion\azar.py        → entradas de referencia, con semilla fija
  medicion\analisis.py    → cada pestaña del archivo 2
  medicion\reportes.py    → escribe los dos archivos
  tests\
```
Reutiliza `armar_vela`, `leer_registro`, `ruta_parquet` y `ns_del_dia`. Añade numpy, una librería de cálculo numérico.

### Pruebas
Tus ejemplos 1 y 2 con ticks reales; el ejemplo de 4 min de la sección 1; cada rama de la entrada en compra y venta; límite exacto del horizonte, MFE negativo y primera vez del máximo; ATR sin datos posteriores a la señal; los cinco casos de tu regla, con casos a mano y límites exactos; azar repetible; E4 = E1 desplazado 3 ticks.

## 10. Decisiones que apruebas con este documento
1. Los dos archivos de salida de la sección 9.
2. Tu regla ampliada con Negativa tras el máximo, Sin tocar y Dudosa.
3. Reglas de entrada, disparo por Last y deslizamiento fijo.
4. Referencia contra azar, ATR NY con lectura en proporción, MAE pre por MFE y después de ir a favor.

## 11. Verificación al terminar
- E1: 692 / 3 / 8. E2: 670 / 28 / 5. E3: 680 / 6 / 17. E4 igual que E1.
- Señal 552 a 4 min: MFE 75, Hora MFE 14:01:58.896, MAE pre MFE 46, MAE 63.
- E1 a 3 min, 67 %: MFE 57, MAE pre MFE 52, MAE 127.
- Combinaciones E1, 4 min, 120/80: 352 / 16 / 161 / 106 / 57.
- Ejemplo 1: entrada 13:31:00.384, MFE (1 min) 5, MAE 149.

Cualquier diferencia se investiga antes de darla por buena.

## 12. Pendiente, riesgos y siguiente paso
- **Riesgo principal:** 14 semanas no alcanzan para confirmar la ventaja de dirección.
- **Simulador, a evaluar:** ATM variable, SL y TP en proporción al ATR NY, deslizamiento en saltos violentos y validación fuera de muestra separando semanas.
- **Siguiente paso:** construir esto, leer juntos los resultados y abrir el simulador con el mismo motor.
