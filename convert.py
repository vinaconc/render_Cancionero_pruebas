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

                # Escapar el '#' antes de pasarlo a LaTeX en el texto del índice temático
                # Solo escapamos '#' en el texto literal, no dentro de los comandos \[...]
                escaped_latex = latex.replace('#', '\\#')
                resultado += f"\\textcolor{{blue!50!black}}{{\\textbf{{{escaped_latex}}}}}\\protect\\index[tema]{{{palabra_para_indice}}} "
            else:
                # Escapar '#' si la palabra no es indexada pero contiene el símbolo
                # Idem, solo en texto literal
                escaped_latex = latex.replace('#', '\\#')
                resultado += escaped_latex + ' '
        else:
            # Palabra sin acorde embebido
            palabra_para_indice = limpiar_para_indice(index_real if index_real else base)
            if es_indexada:
                if palabra_para_indice not in indice_tematica_global:
                    indice_tematica_global[palabra_para_indice].add(titulo_cancion or "Sin título")

                # Escapar el '#' antes de pasarlo a LaTeX
                escaped_base = base.replace('#', '\\#')
                resultado += f"\\textcolor{{blue!50!black}}{{\\textbf{{{escaped_base}}}}}\\protect\\index[tema]{{{palabra_para_indice}}} "
            else:
                # Escapar '#' si la palabra no es indexada pero contiene el símbolo
                escaped_base = base.replace('#', '\\#')
                resultado += escaped_base + ' '

    return resultado.strip()


def convertir_songpro(texto):
    referencia_pendiente = None
    # NORMALIZACIÓN: Escapar de la entrada los caracteres problemáticos para LaTeX
    # Mantenemos \\# y \\_ para SongPro, pero escapamos otros caracteres especiales de LaTeX
    # Esta normalización debe hacerse con cuidado para no interferir con la sintaxis de SongPro.
    # El escapado de '#' en acordes se hará más tarde.
    texto = texto.replace('\'', '\\\'')
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
        return None, None # Devuelve None si el tipo no es reconocido

    def cerrar_bloque():
        nonlocal bloque_actual, tipo_bloque
        if bloque_actual:
            if tipo_bloque == 'nodiagram':
                resultado.append(r'\beginverse')
                # Las líneas de nodiagram se procesan individualmente, no como un diagrama
                for linea_contenido in bloque_actual:
                    resultado.append(procesar_bloque_simple_linea(linea_contenido, transposicion))
                resultado.append(r'\endverse')
            elif tipo_bloque is not None:
                begin, end = entorno(tipo_bloque)
                if begin and end:
                    if tipo_bloque == 'verse':
                        letra_diagrama = 'A'
                    elif tipo_bloque == 'chorus':
                        letra_diagrama = 'B'
                    elif tipo_bloque == 'melody':
                        letra_diagrama = 'C'
                    else: # Fallback, aunque no debería ocurrir con las comprobaciones anteriores
                        letra_diagrama = 'A'
                    
                    contenido_final_para_diagram = " \\\\ ".join(bloque_actual)
                    contenido_final_para_diagram = re.sub(r'\\\\(\s*\\\\)*', r'\\\\', contenido_final_para_diagram)
                    
                    resultado.append(begin)
                    resultado.append(f"\\diagram{{{letra_diagrama}}}{{{contenido_final_para_diagram}}}")
                    resultado.append(end)
        bloque_actual = []
        tipo_bloque = None

    def cerrar_cancion():
        nonlocal cancion_abierta, referencia_pendiente
        if cancion_abierta:
            cerrar_bloque() # Asegúrate de cerrar cualquier bloque pendiente antes de la canción
            resultado.append(r'\endsong')
            if referencia_pendiente:
                referencia_escapada = referencia_pendiente.replace('#', '\\#')
                resultado.append(rf'\beginscripture{{[{referencia_escapada}]}}')
                resultado.append(r'\endscripture')
                referencia_pendiente = None
            cancion_abierta = False

    def procesar_bloque_simple_linea(linea_texto, transposicion):
        # Esta función procesará una sola línea y devolverá el string LaTeX con el escapado correcto
        linea = linea_texto.strip()
        if not linea:
            return ""

        # Primero, desescapar _ y # si fueron escapados para SongPro temporalmente
        linea = linea.replace('\\_', '_').replace('\\#', '#')

        match = re.match(r'^([^:]+):\s*(.*)$', linea)
        if match:
            texto_linea, acordes_linea = match.groups()
            acordes = acordes_linea.split()
            acordes_convertidos = [transportar_acorde(a, transposicion) for a in acordes]
            # Escapar sostenidos en acordes para LaTeX
            acordes_escapados = [a.replace('#', '\\#') for a in acordes_convertidos]
            latex_acordes = ' '.join(f'\\[{a}]' for a in acordes_escapados)
            
            texto_linea_escapado = texto_linea.strip().replace("#", "\\#") # Escapar '#' en el texto
            
            # \textnote y \mbox ya gestionan el salto de línea, no agregar '\\' aquí
            return rf'\textnote{{{texto_linea_escapado}}}\mbox{{{latex_acordes}}}'
        
        if es_linea_acordes(linea):
            acordes = linea.split()
            acordes_convertidos = [transportar_acorde(a, transposicion) for a in acordes]
            acordes_escapados = [a.replace('#', '\\#') for a in acordes_convertidos]
            latex_acordes = ' '.join(f'\\[{a}]' for a in acordes_escapados)
            # \mbox ya gestiona el salto de línea, no agregar '\\' aquí
            return rf'\mbox{{{latex_acordes}}}'
        else:
            if linea.strip() in ('V', 'C', 'M', 'N'): # Estos son comandos, no texto para renderizar
                return ""
            
            # Procesar si hay acordes embebidos o índices
            if '_' in linea or '#' in linea:
                linea_procesada_para_lyrics = procesar_linea_con_acordes_y_indices(linea, [], titulo_cancion_actual)
                return linea_procesada_para_lyrics + r'\\' # Añadir '\\' si es línea de letra simple
            else:
                linea_escapada = linea.replace('#', '\\#')
                return linea_escapada + r'\\' # Añadir '\\' al final de la línea para LaTeX

    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()

        # Antes de cualquier procesamiento, desescapar _ y # si fueron escapados para SongPro
        # Esto es crucial porque la sintaxis de SongPro los usa directamente.
        # Desescapar solo para esta línea, no permanentemente en 'texto'
        temp_linea = linea.replace('\\_', '_').replace('\\#', '#')

        if temp_linea.lower().startswith("ref="):
            cerrar_bloque()
            contenido = temp_linea[4:].strip()
            if contenido.startswith('(') and contenido.endswith(')'):
                referencia_pendiente = contenido[1:-1]
            i += 1
            continue

        if not temp_linea:
            cerrar_bloque()
            i += 1
            continue

        if temp_linea.startswith('S '):
            cerrar_bloque()
            cerrar_cancion()
            if seccion_abierta:
                resultado.append(r'\end{songs}')
            seccion_abierta = True
            chapter_title_escaped = temp_linea[2:].strip().title().replace('#', '\\#')
            resultado.append(r'\songchapter{' + chapter_title_escaped + '}')
            resultado.append(r'\begin{songs}{titleidx}')
            i += 1
            continue

        if temp_linea.startswith('O '):
            cerrar_bloque()
            cerrar_cancion()
            partes = temp_linea[2:].strip().split()
            transposicion = 0
            if partes and re.match(r'^=[+-]?\d+$', partes[-1]):
                transposicion = int(partes[-1].replace('=', ''))
                partes = partes[:-1]
            titulo_cancion_actual = ' '.join(partes).title()

            etiqueta = f"cancion-{limpiar_titulo_para_label(titulo_cancion_actual)}"

            title_escaped = titulo_cancion_actual.replace('#', '\\#')
            resultado.append(r'\beginsong{' + title_escaped + '}')
            resultado.append(rf'\index[titleidx]{{{title_escaped}}}')
            resultado.append(r'\phantomsection')
            resultado.append(rf'\label{{{etiqueta}}}')

            cancion_abierta = True
            i += 1
            continue

        if temp_linea.isupper() and len(temp_linea) > 1 and not es_linea_acordes(temp_linea) and temp_linea not in ('V', 'C', 'M', 'O', 'S', 'N'):
            cerrar_bloque()
            cerrar_cancion()
            titulo_cancion_actual = temp_linea.title()

            etiqueta = f"cancion-{limpiar_titulo_para_label(titulo_cancion_actual)}"

            title_escaped = titulo_cancion_actual.replace('#', '\\#')
            resultado.append(r'\beginsong{' + title_escaped + '}')
            resultado.append(r'\phantomsection')
            resultado.append(rf'\label{{{etiqueta}}}')

            cancion_abierta = True
            i += 1
            continue

        if temp_linea == 'O':
            cerrar_bloque()
            cerrar_cancion()
            titulo_cancion_actual = ""
            resultado.append(r'\beginsong{}')
            cancion_abierta = True
            i += 1
            continue

        if not cancion_abierta:
            # Si no hay canción abierta y encontramos contenido, crear una canción sin título
            resultado.append(r'\beginsong{}')
            cancion_abierta = True
            titulo_cancion_actual = "Sin título" # para que procesar_linea_con_acordes_y_indices pueda usarlo

        # Comandos de bloques
        if temp_linea == 'V':
            cerrar_bloque()
            tipo_bloque = 'verse'
            i += 1
            continue

        if temp_linea == 'M':
            cerrar_bloque()
            tipo_bloque = 'melody'
            i += 1
            continue

        if temp_linea == 'N':
            cerrar_bloque()
            tipo_bloque = 'nodiagram'
            i += 1
            continue

        if temp_linea == 'C':
            cerrar_bloque() # Siempre cierra el bloque anterior al iniciar uno nuevo
            tipo_bloque = 'chorus'
            i += 1
            continue

        # Procesa líneas con acordes separados del texto (línea de acordes + línea de letra)
        if i + 1 < len(lineas) and es_linea_acordes(temp_linea):
            acordes_originales = temp_linea.strip().split()
            acordes = [transportar_acorde(a, transposicion) for a in acordes_originales]

            letras_raw = lineas[i + 1].strip().replace('\\_', '_').replace('\\#', '#')

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

            # Caso especial para líneas de acorde sin letra explícita (solo '_')
            if letras_raw == '_':
                cerrar_bloque() # Esto puede ser un problema si '_ ' está al final de un verso.
                                # Quizás este caso debería ser manejado por procesar_bloque_simple
                acorde_cero_escapado = acordes[0].replace('#', '\\#')
                resultado.append(f"\\textnote{{{acorde_cero_escapado}}}")
                i += 2
                continue
            
            # Formatear línea de acordes
            acordes_escapados = [a.replace('#', '\\#') for a in acordes]
            linea_acordes_latex = '\\mbox{' + ' '.join([f'\\[{a}]' for a in acordes_escapados]) + '}'

            # Formatear línea de letra
            if '_' in letras_raw or '#' in letras_raw:
                linea_letras_latex = procesar_linea_con_acordes_y_indices(letras_raw, acordes, titulo_cancion_actual)
            else:
                linea_letras_latex = letras_raw.replace('#', '\\#') # Solo escapa # en texto literal

            # Añadir repeticiones
            if rep_ini and rep_fin:
                linea_letras_latex = r'\lrep ' + linea_letras_latex + rf' \rrep \rep{{{repeticiones}}}'
            elif rep_ini:
                linea_letras_latex = r'\lrep ' + linea_letras_latex
            elif rep_fin:
                linea_letras_latex = linea_letras_latex + rf' \rrep \rep{{{repeticiones}}}'

            # Agrega ambas líneas al bloque actual
            bloque_actual.append(linea_acordes_latex)
            bloque_actual.append(linea_letras_latex) # La función ya añade el \\ si es necesario.
            
            i += 2
            continue

        # Procesa líneas de texto dentro de un bloque existente
        if tipo_bloque and not es_linea_acordes(temp_linea):
            if temp_linea in ('V', 'C', 'M', 'N'):
                i += 1
                continue

            rep_ini = temp_linea.startswith('B ')
            if rep_ini:
                temp_linea = temp_linea[2:].lstrip()

            rep_fin = False
            repeticiones = 2

            m_fin = re.search(r'\s+[Bb]=(\d+)$', temp_linea)
            if m_fin:
                rep_fin = True
                repeticiones = int(m_fin.group(1))
                temp_linea = temp_linea[:m_fin.start()].rstrip()
            elif temp_linea.endswith(' B') or temp_linea.endswith(' b'):
                rep_fin = True
                temp_linea = temp_linea[:-2].rstrip()

            if '_' in temp_linea or '#' in temp_linea: # Si la línea contiene sintaxis de acordes/índices
                linea_procesada = procesar_linea_con_acordes_y_indices(temp_linea, [], titulo_cancion_actual)
            else: # Línea de texto simple
                linea_procesada = temp_linea.replace('#', '\\#') # Escapar '#'

            if rep_ini and rep_fin:
                linea_procesada = r'\lrep ' + linea_procesada + rf' \rrep \rep{{{repeticiones}}}'
            elif rep_ini:
                linea_procesada = r'\lrep ' + linea_procesada
            elif rep_fin:
                linea_procesada = linea_procesada + rf' \rrep \rep{{{repeticiones}}}'

            bloque_actual.append(linea_procesada)
            i += 1
            continue
        
        # Si llegamos aquí y hay una canción abierta, pero la línea no es un comando de bloque,
        # un par acorde/letra, ni dentro de un bloque, entonces es texto "suelto" de la canción.
        # Debe ser añadido al bloque actual (posiblemente un 'verse' implícito si no hay otro).
        # Esto podría ser lo que faltaba para líneas que no se capturaban.
        if cancion_abierta and temp_linea:
            # Asegurar que si hay acordes embebidos o índices en este texto suelto, se procesen.
            if '_' in temp_linea or '#' in temp_linea:
                linea_procesada = procesar_linea_con_acordes_y_indices(temp_linea, [], titulo_cancion_actual)
            else:
                linea_procesada = temp_linea.replace('#', '\\#')
            
            # Si no hay bloque abierto, se asume un verso
            if tipo_bloque is None:
                tipo_bloque = 'verse' # Iniciar un verso implícito
            
            # Aseguramos que se añade un salto de línea LaTeX
            bloque_actual.append(linea_procesada + r'\\')
            i += 1
            continue

        # Si llegamos aquí y la línea no fue procesada por ninguna de las condiciones anteriores,
        # simplemente avanza.
        i += 1

    cerrar_bloque()
    cerrar_cancion()
    if seccion_abierta:
        resultado.append(r'\end{songs}')

    return '\n'.join(resultado) if resultado else "% No se generó contenido válido"


def normalizar(palabra):
    return ''.join(
        c for c in unicodedata.normalize('NFD', palabra.lower())
        if unicodedata.category(c) != 'Mn'
    )

def convertir_a_latina(acorde):
    if '/' in acorde:
        parte_superior, bajo = acorde.split('/')
        parte_superior = equivalencias_latinas.get(parte_superior, parte_superior)
        bajo = equivalencias_latinas.get(bajo, bajo)
        return f"{parte_superior}/{bajo}"
    return equivalencias_latinas.get(acorde, acorde)

def limpiar_titulo_para_label(titulo):
    titulo = re.sub(r'\s*=[+-]?\d+\s*$', '', titulo.strip())
    titulo = unicodedata.normalize('NFD', titulo)
    titulo = ''.join(c for c in titulo if unicodedata.category(c) != 'Mn')
    titulo = re.sub(r'[^a-zA-Z0-9\- ]+', '', titulo)
    return titulo.replace(' ', '-')

def generar_indice_tematica():
    if not indice_tematica_global:
        return ""

    resultado = [r"\section*{Índice Temático}", r"\begin{itemize}"]

    for palabra in sorted(indice_tematica_global.keys(), key=normalizar):
        canciones = sorted(list(indice_tematica_global[palabra]), key=normalizar)
        
        # CORRECCIÓN: Evitar la barra invertida directa en el f-string
        enlaces = [
            rf"\hyperref[cancion-{limpiar_titulo_para_label(c)}]{{{c.replace('#', '\\#')}}}"
            for c in canciones
        ]
        
        palabra_titulo_escapada = palabra.title().replace('#', '\\#')
        resultado.append(rf"  \item \textbf{{{palabra_titulo_escapada}}} --- {', '.join(enlaces)}")

    resultado.append(r"\end{itemize}")
    return '\n'.join(resultado)

def compilar_tex_seguro(tex_path):
    tex_dir = os.path.dirname(tex_path) or "."
    tex_file = os.path.basename(tex_path)

    try:
        logs = ""
        # Primera compilación
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_file],
            capture_output=True,
            text=True,
            cwd=tex_dir
        )
        logs += "\n--- COMPILACIÓN 1 ---\n" + result.stdout + result.stderr
        if result.returncode != 0:
            raise RuntimeError(f"Error compilando LaTeX en la primera iteración.\nLog completo:\n{logs}")

        base = os.path.splitext(tex_file)[0]
        posibles_indices = [
            (f"{base}.idx", None),
            (f"{base}.tema.idx", f"{base}.tema.ind"),
            (f"{base}.titleidx", f"{base}.titleidx.ind"), # Corregir este, imakeidx usa .idx por defecto
        ]
        for entrada, salida in posibles_indices:
            entrada_path = os.path.join(tex_dir, entrada)
            if os.path.exists(entrada_path):
                cmd = ["makeindex", entrada]
                if salida is not None:
                    cmd = ["makeindex", "-o", salida, entrada]
                else: # Si no hay salida definida, makeindex por defecto genera .ind
                    cmd = ["makeindex", entrada] # makeindex -o base.ind base.idx
                    
                mi = subprocess.run(cmd, capture_output=True, text=True, cwd=tex_dir)
                logs += "\n--- MAKEINDEX ---\n" + mi.stdout + mi.stderr

        # Segunda y tercera compilación para manejar índices y referencias cruzadas
        for i in range(2): 
            result_loop = subprocess.run(
                ["pdflatex", "-interaction=nonstopmode", tex_file],
                capture_output=True,
                text=True,
                cwd=tex_dir
            )
            logs += f"\n--- COMPILACIÓN {i+2} ---\n" + result_loop.stdout + result_loop.stderr
            if result_loop.returncode != 0:
                raise RuntimeError(f"Error compilando LaTeX en la iteración {i+2}.\nLog completo:\n{logs}")

        pdf_file = os.path.splitext(tex_path)[0] + ".pdf"
        if not os.path.exists(pdf_file):
            raise RuntimeError(f"No se generó el PDF. Revisa el log:\n{logs}")

        return logs

    except Exception as e:
        raise RuntimeError(f"Excepción en compilación: {e}\n{logs}")

@app.route("/", methods=["GET", "POST"])
def index():
    texto = ""
    filename = archivo_por_defecto
    try:
        if request.method == "POST":
            accion = request.form.get("accion")
            filename = request.form.get("filename", archivo_por_defecto)
            uploaded_file = request.files.get("archivo")

            # Priorizar el archivo subido si existe
            if uploaded_file and uploaded_file.filename:
                texto = uploaded_file.read().decode("utf-8")
                filename = uploaded_file.filename
                return render_template_string(FORM_HTML, texto=texto, filename=filename, mensaje_exito=f"Archivo '{filename}' cargado exitosamente.")

            if accion == "guardar":
                try:
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(request.form.get("texto", ""))
                    return render_template_string(FORM_HTML, texto=request.form.get("texto", ""), filename=filename, mensaje_exito=f"Archivo '{filename}' guardado con éxito.")
                except Exception:
                    return f"<h3>Error guardando archivo:</h3><pre>{traceback.format_exc()}</pre>"

            if accion == "abrir":
                if os.path.exists(filename):
                    with open(filename, "r", encoding="utf-8") as f:
                        texto = f.read()
                    return render_template_string(FORM_HTML, texto=texto, filename=filename, mensaje_exito=f"Archivo '{filename}' cargado con éxito.")
                else:
                    return render_template_string(FORM_HTML, texto="", filename=filename, mensaje_error=f"El archivo '{filename}' no existe.")

            if accion == "generar_pdf":
                # Reiniciar el índice temático global para cada generación de PDF
                global indice_tematica_global
                indice_tematica_global = {}

                try:
                    contenido_canciones = convertir_songpro(request.form.get("texto", ""))
                    indice_tematica = generar_indice_tematica()

                    def reemplazar(match):
                        return match.group(1) + "\n" + contenido_canciones + "\n\n" + indice_tematica + "\n" + match.group(3)

                    # Usar un nombre de archivo fijo para la compilación del PDF para evitar problemas
                    archivo_salida_tex = "cancionero_compilado.tex"
                    nuevo_tex = re.sub(
                        r"(% --- INICIO CANCIONERO ---)(.*?)(% --- FIN CANCIONERO ---)",
                        reemplazar,
                        plantilla,
                        flags=re.S
                    )
                    with open(archivo_salida_tex, "w", encoding="utf-8") as f:
                        f.write(nuevo_tex)

                    logs = compilar_tex_seguro(archivo_salida_tex)

                    pdf_file = os.path.splitext(archivo_salida_tex)[0] + ".pdf"
                    if os.path.exists(pdf_file):
                        return send_file(pdf_file, as_attachment=False)
                    else:
                        return f"<h3>PDF no generado.</h3><pre>Logs de compilación:\n{logs}</pre>"

                except Exception:
                    return f"<h3>Error en generar PDF:</h3><pre>{traceback.format_exc()}</pre>"

        if 'filename' in request.args:
            filename = request.args.get('filename')
            if os.path.exists(filename):
                with open(filename, "r", encoding="utf-8") as f:
                    texto = f.read()
        return render_template_string(FORM_HTML, texto=texto, filename=filename)

    except Exception:
        return f"<h3>Error inesperado:</h3><pre>{traceback.format_exc()}</pre>"

FORM_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Editor de Canciones</title>
    <style>
        body { font-family: sans-serif; margin: 20px; }
        h2 { color: #333; }
        textarea { width: 90%; max-width: 800px; height: 400px; padding: 10px; border: 1px solid #ccc; }
        input[type="text"] { width: 90%; max-width: 300px; padding: 8px; border: 1px solid #ccc; }
        input[type="file"] { margin-top: 10px; }
        button { padding: 10px 15px; background-color: #007bff; color: white; border: none; cursor: pointer; margin-right: 10px; }
        button:hover { background-color: #0056b3; }
        p.success { color: green; }
        p.error { color: red; }
    </style>
</head>
<body>
    <h2>Editor de Canciones</h2>
    {% if mensaje_exito %}
        <p class="success">{{ mensaje_exito }}</p>
    {% endif %}
    {% if mensaje_error %}
        <p class="error">{{ mensaje_error }}</p>
    {% endif %}
    <form method="post" enctype="multipart/form-data">
        <p>
            Para "Guardar como", introduce un nuevo nombre de archivo en el campo de texto y haz clic en "Guardar".
        </p>
        <label for="filename">Nombre del archivo:</label>
        <input type="text" id="filename" name="filename" value="{{ filename }}"><br><br>

        <textarea name="texto" rows="20" cols="80" placeholder="Escribe tus canciones aquí...">{{ texto }}</textarea><br>

        <label for="archivo">O cargar un archivo de texto desde tu equipo:</label>
        <input type="file" name="archivo" id="archivo"><br><br>

        <button type="submit" name="accion" value="guardar">Guardar</button>
        <button type="submit" name="accion" value="abrir">Abrir</button>
        <button type="submit" name="accion" value="generar_pdf">Generar PDF</button>
    </form>
</body>
</html>
"""

@app.route("/health", methods=["GET"])
def health():
    return "ok", 200

@app.route("/ver_log")
def ver_log():
    log_file = "cancionero_compilado.log"
    if os.path.exists(log_file):
        return send_file(log_file, mimetype="text/plain")
    else:
        return f"<h3>No se encontró el archivo de log '{log_file}'.</h3>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
