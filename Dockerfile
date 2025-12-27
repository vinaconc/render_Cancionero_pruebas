FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Paquetes mínimos para cancionero (songs, hyperref, índices, español)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        texlive-latex-base \
        texlive-latex-recommended \
        texlive-latex-extra \
        texlive-fonts-recommended \
        texlive-lang-spanish \
        texlive-music \ 
        latexmk \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY convert.py plantilla.tex /app/

EXPOSE 8000

CMD ["bash", "-c", "latexmk -pdf -interaction=nonstopmode plantilla.tex && gunicorn --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 180 convert:app"]

