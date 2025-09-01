from flask import Flask, request, render_template_string, send_file
import traceback
import os
import subprocess
import re
import unicodedata

# ----------------- INICIO DEL PREÁMBULO -----------------
app = Flask(__name__)

# Directorio para guardar los archivos de los usuarios
CARPETA_ARCHIVOS = "./archivos_locales"
os.makedirs(CARPETA_ARCHIVOS, exist_ok=True)

archivo_plantilla = "plantilla.tex"
# Esta ruta se usará para el archivo temporal del PDF
archivo_salida = os.path.join(CARPETA_ARCHIVOS, "cancionero_web.tex")

try:
    with open(archivo_plantilla, "r", encoding="utf-8") as f:
        plantilla = f.read()
except FileNotFoundError:
    plantilla = """
    \\documentclass{article}
    \\begin{document}
    % --- INICIO CANCIONERO ---
    % --- FIN CANCIONERO ---
    \\end{document}
    """
    print(f"Advertencia: No se encontró '{archivo_plantilla}'. Usando plantilla por defecto.")

indice_tematica_global = {}

notas = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
equivalencias_latinas = {
    'Do': 'C', 'Do#': 'C#', 'Re': 'D', 'Re#': 'D#', 'Mi': 'E', 'Fa': 'F',
    'Fa#': 'F#', 'Sol': 'G', 'Sol#': 'G#', 'La': 'A', 'La#': 'A#', 'Si': 'B'
}

# ----------------- FIN DEL PREÁMBULO -----------------

def escapar_latex(texto):
    """Escapa caracteres especiales de LaTeX para evitar errores de compilación."""
    if not isinstance(texto, str):
        return texto
    
    # Manejar acentos y ñ
    texto = texto.replace('á', "\\'a").replace('é', "\\'e").replace('í', "\\'i")
    texto = texto.replace('ó', "\\'o").replace('ú', "\\'u").replace('ñ', "\\~n")
    texto = texto.replace('Á', "\\'A").replace('É', "\\'E").replace('Í', "\\'I")
    texto = texto.replace('Ó', "\\'O").replace('Ú', "\\'U").replace('Ñ', "\\~N")
    
    # Escapar otros caracteres especiales
    return texto.replace('\\', '\\textbackslash{}') \
                 .replace('{', '\\{').replace('}', '\\}') \
                 .replace('#', '\\#').replace('$', '\\$') \
                 .replace('%', '\\%').replace('&', '\\&') \
                 .replace('~', '\\~{}').replace('_', '\\_') \
                 .replace('^', '\\^{}')

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

    mapa_bemoles_a_sostenidos = {
        'Reb': 'Do#', 'Rebm': 'Do#m', 'Mib': 'Re#', 'Mibm': 'Re#m',
        'Lab': 'Sol#', 'Labm': 'Sol#m', 'Sib': 'La#', 'Sibm': 'La#m'
    }

    for bemol, sostenido in mapa_bemoles_a_sostenidos.items():
        if acorde.lower().startswith(bemol.lower()):
            acorde = sostenido + acorde[len(bemol):]
            break			

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

    return nueva_nota + sufijo

def limpiar_para_indice(palabra):
    return re.sub(r'[^a-zA-Z0-9áéíóúÁÉÍÓÚñÑ]', '', palabra)

def es_linea_acordes(linea):
    tokens = linea.strip().split()
    if not tokens:
        return False
    
    for t in tokens:
        # Simplificación de la lógica para detectar acordes
        if not (re.match(r'^[A-G][#b]?(m|maj|min|dim|aug|sus|add)?\d*(/[A-G][#b]?)?$', t, re.IGNORECASE) or
                any(t.lower().startswith(n.lower()) for n in ['do', 're', 'mi', 'fa', 'sol', 'la', 'si', 'reb', 'mib', 'lab', 'sib', 'do#', 're#', 'fa#', 'sol#', 'la#'])):
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
    mapa_bemoles_excepcion = { 'La#': 'Sib', 'La#m': 'Sibm' }

    acorde = acorde.strip()
    acorde = acorde.replace('Bb', 'A#').replace('bb', 'a#')
    acorde = acorde.replace('Gb', 'F#').replace('gb', 'f#')

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
        raiz_convertida = mapa_bemoles_excepcion.get(raiz_convertida, raiz_convertida)
        return raiz_convertida + extension

    return acorde

def procesar_linea_con_acordes_y_indices(linea, acordes, titulo_cancion):
    resultado = ''
    idx_acorde = 0
    
    # Reemplazar los marcadores de acordes ('_') con un marcador temporal
    linea_con_marcadores = linea.replace('_', '§_§')
    
    # Separar la línea por los marcadores
    partes = linea_con_marcadores.split('§_§')

    for i, parte in enumerate(partes):
        # Insertar acorde si estamos entre dos partes de texto
        if i > 0 and idx_acorde < len(acordes):
            # Escapar sostenidos en acordes para LaTeX
            acorde_escapado = escapar_latex(acordes[idx_acorde])
            resultado += f"\\raisebox{{1.7ex}}{{\\[{acorde_escapado}]}}"
            idx_acorde += 1
        
        palabras_parte = parte.strip().split()
        
        for palabra in palabras_parte:
            es_indexada = palabra.startswith('#')
            texto_base = palabra[1:] if es_indexada else palabra
            
            if es_indexada and '=' in texto_base:
                texto_base, indice_real = texto_base.split('=', 1)
            else:
                indice_real = None
            
            palabra_para_indice = limpiar_para_indice(indice_real if indice_real else texto_base)
            
            if es_indexada:
                if palabra_para_indice not in indice_tematica_global:
                    indice_tematica_global[palabra_para_indice] = set()
                titulo_indexado = re.sub(r'\s*=[+-]?\d+\s*$', '', titulo_cancion.strip()) if titulo_cancion else "Sin título"
                indice_tematica_global[palabra_para_indice].add(titulo_indexado)
                
                texto_escapado = escapar_latex(texto_base)
                resultado += f"\\textcolor{{blue!50!black}}{{\\textbf{{{texto_escapado}}}}}\\protect\\index[tema]{{{palabra_para_indice}}} "
            else:
                resultado += escapar_latex(palabra) + ' '
                
    return resultado.strip()


def convertir_songpro(texto):
    global indice_tematica_global
    indice_tematica_global = {} # Limpiar al inicio de cada conversión
    referencia_pendiente = None
    lineas = [linea.rstrip() for linea in texto.strip().split('\n')]
    resultado = []
    bloque_actual = []
    tipo_bloque = None
    seccion_abierta = False
    cancion_abierta = False
    titulo_cancion_actual = ""
    transposicion = 0
    acordes_linea_anterior = []

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
            begin, end = entorno(tipo_bloque)
            letra_diagrama = 'A' if tipo_bloque == 'verse' else 'B' if tipo_bloque == 'chorus' else 'C'
            contenido = ' \\\\'.join(bloque_actual) + ' \\\\'
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
                resultado.append(rf'\beginscripture{{[{escapar_latex(referencia_pendiente)}]}}')
                resultado.append(r'\endscripture')
                referencia_pendiente = None
            cancion_abierta = False

    def procesar_bloque_simple(texto, transposicion):
        lineas = texto.strip().split('\n')
        resultado_lineas = []
        for linea in lineas:
            linea = linea.strip()
            if not linea:
                continue
            match = re.match(r'^([^:]+):\s*(.*)$', linea)
            if match:
                texto, acordes_linea = match.groups()
                acordes = acordes_linea.split()
                acordes_convertidos = [transportar_acorde(a, transposicion) for a in acordes]
                acordes_escapados = [escapar_latex(a) for a in acordes_convertidos]
                latex_acordes = ' '.join(f'\\[{a}]' for a in acordes_escapados)
                resultado_lineas.append(rf'\textnote{{{escapar_latex(texto.strip())}}}')
                resultado_lineas.append(rf'\mbox{{{latex_acordes}}}')
                continue
            if es_linea_acordes(linea):
                acordes = linea.split()
                acordes_convertidos = [transportar_acorde(a, transposicion) for a in acordes]
                acordes_escapados = [escapar_latex(a) for a in acordes_convertidos]
                latex_acordes = ' '.join(f'\\[{a}]' for a in acordes_escapados)
                resultado_lineas.append(rf'\mbox{{{latex_acordes}}}')
                continue
            else:
                if linea.strip() in ('V', 'C', 'M', 'N'):
                    continue
                resultado_lineas.append(escapar_latex(linea) + r'\\')
        return '\n'.join(resultado_lineas)

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
            resultado.append(r'\songchapter{' + escapar_latex(linea[2:].strip().title()) + '}')
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
            resultado.append(r'\beginsong{' + escapar_latex(titulo_cancion_actual) + '}')
            resultado.append(rf'\index[titleidx]{{{escapar_latex(titulo_cancion_actual)}}}')
            resultado.append(r'\phantomsection')
            resultado.append(rf'\label{{{etiqueta}}}')
            cancion_abierta = True
            i += 1
            continue
        
        # Este bloque estaba duplicado y era problemático
        # if linea.isupper() and len(linea) > 1 and not es_linea_acordes(linea) and linea not in ('V', 'C', 'M', 'O', 'S'):
        # ... se eliminó para evitar inconsistencias

        if not cancion_abierta:
            resultado.append(r'\beginsong{}')
            cancion_abierta = True

        if linea == 'V':
            cerrar_bloque()
            tipo_bloque = 'verse'
            i += 1
            continue

        if linea == 'C':
            if i + 1 < len(lineas) and es_linea_acordes(lineas[i + 1].strip()):
                cerrar_bloque()
                tipo_bloque = 'chorus'
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
        
        # Procesar acordes y letra
        if i + 1 < len(lineas) and es_linea_acordes(lineas[i]):
            acordes_originales = lineas[i].strip().split()
            acordes = [transportar_acorde(a, transposicion) for a in acordes_originales]
            letras_raw = lineas[i + 1].strip()
            
            linea_convertida = procesar_linea_con_acordes_y_indices(letras_raw, acordes, titulo_cancion_actual)
            bloque_actual.append(linea_convertida)
            i += 2
            continue
        
        # Procesar solo texto
        if tipo_bloque and not es_linea_acordes(linea):
            if linea in ('V', 'C', 'M', 'N'):
                i += 1
                continue
            
            # Repeticiones
            rep_ini = linea.startswith('B ')
            if rep_ini: linea = linea[2:].lstrip()
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

            linea_procesada = procesar_linea_con_acordes_y_indices(linea, [], titulo_cancion_actual)
            
            if rep_ini and rep_fin:
                linea_procesada = r'\lrep ' + linea_procesada + rf' \rrep \rep{{{repeticiones}}}'
            elif rep_ini:
                linea_procesada = r'\lrep ' + linea_procesada
            elif rep_fin:
                linea_procesada = linea_procesada + rf' \rrep \rep{{{repeticiones}}}'

            bloque_actual.append(linea_procesada)
            i += 1
            continue

        # Si ninguna de las reglas anteriores aplica, solo pasar la línea como texto
        bloque_actual.append(escapar_latex(linea))
        i += 1

    cerrar_bloque()
    cerrar_cancion()
    if seccion_abierta:
        resultado.append(r'\end{songs}')

    return '\n'.join(resultado) if resultado else "% No se generó contenido válido"


def normalizar(palabra):
    return ''.join(c for c in unicodedata.normalize('NFD', palabra.lower()) if unicodedata.category(c) != 'Mn')

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
        enlaces = [rf"\hyperref[cancion-{limpiar_titulo_para_label(c)}]" + f"{{{c}}}" for c in canciones]
        resultado.append(rf"  \item \textbf{{{palabra.title()}}} --- {', '.join(enlaces)}")
    resultado.append(r"\end{itemize}")
    return '\n'.join(resultado)

def compilar_tex_seguro(tex_path):
    tex_dir = os.path.dirname(tex_path) or "."
    tex_file = os.path.basename(tex_path)
    try:
        logs = ""
        result = subprocess.run(["pdflatex", "-interaction=nonstopmode", tex_file], capture_output=True, text=True, cwd=tex_dir)
        logs += "\n--- COMPILACIÓN 1 ---\n" + result.stdout + result.stderr
        if result.returncode != 0: raise RuntimeError(f"Error compilando LaTeX en la primera iteración.\nLog completo:\n{logs}")
        base = os.path.splitext(tex_file)[0]
        posibles_indices = [(f"{base}.idx", None), (f"{base}.tema.idx", f"{base}.tema.ind"), (f"{base}.cbtitle", f"{base}.cbtitle.ind")]
        for entrada, salida in posibles_indices:
            entrada_path = os.path.join(tex_dir, entrada)
            if os.path.exists(entrada_path):
                cmd = ["makeindex", entrada]
                if salida is not None: cmd = ["makeindex", "-o", salida, entrada]
                mi = subprocess.run(cmd, capture_output=True, text=True, cwd=tex_dir)
                logs += "\n--- MAKEINDEX ---\n" + mi.stdout + mi.stderr
        result2 = subprocess.run(["pdflatex", "-interaction=nonstopmode", tex_file], capture_output=True, text=True, cwd=tex_dir)
        logs += "\n--- COMPILACIÓN 2 ---\n" + result2.stdout + result2.stderr
        if result2.returncode != 0: raise RuntimeError(f"Error compilando LaTeX en la segunda iteración.\nLog completo:\n{logs}")
        pdf_file = os.path.splitext(tex_path)[0] + ".pdf"
        if not os.path.exists(pdf_file): raise RuntimeError(f"No se generó el PDF. Revisa el log:\n{logs}")
        return logs
    except Exception as e:
        raise RuntimeError(f"Excepción en compilación: {e}\n{logs}")

# 🔹 HTML con "menú" y opción de generar PDF
FORM_HTML = """
<h2>Editor de Canciones</h2>
<form method="post" enctype="multipart/form-data">
    {% if mensaje %}
        <p style="color: green;">{{ mensaje }}</p>
    {% endif %}
    {% if logs %}
        <div style="background: #f8d7da; color: #721c24; padding: 10px; margin-bottom: 10px; border: 1px solid #f5c6cb;">
            <h3>Error de compilación de PDF:</h3>
            <pre>{{ logs }}</pre>
        </div>
    {% endif %}
    <textarea name="texto" rows="20" cols="80" placeholder="Escribe tus canciones aquí...">{{ texto }}</textarea><br>
    
    <div style="margin-top: 10px; margin-bottom: 10px;">
        <label for="archivo">Sube un archivo:</label>
        <input type="file" name="archivo" id="archivo">
    </div>

    <button type="submit" name="accion" value="guardar">Guardar como</button>
    <button type="submit" name="accion" value="cargar_archivo">Cargar archivo</button>
    <button type="submit" name="accion" value="generar_pdf">Generar PDF</button>
</form>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    texto = ""
    mensaje = ""
    logs = ""
    
    try:
        if request.method == "POST":
            accion = request.form.get("accion")

            if accion == "cargar_archivo":
                uploaded_file = request.files.get("archivo")
                if uploaded_file and uploaded_file.filename:
                    texto = uploaded_file.read().decode("utf-8")
                    mensaje = f"Archivo '{uploaded_file.filename}' cargado para su edición."
                else:
                    mensaje = "Error: No se seleccionó ningún archivo para cargar."
                return render_template_string(FORM_HTML, texto=texto, mensaje=mensaje, logs=logs)

            texto = request.form.get("texto", "")
            
            if accion == "guardar":
                try:
                    path_archivo_temp = os.path.join(CARPETA_ARCHIVOS, "temp_guardar_como.txt")
                    with open(path_archivo_temp, "w", encoding="utf-8") as f:
                        f.write(texto)
                    return send_file(path_archivo_temp, as_attachment=True, download_name="cancionero.txt", mimetype='text/plain')
                except Exception:
                    return f"<h3>Error guardando archivo:</h3><pre>{traceback.format_exc()}</pre>"

            if accion == "generar_pdf":
                try:
                    contenido_canciones = convertir_songpro(texto)
                    indice_tematica = generar_indice_tematica()

                    def reemplazar(match):
                        return match.group(1) + "\n" + contenido_canciones + "\n\n" + indice_tematica + "\n" + match.group(3)

                    nuevo_tex = re.sub(r"(% --- INICIO CANCIONERO ---)(.*?)(% --- FIN CANCIONERO ---)", reemplazar, plantilla, flags=re.S)
                    with open(archivo_salida, "w", encoding="utf-8") as f:
                        f.write(nuevo_tex)

                    logs = compilar_tex_seguro(archivo_salida)

                    pdf_file = os.path.splitext(archivo_salida)[0] + ".pdf"
                    if os.path.exists(pdf_file):
                        return send_file(pdf_file, as_attachment=False)
                    else:
                        return render_template_string(FORM_HTML, texto=texto, logs=logs)

                except Exception:
                    return f"<h3>Error en generar PDF:</h3><pre>{traceback.format_exc()}</pre>"

        return render_template_string(FORM_HTML, texto=texto, mensaje=mensaje, logs=logs)

    except Exception:
        return f"<h3>Error inesperado:</h3><pre>{traceback.format_exc()}</pre>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
