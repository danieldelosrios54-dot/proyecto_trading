# Entregable principal: 6 escenarios con cierre por minutos y análisis con conclusiones (diseño técnico)

## Contexto
Tu documento "4. Entregable principal luego de análisis" fija un escenario principal: orden a ±3 ticks, colocación en 200 ms, deslizamiento de 3 y cierre a 9 minutos desde la entrada. Lo compara con 5 variantes que cambian una sola cosa cada una y pide tres archivos.

A eso se suman dos cosas:
- **Dos columnas de consistencia.**
- **Un archivo de análisis que escriba las conclusiones**, porque los anteriores eran difíciles de leer y las conclusiones salieron de preguntarme.

Los análisis dejan este escenario en nivel **Candidata**: positivo en semanas no vistas, pero con la ganancia concentrada en las primeras 7 semanas. No soy asesor financiero; esto mide tus datos históricos.

## Decisiones de esta versión
| Tema | Decisión |
|---|---|
| Solapamiento | La señal se pierde solo si sigues dentro de otra operación cuando el precio llega a la orden. Es tu respuesta y corrige el texto del documento 4 |
| Salida por SL | Precio del SL − 2 ticks. Los datos lo respaldan: el 98 % de los SL se tocan justo en su precio |
| Re-entrada | Límite de 60 ticks a favor antes de volver (antes 45), solo en estos entregables. La medición MFE/MAE sigue con 45 |
| Comisión | 1,86 USD por operación (lo exige el documento 1) |
| Colocación en 200 ms | Supuesto tuyo. Conviene confirmarlo con el Log de NinjaTrader |
| Consistencia | "Peor mitad" y "Semanas positivas" en los archivos de escenarios y de zonas; **no en el de semanas**, porque ahí no tienen sentido |
| Archivo de zonas | Columnas reducidas a las que responden qué SL/TP funciona en cada zona (ver Columnas) |
| Errata | Escenario 6 = resultados del escenario 6 |

## Escenarios
| | E1 (principal) | E2 | E3 | E4 | E5 | E6 |
|---|---|---|---|---|---|---|
| Distancia de la orden | 3 | 7 | 3 | 3 | 3 | 3 |
| Colocación | 200 ms | 200 ms | 600 ms | 200 ms | 200 ms | 200 ms |
| Deslizamiento de entrada | 3 | 3 | 3 | 6 | 3 | 3 |
| Cierre por tiempo | 9 min | 9 min | 9 min | 9 min | 8 min | 5 min |

Las demás reglas no cambian: ventana de ejecución por zona, disparo por Last, TP al pasar 2 ticks, cierre por tiempo con el primer tick en o después de entrada + X minutos, −2 ticks.

## Columnas
**Archivo de zonas (entregable 2): columnas reducidas**, porque su pregunta es qué SL/TP funciona mejor en cada zona. Las demás columnas no aplican: valen siempre lo mismo, no cambian entre combinaciones o dependen de operar todas las zonas juntas.

| Columna | Qué registra | Formato |
|---|---|---|
| SL (ticks), TP (ticks), SL (USD), TP (USD) | La combinación | Número |
| Operaciones | Señales de la zona ejecutadas (igual en todas las filas de la pestaña) | Número |
| Ganancia Neta | Suma en USD de las operaciones de la zona | USD |
| Esperanza Matematica | USD por operación. Sirve para comparar zonas con distinto número de señales | USD |
| Win Rate | % de operaciones ganadoras | % |
| Payoff Ratio | Ganancia media / pérdida media. Junto al Win Rate explica la Esperanza | Número |
| Combinaciones Vecinas | Ganancia Neta mínima de la matriz 3 × 3 de esa zona | USD |
| Peor mitad | Neto de la mitad de semanas que ganó menos | USD |
| Semanas positivas | Semanas con neto > 0 sobre las semanas en que la zona tuvo operaciones | "X de Y" |

Las pestañas de zonas con menos de 30 señales llevan "(poca muestra)" en el nombre.

**En los archivos de escenarios y de semanas:**
- Las que identifican la combinación: SL (ticks), TP (ticks), SL (USD), TP (USD).
- Las 20 de tu documento: Revision Invalida, No Ejecutadas, # Solapamiento, Hora Entrada, Ventana Ejecucion, Prom. Tiempo Abierta, Ganancia Neta, Esperanza Matematica, Profit Factor, Win Rate, Payoff Ratio, Drawdown, Recovery Factor, Combinaciones Vecinas, Trades +, Trades −, Racha Max. (Operaciones −), Racha Max. (Dias −), $ Peor Dia, Fecha Peor Dia.

**Solo en el archivo de escenarios**, después de Combinaciones Vecinas (en el de zonas ya están en sus columnas reducidas):

| Columna | Qué registra | Formato |
|---|---|---|
| Peor mitad | Las semanas se dividen en dos mitades iguales (con 14 semanas, 7 y 7). Registra el neto de la mitad que ganó menos. Positiva = ganó en ambas partes; negativa = su ganancia depende de una sola época | USD, 2 decimales |
| Semanas positivas | En cuántas semanas la combinación tuvo neto mayor que 0, sobre el total de semanas | "X de 14" |

**Definiciones de las columnas que tu documento dejó vacías:**
- Ganancia Neta: suma en USD, con comisión y deslizamientos.
- Esperanza Matematica: Ganancia Neta / operaciones.
- Profit Factor: ganancias brutas / pérdidas brutas.
- Win Rate: % de operaciones con neto > 0.
- Payoff Ratio: ganancia media / pérdida media.
- Drawdown: mayor caída del neto acumulado, por orden de cierre.
- Recovery Factor: Ganancia Neta / Drawdown.
- $ Peor Dia y Fecha Peor Dia: el día con menor neto y su fecha.

## Archivos (en `salida\combinaciones\principal\`)
| Archivo | Pestañas | Solapamiento |
|---|---|---|
| `combinaciones_principal.xlsx` | Matriz + Escenario 1 (Principal) a Escenario 6, 7.744 filas cada una | Sí |
| `combinaciones_principal_zonas.xlsx` | Matriz + 10 zonas (Escenario 1) | No |
| `combinaciones_principal_semana.xlsx` | Matriz + 14 semanas (Escenario 1) | Sí |
| `analisis_principal.xlsx` | 6 pestañas, abajo | — |

**Pestaña "Matriz":** la tabla Recorrido/Escenario, las reglas en texto, la definición de cada columna y una nota con el nivel de evidencia.

### Archivo de análisis: cada pestaña con la conclusión escrita y como máximo 30 filas
| Pestaña | Contenido |
|---|---|
| **Conclusiones** | Una fila por pregunta, con Pregunta · Respuesta (Sí / No / Empate) · Dato que la respalda (frase con números, generada en cada ejecución) · Nivel de evidencia · Pestaña de detalle. Preguntas: ¿3 o 7 ticks? ¿200 o 600 ms? ¿Cuánto cuesta un deslizamiento de 6? ¿9, 8 o 5 minutos? ¿Alguna zona resta? ¿Qué semanas fallaron y cómo estaba el mercado? ¿Qué combinaciones son sólidas y consistentes? |
| Escenarios | Una fila por escenario: combinaciones positivas, resultado del ATM de referencia (SL 185 / TP 125), peor mitad, semanas positivas, resultado fuera de muestra y diferencia con el E1. Verde si mejora, rojo si empeora |
| Combinaciones candidatas | Las del E1 que cumplen a la vez Ganancia Neta > 0, Combinaciones Vecinas > 0 y Peor mitad > 0, ordenadas por Ganancia Neta (máximo 30) |
| Zonas | Una fila por zona: resultado del ATM de referencia, peor mitad, si aporta o resta al total, y la marca de poca muestra |
| Semanas | Una fila por semana: resultado del ATM de referencia, cuántas combinaciones ganaron, ATR(5) y Range promedio |
| Cómo leer | Qué responde cada pestaña, con un ejemplo real |

**Reglas de las respuestas:**
- "Sí" o "No" solo cuando la diferencia es clara en el total y en ambas mitades.
- Si no, "Empate".
- El nivel de evidencia sigue los criterios aprobados: Candidata, Confirmada o Validada.

**ATM de referencia:** SL 185 / TP 125 ticks. Se puede cambiar en `config.py`.

## Código
- `medicion/entrada.py`: `Escenario` recibe un límite de re-entrada (por defecto, el de config: 45).
- `simulador/salidas.py`: cierre por minutos (`fijo_minutos`) y opción de salida del SL "precio del SL − 2".
- `simulador/metricas.py`:
  - `combinaciones_vecinas` (mínimo de la matriz 3 × 3, con 6 vecinas en los bordes y 4 en las esquinas);
  - `peor_mitad`;
  - `semanas_positivas`.
- `simulador/principal_escenarios.py` (nuevo): arma los 6 escenarios, calcula las columnas y el análisis, y escribe los 4 archivos. Reutiliza `operaciones_de`, `conjunto`, `tomar_sin_solape`, `columnas`, `fuera_de_muestra` y `escribir_libro`.
- `simulador/reportes.py`: tabla de columnas configurable, pestaña Matriz y colores verde y rojo en el análisis.
- `config.py`: escenarios principales, límite de 60 ticks, ATM de referencia y rutas.
- `main.py`: nuevo comando `python main.py principal`. `medir` y `simular` no cambian.
- **Pruebas:**
  - cierre por minutos en Te 1 y Te 2;
  - SL − 2;
  - límite de 60 ticks en una re-entrada;
  - Combinaciones Vecinas en centro, borde y esquina;
  - Peor mitad y Semanas positivas con un caso a mano;
  - que el archivo de semanas no tenga esas dos columnas y que el de zonas tenga solo sus columnas reducidas;
  - que las respuestas de Conclusiones salgan de los números (caso Sí, No y Empate).

## Verificación
- `pytest` (170 actuales + nuevas).
- `python main.py principal` (unos 5–10 minutos, con los Excel cerrados).
- E1, SL 185 / TP 125: debe quedar cerca del +3.774 USD medido con 200 ms. La diferencia debe venir solo del SL − 2 y del límite de 60 ticks; se reporta.
- Recalcular a mano, tick a tick, una combinación del E1.
- La suma de las 14 semanas coincide con el E1. Peor mitad y Semanas positivas coinciden con las pestañas semanales.
- Leer juntos la pestaña Conclusiones.
- Guardar este diseño en `documentos`.
