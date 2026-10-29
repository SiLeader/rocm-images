ARG ROCM_VERSION
ARG GFX_TARGET
ARG LLAMA_CPP_VERSION

FROM ghcr.io/sileader/rocm-images/base-ubuntu:26.04-rocm${ROCM_VERSION}-${GFX_TARGET}

LABEL llama.cpp.version="${LLAMA_CPP_VERSION}"

COPY llama /opt/llama.cpp

ENTRYPOINT ["/opt/llama.cpp/llama-server"]
