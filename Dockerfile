FROM python:3.11-slim

# Evita los prompts interactivos de APT durante la instalación.
ENV DEBIAN_FRONTEND=noninteractive

# Instala una versión mínima de LaTeX con los paquetes más frecuentes
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        latexmk \
    && rm -rf /var/lib/apt/lists/*

# Crea un directorio para tu aplicación.
WORKDIR /app

# Copia dependencias e instálalas
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copia el código y la plantilla
COPY convert.py plantilla.tex /app/

# Exponer el puerto que usará Gunicorn
EXPOSE 8000

# Comando por defecto: Gunicorn con menos workers/threads
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--timeout", "120", "convert:app"]
