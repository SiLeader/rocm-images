FROM ubuntu:26.04@sha256:6a06111c3b0a8600feadb270aec771dc239bf407b25625f93f44ab00e11f4d3c

ARG ROCM_VERSION
ARG GFX_TARGET

LABEL org.opencontainers.image.url="https://github.com/SiLeader/rocm-images"
LABEL org.opencontainers.image.version="26.04"
LABEL org.opencontainers.image.licenses="Apache-2.0"
LABEL rocm.version="${ROCM_VERSION}"
LABEL gfx.target="${GFX_TARGET}"

COPY ./amdrocm-stable.sources /etc/apt/sources.list.d/

RUN apt-get update && \
    apt-get install -y --no-install-recommends wget gpg ca-certificates && \
    mkdir --parents --mode=0755 /etc/apt/keyrings && \
    wget https://stable.repo.amd.com/rocm/gpg/packages.gpg -O - | gpg --dearmor > /etc/apt/keyrings/amdrocm.gpg && \
    apt-get update && \
    apt-get install -y --no-install-recommends amdrocm${ROCM_VERSION}-${GFX_TARGET} && \
    apt-get purge -y wget gpg ca-certificates && \
    apt-get autopurge -y && \
    rm -rf /var/lib/apt/lists/*

ENV LD_LIBRARY_PATH=/opt/rocm/lib
