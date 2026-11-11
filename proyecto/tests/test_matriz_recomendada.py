"""La pestaña Matriz recomendada se arma con los números del catálogo y marca las columnas elegidas."""

import openpyxl

from simulador.matriz_recomendada import ESCENARIOS, escribir


def test_matriz_recomendada(tmp_path):
    analisis = tmp_path / "analisis.xlsx"
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Catálogo"
    columnas = ["Forma", "Estado", "Fuera: neto (USD)", "Fuera: PF", "Fuera: operaciones", "Fuera: primera mitad", "Fuera: segunda mitad",
                "Fuera: semanas positivas", "Caída máxima (USD)", "Percentil frente al azar", "ATM o parámetro más elegido"]
    hoja.append(columnas)
    for i, (_, forma, _, _) in enumerate(ESCENARIOS):
        hoja.append([forma, "Candidata", 1000 + i, 1.2, 400, 600, 400 + i, 9, 900, 100, "SL 92.5 / TP 62.5 USD"])
    libro.save(analisis)

    propuesta = tmp_path / "propuesta.xlsx"
    libro = openpyxl.Workbook()
    hoja = libro.active
    hoja.title = "Matriz propuesta"
    hoja.append(["Recorrido", "Referencia", "Referencia + Stop al cierre de vela", "Referencia + Otra forma"])
    libro.save(propuesta)

    assert len(escribir(analisis, propuesta)) == 5
    escribir(analisis, propuesta)  # repetir no duplica nada
    libro = openpyxl.load_workbook(propuesta)
    assert libro.sheetnames[0] == "Matriz recomendada"
    recomendada = libro["Matriz recomendada"]
    assert [c.value for c in recomendada[1]] == ["Recorrido", *[e[0] for e in ESCENARIOS]]
    fuera = next(f for f in recomendada.iter_rows(values_only=True) if f[0] == "Fuera de muestra (USD)")
    assert fuera[1:] == (1000, 1001, 1002, 1003, 1004)
    marcas = [list(f) for f in libro["Matriz propuesta"].iter_rows(values_only=True)]
    assert marcas[-1] == ["¿En la Matriz recomendada?", "E1 Referencia", "E2 Stop al cierre de vela", "No"]
    assert len(marcas) == 2
