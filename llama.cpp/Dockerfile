ARG ROCM_VERSION
ARG GFX_TARGET

FROM ghcr.io/sileader/rocm-images/base-ubuntu:26.04-rocm${ROCM_VERSION}-${GFX_TARGET}

ARG ROCM_VERSION
ARG GFX_TARGET
ARG LLAMA_CPP_VERSION

LABEL llama.cpp.version="${LLAMA_CPP_VERSION}"

COPY llama.cpp /opt/llama.cpp

ENTRYPOINT ["/opt/llama.cpp/llama-server"]
