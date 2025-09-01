from flask import Flask, request, render_template_string, send_file
import traceback
import os
import subprocess
import re
import unicodedata

app = Flask(__name__)

# NOTA: Usar un directorio temporal para archivos de salida en un entorno de producción es más seguro.
# Para este ejemplo simple, se usa el mismo directorio.
archivo_plantilla = "plantilla.tex"
# Archivo por defecto para guardar/cargar si no se especifica otro
archivo_por_defecto = "cancionero_web.txt"

# Cargar la plantilla al iniciar la aplicación
try:
    with open(archivo_plantilla, "r", encoding="utf-8") as f:
        plantilla = f.read()
except FileNotFoundError:
    print(f"Error: No se encontró el archivo de plantilla '{archivo_plantilla}'. Asegúrate de que existe en el mismo directorio.")
    plantilla = "% Plantilla LaTeX no encontrada. Fallará la compilación."

indice_tematica_global = {}

notas = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
equivalencias_latinas = {
    'Do': 'C', 'Do#': 'C#', 'Re': 'D', 'Re#': 'D#', 'Mi': 'E', 'Fa': 'F',
    'Fa#': 'F#', 'Sol': 'G', 'Sol#': 'G#', 'La': 'A', 'La#': 'A#', 'Si': 'B'
}

def transportar_acorde(acorde, semitonos):
    acorde = acorde.strip()

    # Convertir notación de bemoles en inglés a notación estándar
    acorde = acorde.replace('Bb', 'A#').replace('bb', 'a#')
    acorde = acorde.replace('Gb', 'F#').replace('gb', 'f#')

    # Manejar acordes con bajo (por ejemplo D/F#)
    if '/' in acorde:
        parte_superior, bajo = acorde.split('/')
        parte_superior_transpuesta = transportar_acorde(parte_superior, semitonos)
        bajo_transpuesto = transportar_acorde(bajo, semitonos)
        return f"{parte_superior_transpuesta}/{bajo_transpuesto}"

    # Mapa de conversión de bemoles a sostenidos para procesamiento interno
    mapa_bemoles_a_sostenidos = {
        'Reb': 'Do#', 'Rebm': 'Do#m',
        'Mib': 'Re#', 'Mibm': 'Re#m',
        'Lab': 'Sol#', 'Labm': 'Sol#m',
        'Sib': 'La#', 'Sibm': 'La#m'
    }

    # Convertir bemoles a sostenidos para procesamiento interno
    for bemol, sostenido in mapa_bemoles_a_sostenidos.items():
        if acorde.lower().startswith(bemol.lower()):
            acorde = sostenido + acorde[len(bemol):]
            break

    # Detectar si es notación latina y convertir a americana
    for nota_lat, nota_ang in equivalencias_latinas.items():
        if acorde.lower().startswith(nota_lat.lower()):
            acorde = nota_ang + acorde[len(nota_lat):]
            break

    match = re.match(r'^([A-Ga-g][#b]?)(.*)$', acorde)
    if not match:
        return acorde
    nota, sufijo = match.groups()
    nota_mayus = nota.upper()

    try:
        idx = notas.index(nota_mayus)
    except ValueError:
        return acorde

    nueva_idx = (idx + semitonos) % 12
    nueva_nota = notas[nueva_idx]
    if nota[0].islower():
        nueva_nota = nueva_nota.lower()

    acorde_transpuesto = nueva_nota + sufijo

    # Volver a convertir a notación latina
    return convertir_a_latex(acorde_transpuesto)


def limpiar_para_indice(palabra):
    return re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]', '', palabra)

def es_linea_acordes(linea):
    tokens = linea.split()
    if not tokens:
        return False
    for t in tokens:
        # Verificar si es un acorde en notación americana
        if re.match(r'^[A-G][#b]?(m|maj|min|dim|aug|sus|add)?\d*(/[A-G][#b]?)?$', t, re.IGNORECASE):
            continue

        # Verificar si es un acorde en notación latina
        notas_latinas = ['do', 're', 'mi', 'fa', 'sol', 'la', 'si']
        notas_latinas_bemoles = ['reb', 'mib', 'lab', 'sib']
        notas_latinas_sostenidos = ['do#', 're#', 'fa#', 'sol#', 'la#']

        # Comprobar si comienza con una nota latina (con sostenido, bemol o natural)
        if any(t.lower().startswith(n.lower()) for n in notas_latinas) or \
           any(t.lower().startswith(n.lower()) for n in notas_latinas_bemoles) or \
           any(t.lower().startswith(n.lower()) for n in notas_latinas_sostenidos):
            continue

        # Si no coincide con ningún patrón, no es un acorde
        return False
    return True

def convertir_a_latex(acorde):
    mapa = {
        'C': 'Do', 'C#': 'Do#', 'D': 'Re', 'D#': 'Re#', 'E': 'Mi', 'F': 'Fa',
        'F#': 'Fa#', 'G': 'Sol', 'G#': 'Sol#', 'A': 'La', 'A#': 'La#', 'B': 'Si',
        'Cm': 'Dom', 'C#m': 'Do#m', 'Dm': 'Rem', 'D#m': 'Re#m', 'Em': 'Mim',
        'Fm': 'Fam', 'F#m': 'Fa#m', 'Gm': 'Solm', 'G#m': 'Sol#m',
        'Am': 'Lam', 'A#m': 'La#m', 'Bm': 'Sim'
    }

    # Mapa de conversión de sostenidos a bemoles (SOLO para La#)
    mapa_bemoles_excepcion = {
        'La#': 'Sib', 'La#m': 'Sibm'
    }

    acorde = acorde.strip()
    # Convertir notación de bemoles en inglés a notación estándar
    acorde = acorde.replace('Bb', 'A#').replace('bb', 'a#')
    acorde = acorde.replace('Gb', 'F#').replace('gb', 'f#')

    if any(acorde.lower().startswith(n.lower()) for n in ['do', 're', 'mi', 'fa', 'sol', 'la', 'si']):
        return acorde

    # Manejar acordes con bajo (por ejemplo D/F#)
    if '/' in acorde:
        parte_superior, bajo = acorde.split('/')
        parte_superior_convertida = convertir_a_latex(parte_superior)
        bajo_convertido = convertir_a_latex(bajo)
        return f"{parte_superior_convertida}/{bajo_convertido}"

    match = re.match(r'^([A-Ga-g][#b]?m?)(.*)$', acorde)
    if match:
        raiz, extension = match.groups()
        raiz_mayus = raiz[0].upper() + raiz[1:]
        raiz_convertida = mapa.get(raiz_mayus, raiz)

        # Convertir SÓLO La# a Sib
        raiz_convertida = mapa_bemoles_excepcion.get(raiz_convertida, raiz_convertida)

        return raiz_convertida + extension

    return acorde

def procesar_linea_con_acordes_y_indices(linea, acordes, titulo_cancion, simbolo='#'):
    resultado = ''
    idx_acorde = 0
    palabras = linea.strip().split()

    for palabra in palabras:
        es_indexada = palabra.startswith(simbolo)
        index_real = None

        if es_indexada and '=' in palabra:
            base, index_real = palabra[1:].split('=', 1)
        else:
            base = palabra[1:] if es_indexada else palabra

        if base == '_':
            if idx_acorde < len(acordes):
                # Escapar sostenidos en acordes para LaTeX
                acorde_escapado = acordes[idx_acorde].replace('#', '\\#')
                resultado += f"\\raisebox{{1.7ex}}{{\\[{acorde_escapado}]}} "
                idx_acorde += 1
            else:
                resultado += '_ '
            continue

        if '_' in base:
            # Aquí base tiene acordes embebidos
            partes = base.split('_')
            latex = ''
            for i, parte in enumerate(partes):
                if i > 0 and idx_acorde < len(acordes):
                    # Escapar sostenidos en acordes para LaTeX
                    acorde_escapado = acordes[idx_acorde].replace('#', '\\#')
                    latex += f"\\[{acorde_escapado}]"
                    idx_acorde += 1
                latex += parte

            palabra_para_indice = limpiar_para_indice(index_real if index_real else ''.join(partes))

            if es_indexada:
                if palabra_para_indice not in indice_tematica_global:
                    indice_tematica_global[palabra_para_indice] = set()
                titulo_indexado = re.sub(r'\s*=[+-]?\d+\s*$', '', titulo_cancion.strip()) if titulo_cancion else "Sin título"
                indice_tematica_global[palabra_para_indice].add(titulo_indexado)

                # Solo agregamos esta palabra, resaltada y con acorde insertado
                resultado += f"\\textcolor{{blue!50!black}}{{\\textbf{{{latex}}}}}\\protect\\index[tema]{{{palabra_para_indice}}} "
            else:
                resultado += latex + ' '
        else:
            # Palabra sin acorde embebido
            palabra_para_indice = limpiar_para_indice(index_real if index_real else base)
            if es_indexada:
                if palabra_para_indice not in indice_tematica_global:
                    indice_tematica_global[palabra_para_indice] = set()
                indice_tematica_global[palabra_para_indice].add(titulo_cancion or "Sin título")

                resultado += f"\\textcolor{{blue!50!black}}{{\\textbf{{{base}}}}}\\protect\\index[tema]{{{palabra_para_indice}}} "
            else:
                resultado += base + ' '

    return resultado.strip()


def convertir_songpro(texto):
    referencia_pendiente = None
    # NORMALIZACIÓN: Escapar de la entrada los caracteres problemáticos.
    texto = texto.replace('_', '\\_').replace('#', '\\#').replace('\'', '\\\'')
    texto = unicodedata.normalize('NFC', texto)

    lineas = [linea.rstrip() for linea in texto.strip().split('\n')]
    resultado = []
    bloque_actual = []
    tipo_bloque = None
    seccion_abierta = False
    cancion_abierta = False
    titulo_cancion_actual = ""
    transposicion = 0

    def entorno(tb):
        if tb == 'verse':
            return (r'\beginverse', r'\endverse')
        elif tb == 'chorus':
            return (r'\beginchorus', r'\endchorus')
        elif tb == 'melody':
            return (r'\beginverse', r'\endverse')

    def cerrar_bloque():
        nonlocal bloque_actual, tipo_bloque
        if bloque_actual:
            if tipo_bloque == 'nodiagram':
                resultado.append(r'\beginverse')
                resultado.append(procesar_bloque_simple('\n'.join(bloque_actual), transposicion))
                resultado.append(r'\endverse')
            else:
                begin, end = entorno(tipo_bloque)
                # Asignar letra según el tipo de bloque: A para estrofa, B para coro, C para melodía
                if tipo_bloque == 'verse':
                    letra_diagrama = 'A'
                elif tipo_bloque == 'chorus':
                    letra_diagrama = 'B'
                elif tipo_bloque == 'melody':
                    letra_diagrama = 'C'
                else:
                    letra_diagrama = 'A'
                # Eliminar barras invertidas duplicadas y comillas
                contenido = ' \\\\'.join(bloque_actual).replace('\\\\ \\\\', ' \\\\')
                contenido = contenido.replace('"', '')

                # Desescapar los caracteres que son parte del formato songpro
                contenido = contenido.replace('\\#', '#').replace('\\_', '_')

                resultado.append(begin)
                resultado.append(f"\\diagram{{{letra_diagrama}}}{{{contenido}}}")
                resultado.append(end)
        # Siempre limpiar bloque actual y tipo
        bloque_actual = []
        tipo_bloque = None

    def cerrar_cancion():
        nonlocal cancion_abierta, referencia_pendiente
        if cancion_abierta:
            resultado.append(r'\endsong')
            if referencia_pendiente:
                resultado.append(rf'\beginscripture{{[{referencia_pendiente}]}}')
                resultado.append(r'\endscripture')
                referencia_pendiente = None
            cancion_abierta = False

    def procesar_bloque_simple(texto, transposicion):
        # Desescapar los caracteres que son parte del formato songpro
        texto = texto.replace('\\#', '#').replace('\\_', '_')

        lineas = texto.strip().split('\n')
        resultado = []
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            match = re.match(r'^([^:]+):\s*(.*)$', linea)
            if match:
                texto, acordes_linea = match.groups()
                acordes = acordes_linea.split()
                acordes_convertidos = [transportar_acorde(a, transposicion) for a in acordes]
                # Escapar sostenidos en acordes para LaTeX
                acordes_escapados = [a.replace('#', '\\#') for a in acordes_convertidos]
                latex_acordes = ' '.join(f'\\[{a}]' for a in acordados_escapados)
                resultado.append(rf'\textnote{{{texto.strip()}}}')
                resultado.append(rf'\mbox{{{latex_acordes}}}')
                continue
            if es_linea_acordes(linea):
                acordes = linea.split()
                acordes_convertidos = [transportar_acorde(a, transposicion) for a in acordes]
                # Escapar sostenidos en acordes para LaTeX
                acordes_escapados = [a.replace('#', '\\#') for a in acordes_convertidos]
                latex_acordes = ' '.join(f'\\[{a}]' for a in acordes_escapados)
                resultado.append(rf'\mbox{{{latex_acordes}}}')
                continue
            else:
                if linea.strip() in ('V', 'C', 'M', 'N'):
                    continue
                resultado.append(linea + r'\\')
        return '\n'.join(resultado)

    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()
        if linea.lower().startswith("ref="):
            contenido = linea[4:].strip()
            if contenido.startswith('(') and contenido.endswith(')'):
                referencia_pendiente = contenido[1:-1]
            i += 1
            continue

        if not linea:
            i += 1
            continue

        if linea.startswith('S '):
            cerrar_bloque()
            cerrar_cancion()
            if seccion_abierta:
                resultado.append(r'\end{songs}')
            seccion_abierta = True
            resultado.append(r'\songchapter{' + linea[2:].strip().title() + '}')
            resultado.append(r'\begin{songs}{titleidx}')
            i += 1
            continue

        if linea.startswith('O '):
            cerrar_bloque()
            cerrar_cancion()
            partes = linea[2:].strip().split()
            transposicion = 0
            if partes and re.match(r'^=[+-]?\d+$', partes[-1]):
                transposicion = int(partes[-1].replace('=', ''))
                partes = partes[:-1]
            titulo_cancion_actual = ' '.join(partes).title()

            etiqueta = f"cancion-{limpiar_titulo_para_label(titulo_cancion_actual)}"

            resultado.append(r'\beginsong{' + titulo_cancion_actual + '}')
            resultado.append(rf'\index[titleidx]{{{titulo_cancion_actual}}}')
            resultado.append(r'\phantomsection')
            resultado.append(rf'\label{{{etiqueta}}}')

            cancion_abierta = True
            i += 1
            continue

        if linea.isupper() and len(linea) > 1 and not es_linea_acordes(linea) and linea not in ('V', 'C', 'M', 'O', 'S'):
            cerrar_bloque()
            cerrar_cancion()
            titulo_cancion_actual = linea.title()

            etiqueta = f"cancion-{limpiar_titulo_para_label(titulo_cancion_actual)}"

            resultado.append(r'\beginsong{' + titulo_cancion_actual + '}')
            resultado.append(r'\phantomsection')
            resultado.append(rf'\label{{{etiqueta}}}')

            cancion_abierta = True
            i += 1
            continue

        if linea == 'O':
            cerrar_bloque()
            cerrar_cancion()
            titulo_cancion_actual = ""
            resultado.append(r'\beginsong{}')
            cancion_abierta = True
            i += 1
            continue

        if not cancion_abierta:
            resultado.append(r'\beginsong{}')
            cancion_abierta = True

        if linea == 'V':
            cerrar_bloque()
            tipo_bloque = 'verse'
            i += 1
            continue

        if linea == 'M':
            cerrar_bloque()
            tipo_bloque = 'melody'
            i += 1
            continue

        if linea == 'N':
            cerrar_bloque()
            tipo_bloque = 'nodiagram'
            i += 1
            continue

        if linea == 'C':
            if i + 1 < len(lineas) and es_linea_acordes(lineas[i + 1].strip()):
                cerrar_bloque()
                tipo_bloque = 'chorus'
                i += 1
                continue
            else:
                pass

        if i > 0 and lineas[i - 1].strip() in ('V', 'C', 'M'):
            cerrar_bloque()
            if lineas[i - 1].strip() == 'V':
                tipo_bloque = 'verse'
            elif lineas[i - 1].strip() == 'C':
                tipo_bloque = 'chorus'
            elif lineas[i - 1].strip() == 'M':
                tipo_bloque = 'melody'

        if i + 1 < len(lineas) and es_linea_acordes(lineas[i]):
            acordes_originales = lineas[i].strip().split()
            acordes = [transportar_acorde(a, transposicion) for a in acordes_originales]
            letras_raw = lineas[i + 1].strip()
            if letras_raw.startswith("//") and letras_raw.endswith("//"):
                letras_raw = letras_raw[2:-2].strip()

            rep_ini = letras_raw.startswith('B ')
            if rep_ini:
                letras_raw = letras_raw[2:].lstrip()
            rep_fin = False
            repeticiones = 2

            m_fin = re.search(r'\s+B=(\d+)$', letras_raw)
            if m_fin:
                rep_fin = True
                repeticiones = int(m_fin.group(1))
                letras_raw = letras_raw[:m_fin.start()].rstrip()
            elif letras_raw.endswith(' B'):
                rep_fin = True
                letras_raw = letras_raw[:-2].rstrip()

            if letras_raw == '_':
                cerrar_bloque()
                resultado.append(f"\\textnote{{{acordes[0]}}}")
                i += 2
                continue

            if not ('_' in letras_raw or '#' in letras_raw):
                acordes_escapados = [a.replace('#', '\\#') for a in acordes]
                bloque_actual.append('\\mbox{' + ' '.join([f'\\[{a}]' for a in acordes_escapados]) + '}')
                bloque_actual.append(letras_raw)
                i += 2
                continue

            linea_convertida = procesar_linea_con_acordes_y_indices(letras_raw, acordes, titulo_cancion_actual)
            if rep_ini and rep_fin:
                linea_convertida = r'\lrep ' + linea_convertida + rf' \rrep \rep{{{repeticiones}}}'
            elif rep_ini:
                linea_convertida = r'\lrep ' + linea_convertida
            elif rep_fin:
                linea_convertida = linea_convertida + rf' \rrep \rep{{{repeticiones}}}'
            bloque_actual.append(linea_convertida)
            i += 2
            continue

        if tipo_bloque and not es_linea_acordes(linea):
            if linea in ('V', 'C', 'M', 'N'):
                i += 1
                continue

            rep_ini = linea.startswith('B ')
            if rep_ini:
                linea = linea[2:].lstrip()

            rep_fin = False
            repeticiones = 2

            m_fin = re.search(r'\s+[Bb]=(\d+)$', linea)
            if m_fin:
                rep_fin = True
                repeticiones = int(m_fin.group(1))
                linea = linea[:m_fin.start()].rstrip()
            elif linea.endswith(' B') or linea.endswith(' b'):
                rep_fin = True
                linea = linea[:-2].rstrip()

            if '_' in linea or '#' in linea:
                linea_procesada = procesar_linea_con_acordes_y_indices(linea, [], titulo_cancion_actual)
            else:
                linea_procesada = linea

            if rep_ini and rep_fin:
                linea_procesada = r'\lrep ' + linea_procesada + rf' \rrep \rep{{{repeticiones}}}'
            elif rep_ini:
                linea_procesada = r'\lrep ' + linea_procesada
            elif rep_fin:
                linea_procesada = linea_procesada + rf' \rrep \rep{{{repeticiones}}}'

            bloque_actual.append(linea_procesada)
            i += 1
            continue
            if linea in ('V', 'C', 'M', 'N'):
                i += 1
                continue
            if linea == 'V':
                cerrar_bloque()
                tipo_bloque = 'verse'
                i += 1
                continue
            if linea == 'M':
                cerrar_bloque()
                tipo_bloque = 'melody'
                i += 1
                continue

    cerrar_bloque
