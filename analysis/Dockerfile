# analysis/Dockerfile — contenedor de análisis (nada de Python en el host).
# Imagen base documentada: python:3.12-slim (Debian slim + Python 3.12).
ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY analyze.py decision_matrix.py compare_all.py avanzadas.py ./

# results/ y docs/ se montan como volúmenes en docker-compose.yml
VOLUME ["/results", "/docs"]

CMD ["python", "analyze.py"]
