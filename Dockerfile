FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Instalar LaTeX con paquetes esenciales y texlive-music que incluye songs
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-music \
        latexmk \
        makeindex \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requirements e instalar dependencias de Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código fuente y la plantilla
COPY convert.py plantilla.tex /app/

# Crear directorio para PDFs con permisos de escritura
RUN mkdir -p /app/pdfs && chmod 777 /app/pdfs

EXPOSE 8000

# Ejecutar Gunicorn con configuración ligera para no saturar CPU
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--timeout", "120", "convert:app"]
