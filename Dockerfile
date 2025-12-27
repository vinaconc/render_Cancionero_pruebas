FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-base \
    texlive-latex-recommended \
    texlive-latex-extra \
    texlive-fonts-recommended \
    texlive-lang-spanish \
    latexmk \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN mktexlsr /app/texmf-local
ENV TEXMFHOME=/app/texmf-local

RUN pip install --no-cache-dir -r requirements.txt

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "180", "convert:app"]


