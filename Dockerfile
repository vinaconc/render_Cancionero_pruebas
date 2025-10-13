# -- Primera etapa: Construcción de la imagen base de TeX Live personalizada --
# Esta etapa instala TeX Live y los paquetes necesarios.
# Se hace en una etapa separada para que la imagen final sea más pequeña,
# ya que solo copia los archivos de TeX Live compilados y no las herramientas de construcción.
FROM texlive/texlive:basic AS texlive-build

# Instala paquetes adicionales de TeX Live usando tlmgr.
# Se recomienda instalar todos los paquetes en una sola capa 'RUN'
# para optimizar el tamaño de la imagen Docker.
# Aquí se incluye 'songs' y otros paquetes comunes.
# La lista de paquetes puede necesitar ajustes según tus necesidades específicas.
RUN tlmgr update --self && \
    tlmgr install \
        amsmath \
        amsfonts \
        graphicx \
        fancyhdr \
        url \
        hyperref \
        geometry \
        xcolor \
        inputenc \
        babel \
        spanish \
        titlesec \
        enumitem \
        ucs \
        latex-ucs \
        collectbox \
        soul \
        etoolbox \
        caption \
        needspace \
        footmisc \
        varwidth \
        songs \
        # Añade aquí cualquier otro paquete LaTeX que tu plantilla.tex o tus canciones usen
    && \
    # Limpieza: Remueve archivos temporales y caches para reducir el tamaño de la imagen.
    tlmgr path add && \
    tlmgr list --only-installed > /dev/null && \
    rm -rf /usr/local/texlive/texmf-var/web2c/tlmgr.log \
           /usr/local/texlive/texmf-var/tlmgr/tlpkg/texlive.tlpdb.log \
           /tmp/* /var/tmp/* \
           /usr/local/texlive/2023/temp/ \
           /usr/local/texlive/2023/texmf-var/web2c/tlmgr.log # Ajusta el año de TeX Live si es diferente
    # Asegúrate de que pdflatex esté en el PATH
    # ln -s /usr/local/texlive/2023/bin/x86_64-linux/pdflatex /usr/local/bin/pdflatex # Ya debería estar en PATH con `texlive:basic`


# -- Segunda etapa: Construcción de la imagen final de la aplicación Flask --
# Aquí usamos una imagen base de Python más ligera para nuestra aplicación Flask.
FROM python:3.9-slim-buster

# Establece variables de entorno para que Python no escriba archivos .pyc
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Copia los archivos de TeX Live instalados de la etapa 'texlive-build'
# Esto hace que la imagen final sea más pequeña al no incluir todas las herramientas de tlmgr, etc.
# Asegúrate de que esta ruta '/usr/local/texlive' es la correcta para tu versión de texlive/texlive:basic
COPY --from=texlive-build /usr/local/texlive /usr/local/texlive
ENV PATH="/usr/local/texlive/2023/bin/x86_64-linux:${PATH}" # Ajusta el año si es diferente (e.g., 2024)

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de nuestra aplicación Flask
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia el resto de los archivos de la aplicación
COPY . /app

# Expone el puerto que usará Gunicorn (o Flask si lo ejecutas en modo desarrollo)
EXPOSE 5000

# Comando para ejecutar la aplicación usando Gunicorn
# 'convert:app' significa que Gunicorn buscará la variable 'app'
# dentro del módulo Python 'convert.py'.
# Puedes ajustar el número de workers (-w) según tus necesidades de concurrencia.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "convert:app"]

# Si solo quieres ejecutar Flask en modo desarrollo (NO RECOMENDADO PARA PRODUCCIÓN):
# CMD ["python", "convert.py"]
