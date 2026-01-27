FROM python:3.10-slim

ENV APP_HOME=/opt
ENV ADA_ENV=${APP_HOME}/ada_env
ENV ALIRE_HOME=/root/.local/share/alire
WORKDIR ${APP_HOME}
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    unzip \
    libncurses6 \
    libgmp-dev \
    libiconv-hook-dev \
 && rm -rf /var/lib/apt/lists/*
ARG ALIRE_VERSION=2.0.1
RUN curl -L https://github.com/alire-project/alire/releases/download/v${ALIRE_VERSION}/alr-${ALIRE_VERSION}-bin-x86_64-linux.zip \
    -o /tmp/alr.zip \
 && unzip /tmp/alr.zip -d /tmp/alr \
 && mv /tmp/alr/bin/alr /usr/local/bin/alr \
 && chmod +x /usr/local/bin/alr \
 && rm -rf /tmp/alr /tmp/alr.zip
RUN alr --non-interactive toolchain --select gnat_native \
 && alr --non-interactive toolchain --select gprbuild
WORKDIR /opt
RUN alr --non-interactive init --bin ada_env
WORKDIR ${ADA_ENV}
ENV LIBRARY_TYPE=relocatable
ENV LAL_LIBRARY_TYPE=relocatable
RUN alr with libadalang \
 && alr build
WORKDIR ${APP_HOME}
COPY requirements.txt .
RUN pip install --no-cache-dir langkit \
 && pip install --no-cache-dir -r requirements.txt
COPY . .
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python3", "-c", "import libadalang; print('Libadalang is ready!')"]