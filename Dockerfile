FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Paso 1: instalar utilidades básicas para apt
RUN apt-get update && \
    apt-get install -y --no-install-recommends apt-utils ca-certificates gnupg && \
    rm -rf /var/lib/apt/lists/*

# Paso 2: actualizar repositorios otra vez
RUN apt-get update

# Paso 3: instalar paquetes LaTeX y relacionados
RUN apt-get install -y --no-install-recommends \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-lang-spanish \
        texlive-music \
        latexmk \
        makeindex

# Limpiar
RUN rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY convert.py plantilla.tex /app/

RUN mkdir -p /app/pdfs && chmod 777 /app/pdfs

EXPOSE 8000

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--timeout", "120", "convert:app"]
