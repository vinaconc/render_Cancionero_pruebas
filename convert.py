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

# Funciones de ejemplo
def convertir_songpro(texto):
    # Aquí puedes añadir tu lógica de conversión de SongPro a LaTeX si la tienes.
    # Por ahora, solo se devuelve el texto.
    return texto
    
def generar_indice_tematica():
    if not indice_tematica_global:
        return ""
    resultado = [r"\section*{Índice Temático}", r"\begin{itemize}"]
    for palabra in sorted(indice_tematica_global.keys()):
        canciones = sorted(list(indice_tematica_global[palabra]))
        enlaces = [
            rf"\hyperref[cancion-{c.replace(' ', '-')}]" + f"{{{c}}}"
            for c in canciones
        ]
        resultado.append(rf"  \item \textbf{{{palabra.title()}}} --- {', '.join(enlaces)}")
    resultado.append(r"\end{itemize}")
    return '\n'.join(resultado)

def limpiar_titulo_para_label(titulo):
    return titulo.replace(" ", "-")

def compilar_tex_seguro(tex_path):
    """
    Compila un archivo .tex y devuelve el log completo.
    Muestra errores y advertencias sin detener el servidor.
    """
    tex_dir = os.path.dirname(tex_path) or "."
    tex_file = os.path.basename(tex_path)

    try:
        # Ejecutar pdflatex -> makeindex (si aplica) -> pdflatex
        logs = ""

        # Primera pasada
        result = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_file],
            capture_output=True,
            text=True,
            cwd=tex_dir
        )
        logs += "\n--- COMPILACIÓN 1 ---\n" + result.stdout + result.stderr
        if result.returncode != 0:
            raise RuntimeError(f"Error compilando LaTeX en la primera iteración.\nLog completo:\n{logs}")

        # makeindex para índices conocidos (si existen)
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

        # Segunda pasada
        result2 = subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", tex_file],
            capture_output=True,
            text=True,
            cwd=tex_dir
        )
        logs += "\n--- COMPILACIÓN 2 ---\n" + result2.stdout + result2.stderr
        if result2.returncode != 0:
            raise RuntimeError(f"Error compilando LaTeX en la segunda iteración.\nLog completo:\n{logs}")

        # Verificar que se generó PDF
        pdf_file = os.path.splitext(tex_path)[0] + ".pdf"
        if not os.path.exists(pdf_file):
            raise RuntimeError(f"No se generó el PDF. Revisa el log:\n{logs}")

        return logs

    except Exception as e:
        raise RuntimeError(f"Excepción en compilación: {e}\n{logs}")


@app.route("/", methods=["GET", "POST"])
def index():
    # Inicializar las variables al inicio para evitar UnboundLocalError
    texto = ""
    mensaje = ""
    logs = ""
    
    try:
        if request.method == "POST":
            accion = request.form.get("accion")

            # 👉 CARGAR ARCHIVO DESDE LA PC
            if accion == "cargar_archivo":
                uploaded_file = request.files.get("archivo")
                if uploaded_file and uploaded_file.filename:
                    texto = uploaded_file.read().decode("utf-8")
                    mensaje = f"Archivo '{uploaded_file.filename}' cargado para su edición."
                else:
                    mensaje = "Error: No se seleccionó ningún archivo para cargar."
                return render_template_string(FORM_HTML, texto=texto, mensaje=mensaje, logs=logs)

            # 👉 OBTENER TEXTO DEL FORMULARIO
            texto = request.form.get("texto", "")
            
            # 👉 GUARDAR COMO
            if accion == "guardar":
                try:
                    path_archivo_temp = os.path.join(CARPETA_ARCHIVOS, "temp_guardar_como.txt")
                    with open(path_archivo_temp, "w", encoding="utf-8") as f:
                        f.write(texto)
                    
                    return send_file(
                        path_archivo_temp,
                        as_attachment=True,
                        download_name="cancionero.txt",
                        mimetype='text/plain'
                    )
                except Exception:
                    return f"<h3>Error guardando archivo:</h3><pre>{traceback.format_exc()}</pre>"

            # 👉 GENERAR PDF
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
                        return render_template_string(FORM_HTML, texto=texto, logs=logs)

                except Exception:
                    return f"<h3>Error en generar PDF:</h3><pre>{traceback.format_exc()}</pre>"

        # GET inicial y manejo de otras acciones
        return render_template_string(FORM_HTML, texto=texto, mensaje=mensaje, logs=logs)

    except Exception:
        return f"<h3>Error inesperado:</h3><pre>{traceback.format_exc()}</pre>"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
