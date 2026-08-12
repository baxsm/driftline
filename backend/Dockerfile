# The runtime for inertial runs.
#
# gtsam publishes manylinux and macOS wheels only, so visual-inertial fusion cannot run on a
# native Windows checkout however the environment is configured. Everything else in this
# backend runs natively, and this image exists so the one part that cannot still has somewhere
# real to run rather than being left unverified.
#
# Python is pinned to 3.12 because that is what gtsam publishes wheels for. Building it from
# source to match the 3.14 used elsewhere would trade an hour of compile time for nothing.
FROM python:3.12-slim

# opencv needs these at runtime even headless; without libxcb the import itself fails
RUN apt-get update && apt-get install --no-install-recommends -y \
    libgl1 \
    libglib2.0-0 \
    libxcb1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-fusion.txt ./
RUN pip install --no-cache-dir -r requirements-fusion.txt

COPY src ./src
COPY migrations ./migrations
COPY alembic.ini pyproject.toml ./

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
