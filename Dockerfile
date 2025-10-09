# Usamos una imagen LaTeX completa preconstruida
FROM texlive/texlive:latest

# Actualizamos e instalamos Python y pip
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copiar requerimientos y instalar dependencias Python
COPY requirements.txt /app/
RUN pip3 install --no-cache-dir -r requirements.txt

# Copiar código fuente y plantilla LaTeX
COPY convert.py plantilla.tex /app/

# Crear carpeta para PDFs con permisos
RUN mkdir -p /app/pdfs && chmod 777 /app/pdfs

EXPOSE 8000

# Ejecutar Gunicorn con configuración conservadora
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "2", "--timeout", "120", "convert:app"]
