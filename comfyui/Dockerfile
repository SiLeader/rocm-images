ARG ROCM_VERSION
ARG GFX_TARGET

FROM ghcr.io/sileader/rocm-images/base-ubuntu:26.04-rocm${ROCM_VERSION}-${GFX_TARGET}

ARG PYTORCH_ROCM_VERSION
ARG TORCHVISION_VERSION
ARG GFX_TARGET
ARG COMFY_VERSION

LABEL comfyui.version="${COMFY_VERSION}"

WORKDIR /opt/comfyui

RUN apt-get update && \
    apt-get install -y python3 python3-pip python3-venv git && \
    python3 -m venv /opt/comfyui/venv && \
    git clone -b "${COMFY_VERSION}" --depth 1  https://github.com/Comfy-Org/ComfyUI.git ComfyUI && \
    cd ComfyUI && \
    /opt/comfyui/venv/bin/python -m pip install --index-url https://stable.repo.amd.com/rocm/whl-next/ \
        "torch[device-${GFX_TARGET}]==2.14.0+rocm${PYTORCH_ROCM_VERSION}" \
        "torchvision[device-${GFX_TARGET}]==${TORCHVISION_VERSION}+rocm${PYTORCH_ROCM_VERSION}" \
        "torchaudio==2.11.0.3+rocm${PYTORCH_ROCM_VERSION}" && \
    /opt/comfyui/venv/bin/python -m pip install -r requirements.txt

WORKDIR /opt/comfyui/ComfyUI

ENTRYPOINT ["/opt/comfyui/venv/bin/python", "main.py"]
CMD ["--listen", "0.0.0.0"]
