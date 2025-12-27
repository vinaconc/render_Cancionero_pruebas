from flask import session, Flask, request, after_this_request, jsonify, send_file, render_template_string, Response, redirect, url_for
from flask_cors import CORS
from werkzeug.exceptions import NotFound
import traceback
import os
import subprocess
import re
import unicodedata
import uuid
import time
import io
import tempfile


app = Flask(__name__)
CORS(app, resources={
    r"/get/pdf/": {"origins": ["https://vinaconc.cl"]}
})
app.secret_key = 'Quique04#'
app.config['ENV'] = 'production'
app.config['DEBUG'] = False
app.config['TESTING'] = False
app.config['PROPAGATE_EXCEPTIONS'] = False
@app.errorhandler(NotFound)
def not_found(e):
    app.logger.error(f"404 en URL: {request.path}")
    return "Página no encontrada", 404
@app.errorhandler(Exception)
def handle_exception(e):
    # Registrar el error para depuración pero no mostrarlo al usuario
    app.logger.error(f"Error no manejado: {str(e)}")
    app.logger.error(traceback.format_exc())
    # Devolver un mensaje de error genérico
    return jsonify({"error": "Error inesperado en el servidor."}), 500

archivo_plantilla = "plantilla.tex"

archivo_salida = "cancionero_web.tex"
directorio_pdfs = "pdfs"
os.makedirs(directorio_pdfs, exist_ok=True)

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
		bajo_transpuesto = transportar_acorde(bajo, semitonos)
		return f"{parte_superior_transpuesta}/{bajo_transpuesto}"

	# Mapa de conversión de bemoles a sostenidos para procesamiento interno
	mapa_bemoles_a_sostenidos = {
		'Reb': 'Do#', 'Rebm': 'Do#m',
		'Mib': 'Re#', 'Mibm': 'Re#m',
		'Lab': 'Sol#', 'Labm': 'Sol#m',
		'Sib': 'La#', 'Sibm': 'La#m'
		# Nota: Solb no se convierte a Fa# para mantener consistencia con el mapa de bemoles
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
	acorde = acorde.replace('F#', 'FA#').replace('f#', 'fa#')
	acorde = acorde.replace('C#', 'DO#').replace('c#', 'do#')

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
        base = palabra

        if es_indexada:
            if '=' in palabra:
                try:
                    partes = palabra[1:].split('=', 1)
                    if len(partes) == 2:
                        base = partes[0]
                        index_real = partes[1]
                    else:
                        base = palabra[1:]
                except:
                    base = palabra[1:]
            else:
                base = palabra[1:]

        if base == '_':
            if idx_acorde < len(acordes):
                acorde_escapado = acordes[idx_acorde].replace('#', '\\#')
                resultado += f"\\raisebox{{1.7ex}}{{\\[{acorde_escapado}]}} "
                idx_acorde += 1
            else:
                resultado += '_ '
            continue

        if '_' in base:
            partes_base = base.split('_')
            latex = ''
            for i, parte in enumerate(partes_base):
                if i > 0 and idx_acorde < len(acordes):
                    acorde_convertido = convertir_a_latex(acordes[idx_acorde])
                    acorde_escapado = acorde_convertido.replace('#', '\\#')
                    latex += f"\\[{acorde_escapado}]"
                    idx_acorde += 1
                latex += parte

            palabra_para_indice = limpiar_para_indice(index_real if index_real else ''.join(partes_base))

            if es_indexada:
                if palabra_para_indice not in indice_tematica_global:
                    indice_tematica_global[palabra_para_indice] = set()
                titulo_indexado = re.sub(r'\s*=[+-]?\d+\s*$', '', (titulo_cancion or "Sin título").strip())
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

def escape_latex_raw(linea):
    """
    Escapa caracteres especiales de LaTeX
    SOLO para la sección N (RAW)
    """
    replacements = {
        '#': r'\#',
        '%': r'\%',
        '&': r'\&',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
    }
    for k, v in replacements.items():
        linea = linea.replace(k, v)
    return linea

def limpiar_titulo_para_label(titulo):
    titulo = re.sub(r'\s*=[+-]?\d+\s*$', '', titulo.strip())
    titulo = unicodedata.normalize('NFD', titulo)
    titulo = ''.join(c for c in titulo if unicodedata.category(c) != 'Mn')
    titulo = re.sub(r'[^a-zA-Z0-9\- ]+', '', titulo)
    return titulo.replace(' ', '-')

def convertir_songpro(texto):
    referencia_pendiente = None
    lineas = [l.rstrip() for l in texto.split('\n')]

    resultado = []
    bloque_actual = []

    tipo_bloque = None
    seccion_abierta = False
    cancion_abierta = False
    titulo_cancion_actual = ""
    raw_mode = False

    # =========================
    # CIERRES
    # =========================
    def cerrar_raw():
        nonlocal bloque_actual
        if bloque_actual:
            resultado.append(r'\\'.join(bloque_actual) + r'\\')
            resultado.append('')
            bloque_actual = []

    def cerrar_bloque():
        nonlocal bloque_actual, tipo_bloque
        if not bloque_actual or not tipo_bloque:
            bloque_actual = []
            tipo_bloque = None
            return

        env = {
            'verse': ('\\beginverse', '\\endverse'),
            'chorus': ('\\beginchorus', '\\endchorus'),
            'melody': ('\\beginverse', '\\endverse')
        }.get(tipo_bloque)

        if not env:
            bloque_actual = []
            tipo_bloque = None
            return

        begin, end = env
        contenido = ' \\\\'.join(bloque_actual) + ' \\\\'

        resultado.extend([
            begin,
            '\\diagram{A}{' + contenido + '}',
            end
        ])

        bloque_actual = []
        tipo_bloque = None

    def cerrar_cancion():
        nonlocal cancion_abierta
        if cancion_abierta:
            resultado.append(r'\endsong')
            cancion_abierta = False

    # =========================
    # PARSER
    # =========================
    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()

        # =========================
        # MODO RAW
        # =========================
        if raw_mode:

            # N → cerrar RAW y abrir otro
            if linea == 'N':
                cerrar_raw()
                raw_mode = True   # ← CLAVE: N siempre deja RAW activo
                i += 1
                continue

            # Control → cerrar RAW y reprocesar
            if linea in ('V', 'C', 'M', 'O', 'S'):
                cerrar_raw()
                raw_mode = False
                continue   # ⚠️ NO avanzar i

            # Texto RAW normal
            bloque_actual.append(escape_latex_raw(linea))
            i += 1
            continue

        # =========================
        # N → abrir RAW
        # =========================
        if linea == 'N':
            cerrar_bloque()
            raw_mode = True
            i += 1
            continue

        # =========================
        # Sección
        # =========================
        if linea.startswith('S '):
            cerrar_bloque()
            cerrar_cancion()
            if seccion_abierta:
                resultado.append(r'\end{songs}')
            seccion_abierta = True
            resultado.extend([
                r'\songchapter{' + linea[2:].strip().title() + '}',
                r'\begin{songs}{titleidx}'
            ])
            i += 1
            continue

        # =========================
        # Canción
        # =========================
        if linea.startswith('O '):
            cerrar_bloque()
            cerrar_cancion()
            titulo_cancion_actual = linea[2:].strip().title()
            resultado.append(r'\beginsong{' + titulo_cancion_actual + '}')
            cancion_abierta = True
            i += 1
            continue

        # =========================
        # Bloques
        # =========================
        if linea == 'V':
            cerrar_bloque()
            tipo_bloque = 'verse'
            i += 1
            continue

        if linea == 'C':
            cerrar_bloque()
            tipo_bloque = 'chorus'
            i += 1
            continue

        # =========================
        # Texto normal
        # =========================
        if tipo_bloque:
            bloque_actual.append(linea)

        i += 1

    # =========================
    # CIERRES FINALES
    # =========================
    if raw_mode:
        cerrar_raw()
    cerrar_bloque()
    cerrar_cancion()
    if seccion_abierta:
        resultado.append(r'\end{songs}')

    return '\n'.join(resultado)


def normalizar(palabra):
	# Normaliza palabra para ordenar (quita tildes y pasa a minúscula)
	return ''.join(
		c for c in unicodedata.normalize('NFD', palabra.lower())
		if unicodedata.category(c) != 'Mn'
	)

def convertir_a_latina(acorde):
	"""Convierte un acorde de notación americana a latina, incluyendo acordes con bajo."""
	if '/' in acorde:
		parte_superior, bajo = acorde.split('/')
		parte_superior = equivalencias_latinas.get(parte_superior, parte_superior)
		bajo = equivalencias_latinas.get(bajo, bajo)
		return f"{parte_superior}/{bajo}"
	return equivalencias_latinas.get(acorde, acorde)

def limpiar_titulo_para_label(titulo):
	# Elimina transposición al final como ' =-2' o '=+1'
	titulo = re.sub(r'\s*=[+-]?\d+\s*$', '', titulo.strip())
	# Normaliza: quita tildes y caracteres no válidos para etiquetas
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


texto_ejemplo = """
 """

def compilar_tex_seguro(tex_path):
    """
    Compila un archivo .tex y devuelve True si tuvo éxito.
    En caso de error, lanza RuntimeError genérico sin mostrar el log.
    El log completo se guarda en 'plantilla.log' para depuración.
    """
    tex_dir = os.path.dirname(tex_path) or "."
    tex_file = os.path.basename(tex_path)
    base_name = os.path.splitext(tex_file)[0]
    logs = ""
    AUX_FILES = ['.aux', '.log', '.out', '.toc', '.lof', '.lot', '.tema.ind', '.tema.idx', '.cbtitle', '.cbtitle.ind', '.fls', '.synctex.gz']
    def cleanup_aux_files():
        """Elimina todos los archivos auxiliares generados por LaTeX y makeindex."""
        for ext in AUX_FILES:
            aux_file = os.path.join(tex_dir, base_name + ext)
            if os.path.exists(aux_file):
                try:
                    os.remove(aux_file)
                except Exception as e:
                    app.logger.warning(f"No se pudo borrar el archivo auxiliar {aux_file}: {e}")
    try:
        # Primera pasada
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_file],
            capture_output=True, text=True, cwd=tex_dir
        )
        logs += "\n--- COMPILACIÓN 1 ---\n" + result.stdout + result.stderr
        if result.returncode != 0:
            raise RuntimeError("Error compilando LaTeX en la primera pasada.")

        # makeindex (si aplica)
        base = os.path.splitext(tex_file)[0]
        for entrada, salida in [
            (f"{base}.idx", None),
            (f"{base}.tema.idx", f"{base}.tema.ind"),
            (f"{base}.cbtitle", f"{base}.cbtitle.ind"),
        ]:
            if os.path.exists(os.path.join(tex_dir, entrada)):
                cmd = ["makeindex", entrada] if salida is None else ["makeindex", "-o", salida, entrada]
                mi = subprocess.run(cmd, capture_output=True, text=True, cwd=tex_dir)
                logs += "\n--- MAKEINDEX ---\n" + mi.stdout + mi.stderr

        # Segunda pasada
        result2 = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_file],
            capture_output=True, text=True, cwd=tex_dir
        )
        logs += "\n--- COMPILACIÓN 2 ---\n" + result2.stdout + result2.stderr
        if result2.returncode != 0:
            raise RuntimeError("Error compilando LaTeX en la segunda pasada.")

        # Verificar PDF
        pdf_file = os.path.splitext(tex_path)[0] + ".pdf"
        if not os.path.exists(pdf_file):
            raise RuntimeError("No se generó el PDF.")

        return True

    except Exception as e:
        log_path = os.path.join(tex_dir, f"{base_name}.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(logs)
        with open(log_path, "r", encoding="utf-8") as f:
            error_log = f.read()
        raise RuntimeError(f"Error de sintaxis en el texto ingresado\nDetalles del log:\n{error_log}")
    finally:
        # **LIMPIEZA CRÍTICA:** Se ejecuta siempre, haya éxito o error.
        cleanup_aux_files()

@app.route("/api/generar_pdf", methods=["POST"])
def api_generar_pdf():
    try:
        texto = request.data.decode("utf-8")  # Recibe el cuerpo de la petición como texto plano

        # Aquí llamas a la función que procesa 'texto' y genera el PDF
        # Ejemplo:
        compilar_tex_seguro(texto)  # Función que crea .tex y compila .pdf

        pdf_file = "archivo_generado.pdf"  # Ruta al PDF generado

        if os.path.exists(pdf_file):
            return send_file(pdf_file, as_attachment=False, mimetype="application/pdf")
        else:
            return "No se generó el PDF", 500

    except Exception as e:
        app.logger.error(f"Error en api_generar_pdf: {str(e)}")
        return f"Error procesando texto: {str(e)}", 500
# 🔹 HTML con menú y botón PDF
FORM_HTML = """
<h2>Creador Cancionero</h2>
{% if error %}
<div style="color:red;font-weight:bold;margin-bottom:1em;">
    {{ error.replace('\\n','<br>')|safe }}
</div>
{% endif %}
<form id="formulario" method="post" enctype="multipart/form-data">
    <textarea id="texto" name="texto" rows="20" cols="80">{{ texto }}</textarea><br>
    <button type="submit">Enviar</button>
</form>
"""

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    texto = session.get('texto_guardado', "")

    if request.method == "POST":
        try:
            app.logger.info("📥 LLEGÓ POST /")
            texto = request.form.get("texto", "")
            app.logger.info(f"Texto recibido: {repr(texto)}")

            # Guardar texto en sesión por si hay error
            session['texto_guardado'] = texto

            # Procesar canciones
            indice_tematica_global.clear()
            contenido_canciones = convertir_songpro(texto)
            indice_tematica = generar_indice_tematica()

            def reemplazar(match):
                return (
                    match.group(1)
                    + "\n" + contenido_canciones
                    + "\n\n" + indice_tematica
                    + "\n" + match.group(3)
                )

            nuevo_tex = re.sub(
                r"(% --- INICIO CANCIONERO ---)(.*?)(% --- FIN CANCIONERO ---)",
                reemplazar,
                plantilla,
                flags=re.S
            )

            with open(archivo_salida, "w", encoding="utf-8") as f:
                f.write(nuevo_tex)

            # Compilar y devolver PDF
            compilar_tex_seguro(archivo_salida)
            pdf_file = os.path.splitext(archivo_salida)[0] + ".pdf"
            return send_file(pdf_file, as_attachment=False)

        except Exception as e:
            app.logger.error(f"Error generando PDF en '/': {e}")
            error = "Error generando PDF. Revisa el log de sintaxis en LaTeX."

    # GET inicial o si hubo error en POST
    return render_template_string(FORM_HTML, texto=texto, error=error)

@app.route("/get/pdf/", methods=["POST"])
def get_pdf():
    try:
        texto = request.data.decode("utf-8")
        contenido_canciones = convertir_songpro(texto)
        indice_tematica = generar_indice_tematica()

        def reemplazar(match):
            """Función para reemplazar el marcador en la plantilla LaTeX."""
            return match.group(1) + "\n" + contenido_canciones + "\n\n" + indice_tematica + "\n" + match.group(3)

        nuevo_tex = re.sub(
            r"(% --- INICIO CANCIONERO ---)(.*?)(% --- FIN CANCIONERO ---)",
            reemplazar,
            plantilla,
            flags=re.S
        )

        # 1. Generar un UUID para un nombre de archivo único
        unique_id = str(uuid.uuid4())
        base_filename = f"cancionero_{unique_id}"

        with tempfile.TemporaryDirectory(dir=directorio_pdfs) as temp_dir:
            
            # 2. Usar el UUID para construir los nombres de los archivos
            archivo_salida_unico = os.path.join(temp_dir, f"{base_filename}.tex")
            pdf_file = os.path.join(temp_dir, f"{base_filename}.pdf")

            app.logger.info(f"Generando archivo único interno: {archivo_salida_unico}")

            with open(archivo_salida_unico, "w", encoding="utf-8") as f:
                f.write(nuevo_tex)

            # Compilar el archivo .tex
            compilar_tex_seguro(archivo_salida_unico)

            if os.path.exists(pdf_file):

                with open(pdf_file, "rb") as f:
                    pdf_data = f.read()

                # El borrado se maneja automáticamente por tempfile.TemporaryDirectory
                # al salir del bloque 'with'.

                # IMPORTANTE: resetear el puntero antes de enviar
                buffer = io.BytesIO(pdf_data)
                buffer.seek(0)

                # Se mantiene el nombre de descarga simple para el usuario final
                return send_file(
                    buffer,
                    as_attachment=False,
                    mimetype="application/pdf",
                    download_name="cancionero.pdf"
                )

            else:
                return jsonify({"error": "No se generó el PDF"}), 500

    except RuntimeError as e:
        # Captura errores específicos de compilación lanzados por compilar_tex_seguro
        app.logger.error(f"Error de compilación capturado: {e}")
        return jsonify({"error": str(e)}), 500
	
    except Exception as e:
        app.logger.error(f"Error no manejado en /get/pdf: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)







































