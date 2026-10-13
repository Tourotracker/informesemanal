#!/usr/bin/env python3
"""
Añade la última semana cerrada al Informe Semanal de Actividad (index.html).

Los datos salen del histórico diario que guarda el Dashboard de Operaciones
(repo Tourotracker/Dashboard-Touron, bloque <script id="estado-bot"> de su index.html),
que a su vez se alimenta cada noche del correo de LIBRA.

Uso (dos pasos, para que el texto de análisis lo redacte quien ejecuta el bot):
  1) python3 bot/actualizar_informe.py --dashboard RUTA/dashboard/index.html --resumen
       → imprime JSON con la semana pendiente y todas las cifras/comparativas
         (código 3 si no hay ninguna semana cerrada pendiente)
  2) python3 bot/actualizar_informe.py --dashboard RUTA/dashboard/index.html --texto analisis.html
       → escribe la semana en index.html con ese texto de análisis

Códigos de salida: 0 = OK, 3 = nada pendiente, 4 = empieza temporada nueva (requiere
ajuste manual del informe), 1/2 = error.
"""
import argparse, datetime as dt, json, re, sys

AÑO = 27            # temporada que muestra el informe (2026/27)
DAY = dt.timedelta(days=1)


def inicio_temporada(y):
    """Lunes de la semana del 1 de octubre (o el lunes siguiente si el 1/10 cae en fin de semana)."""
    o = dt.date(y, 10, 1)
    wd = o.weekday()  # 0=lun … 6=dom
    return o + dt.timedelta(days=(7 - wd) if wd >= 5 else -wd)


def temporada(d):
    y = d.year if d >= inicio_temporada(d.year) else d.year - 1
    return (y + 1) % 100, inicio_temporada(y)


def pct(a, b):
    return None if not b else round((a - b) / abs(b) * 100, 1)


def cargar_historico(dashboard_html):
    s = open(dashboard_html, encoding='utf-8').read()
    m = re.search(r'<script type="application/json" id="estado-bot">(.*?)</script>', s, re.S)
    if not m:
        raise SystemExit('No encuentro el histórico (estado-bot) en el HTML del dashboard')
    return {x[0]: x for x in json.loads(m.group(1))['historico']}


class Informe:
    def __init__(self, path):
        self.path = path
        self.s = open(path, encoding='utf-8').read()

    def arr(self, name):
        m = re.search(rf'const {name}=\[(.*?)\];', self.s)
        return [None if v == 'null' else int(v) for v in m.group(1).split(',')]

    def set_arr(self, name, vals):
        txt = ','.join('null' if v is None else str(v) for v in vals)
        self.s, n = re.subn(rf'const {name}=\[.*?\];', lambda _: f'const {name}=[{txt}];', self.s, count=1)
        assert n == 1, name

    def obj(self, name):
        return json.loads(re.search(rf'const {name}=(\{{.*?\}});\n', self.s).group(1))

    def set_obj(self, name, o):
        txt = json.dumps(o, ensure_ascii=False, separators=(',', ':'))
        self.s, n = re.subn(rf'const {name}=\{{.*?\}};\n', lambda _: f'const {name}={txt};\n', self.s, count=1)
        assert n == 1, name

    @property
    def max_s(self):
        return int(re.search(r'const MAX_S27=(\d+);', self.s).group(1))

    def set_max(self, n):
        self.s = re.sub(r'const MAX_S27=\d+;', f'const MAX_S27={n};', self.s, count=1)

    def save(self):
        open(self.path, 'w', encoding='utf-8').write(self.s)


def semana_pendiente(inf, hoy):
    s = inf.max_s + 1
    ini27 = inicio_temporada(2026)
    lunes = ini27 + dt.timedelta(weeks=s - 1)
    viernes = lunes + 4 * DAY
    if s > 52 or temporada(lunes)[0] != AÑO:
        return s, lunes, viernes, 'nueva_temporada'
    if viernes >= hoy:
        return s, lunes, viernes, 'no_cerrada'
    return s, lunes, viernes, 'ok'


def datos_semana(hist, lunes):
    dias = [hist.get((lunes + i * DAY).isoformat()) for i in range(5)]
    return dict(
        tareas=sum(d[2] for d in dias if d), lineas=sum(d[1] for d in dias if d),
        cd=sum(d[3] for d in dias if d), diario=[d[1] if d else 0 for d in dias],
        dias_sin_datos=[(lunes + i * DAY).strftime('%d/%m') for i, d in enumerate(dias) if not d])


def resumen(inf, s, lunes, viernes, w):
    i = s - 1
    A = {k: inf.arr(k) for k in ('t25', 't26', 't27raw', 'l25', 'l26', 'l27raw', 'cd25', 'cd26', 'cd27raw')}
    acum = lambda a, n: sum(v or 0 for v in a[:n])
    t27 = A['t27raw'][:]; l27 = A['l27raw'][:]; c27 = A['cd27raw'][:]
    t27[i], l27[i], c27[i] = w['tareas'], w['lineas'], w['cd']
    daily = inf.obj('dailyData')
    r = dict(
        semana=s, fechas=f"{lunes.strftime('%d/%m/%Y')}–{viernes.strftime('%d/%m/%Y')}",
        semana_2027=dict(tareas=w['tareas'], lineas=w['lineas'], cd=w['cd'],
                         ratio=round(w['lineas'] / w['tareas'], 2) if w['tareas'] else None,
                         pct_cd=round(w['cd'] / w['lineas'] * 100, 1) if w['lineas'] else None,
                         diario_lun_vie=w['diario'], dias_sin_datos=w['dias_sin_datos']),
        semana_2026=dict(tareas=A['t26'][i], lineas=A['l26'][i], cd=A['cd26'][i],
                         diario_lun_vie=daily.get('26', {}).get(str(s))),
        semana_2025=dict(tareas=A['t25'][i], lineas=A['l25'][i], cd=A['cd25'][i],
                         diario_lun_vie=daily.get('25', {}).get(str(s))),
        variacion_vs_2026=dict(tareas=pct(w['tareas'], A['t26'][i]), lineas=pct(w['lineas'], A['l26'][i]), cd=pct(w['cd'], A['cd26'][i])),
        variacion_vs_2025=dict(tareas=pct(w['tareas'], A['t25'][i]), lineas=pct(w['lineas'], A['l25'][i]), cd=pct(w['cd'], A['cd25'][i])),
        semana_anterior_2027=dict(tareas=A['t27raw'][i - 1], lineas=A['l27raw'][i - 1], cd=A['cd27raw'][i - 1]) if i > 0 else None,
        acumulado_S1_a_S=dict(
            a2027=dict(tareas=acum(t27, s), lineas=acum(l27, s), cd=acum(c27, s)),
            a2026=dict(tareas=acum(A['t26'], s), lineas=acum(A['l26'], s), cd=acum(A['cd26'], s)),
            a2025=dict(tareas=acum(A['t25'], s), lineas=acum(A['l25'], s), cd=acum(A['cd25'], s))),
        semana_mudanza_2025=s in [34],
        textos_anteriores=inf.obj('textos'),
    )
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dashboard', required=True, help='index.html del repo Dashboard-Touron')
    ap.add_argument('--html', default='index.html')
    ap.add_argument('--resumen', action='store_true')
    ap.add_argument('--texto', help='fichero con el párrafo de análisis (HTML: <b>, <br>)')
    ap.add_argument('--hoy', help='fecha de referencia aaaa-mm-dd (pruebas)')
    a = ap.parse_args()
    hoy = dt.date.fromisoformat(a.hoy) if a.hoy else dt.date.today()

    inf = Informe(a.html)
    s, lunes, viernes, estado = semana_pendiente(inf, hoy)
    if estado == 'nueva_temporada':
        print(f'NUEVA_TEMPORADA: la semana {s} ({lunes:%d/%m/%Y}) es de una temporada nueva; '
              'el informe necesita prepararse para el año siguiente (ajuste manual).')
        sys.exit(4)
    if estado == 'no_cerrada':
        print(f'NADA_PENDIENTE: la siguiente semana es la S{s} ({lunes:%d/%m}–{viernes:%d/%m}) y aún no ha terminado.')
        sys.exit(3)

    hist = cargar_historico(a.dashboard)
    w = datos_semana(hist, lunes)
    if not w['lineas']:
        raise SystemExit(f'ERROR: la semana S{s} ({lunes:%d/%m}–{viernes:%d/%m}) no tiene ningún dato en el histórico del dashboard')

    if a.resumen:
        print(json.dumps(resumen(inf, s, lunes, viernes, w), ensure_ascii=False, indent=1))
        return
    if not a.texto:
        raise SystemExit('Falta --texto (o usa --resumen)')
    texto = open(a.texto, encoding='utf-8').read().strip()
    if len(texto) < 80:
        raise SystemExit('El texto de análisis es demasiado corto')

    i = s - 1
    for name, v in (('t27raw', w['tareas']), ('l27raw', w['lineas']), ('cd27raw', w['cd'])):
        arr = inf.arr(name)
        if arr[i] is not None:
            raise SystemExit(f'ERROR: {name}[S{s}] ya tiene valor ({arr[i]})')
        arr[i] = v
        inf.set_arr(name, arr)
    daily = inf.obj('dailyData')
    daily.setdefault('27', {})[str(s)] = w['diario']
    inf.set_obj('dailyData', daily)
    textos = inf.obj('textos')
    textos[str(s)] = texto
    inf.set_obj('textos', textos)
    inf.set_max(s)
    inf.save()
    print('OK ' + json.dumps(dict(semana=s, fechas=f'{lunes:%d/%m}–{viernes:%d/%m}', tareas=w['tareas'],
                                  lineas=w['lineas'], cd=w['cd'], diario=w['diario'],
                                  dias_sin_datos=w['dias_sin_datos']), ensure_ascii=False))


if __name__ == '__main__':
    main()
