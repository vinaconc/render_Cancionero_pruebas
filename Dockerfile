FROM python:3.11-slim

# Evita los prompts interactivos de APT durante la instalación.
ENV DEBIAN_FRONTEND=noninteractive

# Instala todas las dependencias de LaTeX necesarias
# 'texlive-full' es la forma más fácil y robusta de garantizar que todos tus paquetes (songs, imakeidx, etc.) estén disponibles.
# 'latexmk' es crucial para compilar el documento en múltiples pasadas.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        texlive-full \
        latexmk \
    && rm -rf /var/lib/apt/lists/*

# Crea un directorio para tu aplicación.
WORKDIR /app

# Copiar dependencias de Python e instalarlas
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código y la plantilla
COPY convert.py plantilla.tex /app/

# Exponer el puerto (Render usará $PORT)
EXPOSE 8000

# Comando por defecto: usar gunicorn enlazado a $PORT
# convert:app es el módulo:objeto WSGI
CMD ["bash", "-c", "latexmk -pdf -interaction=nonstopmode plantilla.tex && gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 180 convert:app"]




