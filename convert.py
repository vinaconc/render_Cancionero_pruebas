from flask import Flask, request, render_template_string, send_file, Response
import traceback
import os
import subprocess
import re
import unicodedata

app = Flask(__name__)

archivo_plantilla = "plantilla.tex"
archivo_salida = "cancionero_web.tex"

with open(archivo_plantilla, "r", encoding="utf-8") as f:
    plantilla = f.read()

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
        bajo_transposto = transportar_acorde(bajo, semitonos)
        return f"{parte_superior_transpuesta}/{bajo_transposto}"
    # Mapa de conversión de bemoles a sostenidos para procesamiento interno
    mapa_bemoles_a_sostenidos = {
        'Reb': 'Do#', 'Rebm': 'Do#m',
        'Mib': 'Re#', 'Mibm': 'Re#m',
        'Lab': 'Sol#', 'Labm': 'Sol#m',
        'Sib': 'La#', 'Sibm': 'La#m'
    }
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
    return convertir_a_latex(acorde_transpuesto)

def limpiar_para_indice(palabra):
    return re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]', '', palabra)

def es_linea_acordes(linea):
    tokens = linea.split()
    if not tokens:
        return False
    for t in tokens:
        if re.match(r'^[A-G][#b]?(m|maj|min|dim|aug|sus|add)?\d*(/[A-G][#b]?)?$', t, re.IGNORECASE):
            continue
        notas_latinas = ['do', 're', 'mi', 'fa', 'sol', 'la', 'si']
        notas_latinas_bemoles = ['reb', 'mib', 'lab', 'sib']
        notas_latinas_sostenidos = ['do#', 're#', 'fa#', 'sol#', 'la#']
        if any(t.lower().startswith(n.lower()) for n in notas_latinas) or \
           any(t.lower().startswith(n.lower()) for n in notas_latinas_bemoles) or \
           any(t.lower().startswith(n.lower()) for n in notas_latinas_sostenidos):
            continue
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
    mapa_bemoles_excepcion = {
        'La#': 'Sib', 'La#m': 'Sibm'
    }
    acorde = acorde.strip()
    acorde = acorde.replace('Bb', 'A#').replace('bb', 'a#')
    acorde = acorde.replace('Gb', 'F#').replace('gb', 'f#')
    if any(acorde.lower().startswith(n.lower()) for n in ['do', 're', 'mi', 'fa', 'sol', 'la', 'si']):
        return acorde
    if '/' in acorde:
        parte_superior, bajo = acorde.split('/')
        parte_superior = convertir_a_latex(parte_superior)
        bajo = convertir_a_latex(bajo)
        return f"{parte_superior}/{bajo}"
    match = re.match(r'^([A-Ga-g][#b]?m?)(.*)$', acorde)
    if match:
        raiz, extension = match.groups()
        raiz_mayus = raiz[0].upper() + raiz[1:]
        raiz_convertida = mapa.get(raiz_mayus, raiz)
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
                acorde_escapado = acordes[idx_acorde].replace('#', '\\#')
                resultado += f"\\raisebox{{1.7ex}}{{\\[{acorde_escapado}]}} "
                idx_acorde += 1
            else:
                resultado += '_ '
            continue
        if '_' in base:
            partes = base.split('_')
            latex = ''
            for i, parte in enumerate(partes):
                if i > 0 and idx_acorde < len(acordes):
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
                resultado += f"\\textcolor{{blue!50!black}}{{\\textbf{{{latex}}}}}\\protect\\index[tema]{{{palabra_para_indice}}} "
            else:
                resultado += latex + ' '
        else:
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
        else:
            return (None, None)
    def cerrar_bloque():
        nonlocal bloque_actual, tipo_bloque
        if bloque_actual:
            if tipo_bloque == 'nodiagram':
                resultado.append(r'\beginverse')
                resultado.append(r'\begin{minipage}[t]{0.4\textwidth}')
                resultado.append(r'\vspace{-2.5em}')
                resultado.append(r'\centering')
                resultado.append(procesar_bloque_simple('\n'.join(bloque_actual), transposicion, es_seccion_n=True))
                resultado.append(r'\vspace{-1em}')
                resultado.append(r'\end{minipage}')
                resultado.append(r'\endverse')
            else:
                begin_end = entorno(tipo_bloque)
                if begin_end == (None, None):
                    # Manejar caso no reconocido
                    return
                begin, end = begin_end
                if tipo_bloque == 'verse':
                    letra_diagrama = 'A'
                elif tipo_bloque == 'chorus':
                    letra_diagrama = 'B'
                elif tipo_bloque == 'melody':
                    letra_diagrama = 'C'
                else:
                    letra_diagrama = 'A'
                # Mejor usar salto de línea para unir, evita errores en LaTeX
                contenido = '\n'.join(bloque_actual)
                contenido = contenido.replace('"', '')
                resultado.append(begin)
                resultado.append(f"\\diagram{{{letra_diagrama}}}{{{contenido}}}")
                resultado.append(end)
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
    def procesar_bloque_simple(texto, transposicion, es_seccion_n=False):
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
                if es_seccion_n:
                    acordes_convertidos = [a.replace('#', r'\#') for a in acordes_convertidos]
                latex_acordes = ' '.join(f'\[{a}]' for a in acordes_convertidos)
                resultado.append(rf'\textnote{{{texto.strip()}}}')
                resultado.append(rf'\mbox{{{latex_acordes}}}')
                continue
            if es_linea_acordes(linea):
                acordes = linea.split()
                acordes_convertidos = [transportar_acorde(a, transposicion) for a in acordes]
                if es_seccion_n:
                    acordes_convertidos = [a.replace('#', r'\#') for a in acordes_convertidos]
                latex_acordes = ' '.join(f'\[{a}]' for a in acordes_convertidos)
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
            acordes_linea_anterior = []
            i += 1
            continue
        if linea == 'M':
            cerrar_bloque()
            tipo_bloque = 'melody'
            acordes_linea_anterior = []
            i += 1
            continue
        if linea == 'N':
            cerrar_bloque()
            tipo_bloque = 'nodiagram'
            i += 1
            continue
        if i + 2 < len(lineas) and es_linea_acordes(lineas[i + 1]) and not es_linea_acordes(lineas[i + 2]):
            acordes_originales = lineas[i + 1].strip().split()
            acordes = [transportar_acorde(a, transposicion) for a in acordes_originales]
            letras_raw = lineas[i + 2].strip()
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
                i += 3
                continue
            if not ('_' in letras_raw or '#' in letras_raw):
                acordes_escapados = [a.replace('#', '\\#') for a in acordes]
                bloque_actual.append('\\mbox{' + ' '.join([f'\\[{a}]' for a in acordes_escapados]) + '}')
                bloque_actual.append(letras_raw)
                i += 3
                continue
            linea_convertida = procesar_linea_con_acordes_y_indices(letras_raw, acordes, titulo_cancion_actual)
            if rep_ini and rep_fin:
                linea_convertida = r'\lrep ' + linea_convertida + rf' \rrep \rep{{{repeticiones}}}'
            elif rep_ini:
                linea_convertida = r'\lrep ' + linea_convertida
            elif rep_fin:
                linea_convertida = linea_convertida + rf' \rrep \rep{{{repeticiones}}}'
            bloque_actual.append(linea_convertida)
            i += 3
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
                linea_procesada = r'\\lrep ' + linea_procesada + rf' \\rrep \\rep{{{repeticiones}}}'
            elif rep_ini:
                linea_procesada = r'\\lrep ' + linea_procesada
            elif rep_fin:
                linea_procesada = linea_procesada + rf' \\rrep \\rep{{{repeticiones}}}'
            bloque_actual.append(linea_procesada)
            i += 1
            continue
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
        enlaces = [
            rf"\hyperref[cancion-{limpiar_titulo_para_label(c)}]" + f"{{{c}}}"
            for c in canciones
        ]
        resultado.append(rf"  \item \textbf{{{palabra.title()}}} --- {', '.join(enlaces)}")
    resultado.append(r"\end{itemize}")
    return '\n'.join(resultado)

def compilar_tex_seguro(tex_path):
    tex_dir = os.path.dirname(tex_path) or "."
    tex_file = os.path.basename(tex_path)
    try:
        logs = ""
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
            (f"{base}.cbtitle", f"{base}.cbtitle.ind"),
        ]
        for entrada, salida in posibles_indices:
            entrada_path = os.path.join(tex_dir, entrada)
            if os.path.exists(entrada_path):
                cmd = ["makeindex", entrada]
                if salida is not None:
                    cmd = ["makeindex", "-o", salida, entrada]
                mi = subprocess.run(cmd, capture_output=True, text=True, cwd=tex_dir)
                logs += "\n--- MAKEINDEX ---\n" + mi.stdout + mi.stderr
        result2 = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_file],
            capture_output=True,
            text=True,
            cwd=tex_dir
        )
        logs += "\n--- COMPILACIÓN 2 ---\n" + result2.stdout + result2.stderr
        if result2.returncode != 0:
            raise RuntimeError(f"Error compilando LaTeX en la segunda iteración.\nLog completo:\n{logs}")
        pdf_file = os.path.splitext(tex_path)[0] + ".pdf"
        if not os.path.exists(pdf_file):
            raise RuntimeError(f"No se generó el PDF. Revisa el log:\n{logs}")
        return logs
    except Exception as e:
        raise RuntimeError(f"Excepción en compilación: {e}\n{logs}")

@app.route("/", methods=["GET", "POST"])
def index():
    texto = ""
    try:
        if request.method == "POST":
            accion = request.form.get("accion")
            texto = request.form.get("texto", "")
            uploaded_file = request.files.get("archivo")
            if uploaded_file and uploaded_file.filename:
                texto = uploaded_file.read().decode("utf-8")
            if accion == "generar_pdf":
                try:
                    contenido_canciones = convertir_songpro(texto)
                    indice_tematica = generar_indice_tematica()
                    def reemplazar(match):
                        return match.group(1) + "\n" + contenido_canciones + "\n\n" + indice_tematica + "\n" + match.group(3)
                    nuevo_tex = re.sub(
                        r"(% --- INICIO CANCIONERO ---)(.*?)(% --- FIN CANCIONERO ---)",
                        reemplazar,
                        plantilla,
                        flags=re.S
                    )
                    with open(archivo_salida, "w", encoding="utf-8") as f:
                        f.write(nuevo_tex)
                    logs = compilar_tex_seguro(archivo_salida)
                    pdf_file = os.path.splitext(archivo_salida)[0] + ".pdf"
                    if os.path.exists(pdf_file):
                        return send_file(pdf_file, as_attachment=False)
                    else:
                        return "<h3>PDF no generado.</h3>"
                except Exception:
                    return f"<h3>Error en generar PDF:</h3><pre>{traceback.format_exc()}</pre>"
        return render_template_string(FORM_HTML, texto=texto)
    except Exception:
        return f"<h3>Error inesperado:</h3><pre>{traceback.format_exc()}</pre>"

FORM_HTML = """
<h2>Creador Cancionero</h2>
<form method="post" enctype="multipart/form-data">
    <textarea id="texto" name="texto" rows="20" cols="80" placeholder="Escribe tus canciones aquí...">{{ texto }}</textarea><br>
    <button type="button" id="btnInsertB">Repit</button>
    <button type="button" id="btnInsertUnderscore">Chord</button><br><br>
    <label for="archivo">O sube un archivo de texto:</label>
    <input type="file" name="archivo" id="archivo"><br><br>
    <!-- Menú de acciones -->
    <button type="submit" name="accion" value="abrir">Abrir</button>
    <button type="submit" formaction="/descargar">Guardar como (descargar)</button>
    <button type="submit" name="accion" value="generar_pdf">Generar PDF</button>
</form>
<script>
function insertarTexto(texto) {
    const textarea = document.getElementById("texto");
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const value = textarea.value;
    textarea.value = value.substring(0, start) + texto + value.substring(end);
    textarea.selectionStart = textarea.selectionEnd = start + texto.length;
    textarea.focus();
}
document.getElementById("btnInsertB").addEventListener("click", function() {
    insertarTexto("B");
});
document.getElementById("btnInsertUnderscore").addEventListener("click", function() {
    insertarTexto("_");
});
</script>
"""

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)







