# Usamos una imagen LaTeX completa preconstruida
FROM texlive/texlive:latest

# Actualizamos e instalamos Python y pip
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requerimientos
COPY requirements.txt /app/

# Crear entorno virtual y activar para instalar dependencias
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código fuente y plantilla LaTeX
COPY convert.py plantilla.tex /app/

# Crear carpeta para PDFs con permisos
RUN mkdir -p /app/pdfs && chmod 777 /app/pdfs

EXPOSE 8001

# Ejecutar Gunicorn usando el entorno virtual
CMD ["gunicorn", "--bind", "0.0.0.0:8001", "--workers", "2", "--threads", "4", "--timeout", "180", "convert:app"]


