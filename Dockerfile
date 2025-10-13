FROM blang/latex:ubuntu
# Instalar paquetes LaTeX necesarios para el documento
RUN tlmgr install \
    collection-latexrecommended \
    babel-spanish \
    latexmk \
    collection-xetex \
    ulem \
    pdfpages \
    xcolor \
    makeidx

# Actualizamos e instalamos Python y pip
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

COPY convert.py plantilla.tex /app/

RUN mkdir -p /app/pdfs && chmod 777 /app/pdfs

EXPOSE 8001

CMD ["gunicorn", "--bind", "0.0.0.0:8001", "--workers", "2", "--threads", "4", "--timeout", "180", "convert:app"]

