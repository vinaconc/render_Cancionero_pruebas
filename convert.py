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
	notas_americanas_simples = ['A', 'B', 'C', 'D', 'E', 'F', 'G']

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
					acorde_convertido = convertir_a_latex(acordes[idx_acorde])
					# Escapar sostenidos en acordes para LaTeX
					acorde_escapado = acorde_convertido.replace('#', '\\#')
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


# ... (todo tu código anterior se mantiene igual hasta dentro de convertir_songpro)

def limpiar_titulo_para_label(titulo):
    titulo = re.sub(r'\s*=[+-]?\d+\s*$', '', titulo.strip())
    titulo = unicodedata.normalize('NFD', titulo)
    titulo = ''.join(c for c in titulo if unicodedata.category(c) != 'Mn')
    titulo = re.sub(r'[^a-zA-Z0-9\- ]+', '', titulo)
    return titulo.replace(' ', '-')

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
    raw_mode = False

    def entorno(tb):
        if tb == 'verse': return (r'\beginverse', r'\endverse')
        elif tb == 'chorus': return (r'\beginchorus', r'\endchorus')
        elif tb == 'melody': return (r'\beginverse', r'\endverse')

    def cerrar_bloque():
        nonlocal bloque_actual, tipo_bloque
        if bloque_actual:
            begin, end = entorno(tipo_bloque)
            letra_diagrama = {'verse': 'A', 'chorus': 'B', 'melody': 'C'}.get(tipo_bloque, 'A')
            contenido = ' \\\\'.join(bloque_actual) + ' \\\\'
            contenido = contenido.replace('"', '')
            resultado.append(begin)
            resultado.append('\\diagram{' + letra_diagrama + '}{' + contenido + '}')
            resultado.append(end)
        bloque_actual = []
        tipo_bloque = None

    def cerrar_cancion():
        nonlocal cancion_abierta, referencia_pendiente
        if cancion_abierta:
            resultado.append(r'\endsong')
            if referencia_pendiente:
                resultado.append('\\beginscripture{[' + str(referencia_pendiente) + ']}')
                resultado.append(r'\endscripture')
                referencia_pendiente = None
            cancion_abierta = False

    i = 0
    while i < len(lineas):
        linea = lineas[i].strip()
        app.logger.info(f"DEBUG línea {i}: '{linea}' raw_mode={raw_mode}")
        
        if linea.lower().startswith("ref="):
            contenido = linea[4:].strip()
            if contenido.startswith('(') and contenido.endswith(')'):
                referencia_pendiente = contenido[1:-1]
            i += 1
            continue

        if not linea:
            i += 1
            continue

        # N → MODO RAW
        if linea == 'N':
            app.logger.info(">>> ENTRANDO MODO RAW N <<<")
            cerrar_bloque()
            raw_mode = True
            bloque_actual = []
            i += 1
            continue

        # MODO RAW activo
        if raw_mode:
            app.logger.info(f"RAW modo: '{linea}'")
            if linea in ('V', 'C', 'O', 'S', 'N'):
                app.logger.info(f">>> CERRANDO RAW por {linea}")
                raw_mode = False
                if bloque_actual:
                    contenido_raw = r'\\'.join(bloque_actual) + r'\\'
                    resultado.append(contenido_raw)
                    bloque_actual = []
                continue
            else:
                linea_escapada = escape_latex_raw(linea)
                bloque_actual.append(linea_escapada)
                i += 1
                continue

        # S Sección
        if linea.startswith('S '):
            cerrar_bloque()
            cerrar_cancion()
            if seccion_abierta: resultado.append(r'\end{songs}')
            seccion_abierta = True
            resultado.append(r'\songchapter{' + linea[2:].strip().title() + '}')
            resultado.append(r'\begin{songs}{titleidx}')
            i += 1
            continue

        # O Canción titulada
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

        # Título automático (línea UPPERCASE)
        if linea.isupper() and len(linea) > 1 and linea not in ('V', 'C', 'M', 'O', 'S', 'N'):
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

        # Controles de bloque
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
        if linea == 'C':
            if i + 1 < len(lineas) and es_linea_acordes(lineas[i + 1].strip()):
                cerrar_bloque()
                tipo_bloque = 'chorus'
                i += 1
                continue

        # Acordes + Letra
        if i + 1 < len(lineas) and es_linea_acordes(lineas[i]):
            acordes_originales = lineas[i].strip().split()
            acordes = [transportar_acorde(a, transposicion) for a in acordes_originales]
            letras_raw = lineas[i + 1].strip()
            
            if not ('_' in letras_raw or '#' in letras_raw):
                acordes_escapados = [a.replace('#', '\\#') for a in acordes]
                bloque_actual.append('\\mbox{' + ' '.join([f'[{a}]' for a in acordes_escapados]) + '}')
                bloque_actual.append(letras_raw)
            else:
                linea_convertida = procesar_linea_con_acordes_y_indices(letras_raw, acordes, titulo_cancion_actual)
                bloque_actual.append(linea_convertida)
            
            i += 2
            continue

        # Línea normal de letra
        if tipo_bloque:
            linea_procesada = linea
            if '_' in linea or '#' in linea:
                linea_procesada = procesar_linea_con_acordes_y_indices(linea, [], titulo_cancion_actual)
            bloque_actual.append(linea_procesada)
        
        i += 1

    cerrar_bloque()
    cerrar_cancion()
    if seccion_abierta: resultado.append(r'\end{songs}')
    if raw_mode and bloque_actual:
        resultado.append(r'\\'.join(bloque_actual) + r'\\')
    
    return '\n'.join(resultado) if resultado else "% No se generó contenido válido"



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
@app.route("/", methods=["GET", "POST"])
def index():
    # 1. Recuperar el 'error' y el 'texto' de la sesión y LIMPIAR el error
    error = session.pop('error', None)
    texto = session.get('texto_guardado', "") # Usamos get() para persistir el texto
    
    # Si la solicitud es POST
    if request.method == "POST":
        accion = request.form.get("accion")
        
        # Siempre leer el texto actual del formulario/archivo para la ejecución actual
        texto_actual = request.form.get("texto", "") 
        uploaded_file = request.files.get("archivo")
        if uploaded_file and uploaded_file.filename:
            texto_actual = uploaded_file.read().decode("utf-8")
        
        texto = texto_actual # 'texto' ahora tiene el input actual
        
        # 2. Persistir el texto en la sesión para el caso de éxito y de vuelta del PDF
        session['texto_guardado'] = texto 

        # 👉 ABRIR
        if accion == "abrir":
            try:
                # [Asumiendo que 'archivo_salida' es una variable global o importada]
                with open(archivo_salida, "w", encoding="utf-8") as f:
                    f.write(texto)
            except Exception:
                session['error'] = "Error al guardar el archivo" 
            
            # PRG: Redirigir siempre.
            return redirect(url_for('index'))

        # 👉 GENERAR PDF
        elif accion == "generar_pdf": # <<-- Usar 'elif' para aislar el bloque
            try:
                # [Asumiendo que estas funciones y variables están definidas globalmente]
                indice_tematica_global.clear()
                contenido_canciones = convertir_songpro(texto)
                indice_tematica = generar_indice_tematica()

                def reemplazar(match):
                    return match.group(1) + "\n" + contenido_canciones + "\n\n" + indice_tematica + "\n" + match.group(3)

                nuevo_tex = re.sub(
                    r"(% --- INICIO CANCIONERO ---)(.*?)(% --- FIN CANCIONERO ---)",
                    reemplazar,
                    plantilla, # [Asumiendo que 'plantilla' está definida globalmente]
                    flags=re.S
                )

                with open(archivo_salida, "w", encoding="utf-8") as f:
                    f.write(nuevo_tex)

                # Intenta compilar. Si falla, genera una excepción.
                compilar_tex_seguro(archivo_salida) 
                
                pdf_file = os.path.splitext(archivo_salida)[0] + ".pdf"

                if os.path.exists(pdf_file):
                    session.pop('texto_guardado', None)
                    session.pop('error', None)
                    # Éxito: Enviar el PDF directamente.
                    return send_file(pdf_file, as_attachment=False)
                else:
                    # Si la compilación no lanzó error pero el archivo no existe
                    session['error'] = "Error de sintaxis en el texto ingresado (archivo PDF no generado)."
            
            except Exception as e:
                # Captura errores de sintaxis o de compilación.
                app.logger.error(f"Error en procesamiento/compilación: {str(e)}")
                session['error'] = "Error de sintaxis en el texto ingresado."
            
            # Si hubo error (o no se envió el PDF), redirigir para mostrar el alert.
            session.pop('texto_guardado', None)
            return redirect(url_for('index'))
        
        # Si la acción NO es 'abrir' ni 'generar_pdf' (p. ej., un POST sin acción o descargar)
        # Aquí puedes manejar la descarga si el JavaScript la permite, o simplemente continuar.
        # Si la acción es la descarga, se maneja en @app.route("/descargar")

    # GET inicial o POST con error redirigido.
    return render_template_string(FORM_HTML, texto=texto, error=error)

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
    <div style="color: red; font-weight: bold; margin-bottom: 1em;">
        {{ error.replace('\\n', '<br>')|safe }}
    </div>
{% endif %}
<form id="formulario" method="post" enctype="multipart/form-data">
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
const form = document.getElementById("formulario");

// Función para validar acordes
function validarAcordes(texto) {
    const lineas = texto.split('\n');
    const errores = [];
    
    for (let i = 0; i < lineas.length; i++) {
        const linea = lineas[i].trim();
        
        if (!linea || linea.startsWith('S ') || linea.startsWith('O ') || 
            ['V', 'C', 'M', 'N'].includes(linea) || linea.startsWith('ref=') ||
            linea.match(/^[A-Z\s]+$/) || linea.includes('_')) {
            continue;
        }
        
        const tokens = linea.split(/\s+/);
        let tieneAcordesValidos = false;
        let tieneTokensInvalidos = false;
        const tokensInvalidos = [];
        
        for (const token of tokens) {
            const acordeAmericano = /^[A-G][#b]?(m|maj|min|dim|aug|sus|add)?\d*(\/[A-G][#b]?)?$/i;
            const notasLatinas = ['do', 're', 'mi', 'fa', 'sol', 'la', 'si', 'reb', 'mib', 'lab', 'sib', 'do#', 're#', 'fa#', 'sol#', 'la#'];
            const acordeLatino = notasLatinas.some(nota => token.toLowerCase().startsWith(nota.toLowerCase()));
            
            if (acordeAmericano.test(token) || acordeLatino) {
                tieneAcordesValidos = true;
            } else {
                tieneTokensInvalidos = true;
                tokensInvalidos.push(token);
            }
        }
        
        if (tieneAcordesValidos && tieneTokensInvalidos) {
            errores.push(`Línea ${i + 1}: Acordes inválidos: ${tokensInvalidos.join(', ')}. Use acordes válidos como: C, D, E, F, G, A, B, Do, Re, Mi, Fa, Sol, La, Si, etc.`);
        }
    }
    
    return errores;
}
const form = document.getElementById("formulario");

form.addEventListener("submit", async function (e) {
    
    const submitter = e.submitter; 
    const accion = submitter ? submitter.value : '';

    // Si la acción es 'abrir', 'descargar', o cualquier otra, dejamos el envío nativo.
    if (accion !== "generar_pdf") {
        return; 
    }

    // A partir de aquí, solo se ejecuta si accion === "generar_pdf"
    
    e.preventDefault(); // Detenemos el envío solo para generar_pdf para usar fetch

    const texto = document.getElementById("texto").value;
    const errores = validarAcordes(texto);
    
    if (errores.length > 0) {
        alert("Error de sintaxis detectado:\n\n" + errores.join("\n") + "\n\nPor favor, corrige los errores y vuelve a intentar.");
        return;
    }
    
    const formData = new FormData(form);

    try {
        const resp = await fetch("/", {
            method: "POST",
            body: formData,
            redirect: 'manual' // Clave para manejar el PRG
        });

        // 1. Manejo de Redirecciones (PRG): Para errores (status 302 o similar)
        if (resp.status === 302 || (resp.status >= 300 && resp.status < 400 && resp.headers.get('Location'))) {
            // Sigue la redirección a la ruta GET, que contiene el alert de error.
            window.location.href = resp.headers.get('Location') || "/";
            return;
        }

        // 2. Manejo de PDF (Acción exitosa)
        const contentType = resp.headers.get("content-type");
        if (contentType && contentType.includes("application/pdf")) {
            const blob = await resp.blob();
            const url = window.URL.createObjectURL(blob);
            window.open(url, "_blank");
            return;
        } 
        
        // 3. Manejo de Errores Inesperados
        if (contentType && contentType.includes("application/json")) {
            const data = await resp.json();
            alert(data.error || "Error de servidor inesperado (JSON).");
        } else {
             // Si no es PDF ni redirección ni JSON, forzamos la recarga para ver el error HTML
             alert("Respuesta inesperada del servidor. Recargando...");
             window.location.href = "/";
        }
        
    } catch (err) {
        alert("Error de conexión con el servidor o fallo de red: " + err.message);
    }
});
</script>
"""

@app.route("/descargar", methods=["POST"])
def descargar():
    texto = request.form.get("texto", "")
    nombre_archivo = request.form.get("nombre_archivo", "cancionero.txt")
    return Response(
        texto,
        mimetype="text/plain",
        headers={"Content-Disposition": f"attachment;filename={nombre_archivo}"}
    )

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

































