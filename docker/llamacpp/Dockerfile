# OpsGPT — llama.cpp inference server
# Built from source and tuned for the target CPU: Intel Xeon E5-2650 v3 (Haswell)
#   SIMD available: AVX, AVX2, FMA, F16C  (NO AVX-512)
# We compile explicitly for those ISA extensions for reproducible, optimized CPU inference.
#
# Multi-stage: a heavy build stage (toolchain + sources) and a slim runtime stage.

# ---------- build stage ----------
FROM ubuntu:24.04 AS build

ARG LLAMA_CPP_REF=master

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        git \
        ccache \
        libcurl4-openssl-dev \
        libgomp1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src
RUN git clone --depth 1 --branch "${LLAMA_CPP_REF}" https://github.com/ggml-org/llama.cpp.git . \
    && git rev-parse HEAD > /llama.cpp.commit

# Explicit ISA flags for Haswell. GGML_NATIVE=OFF keeps the build deterministic
# (does not silently pick up build-host-only extensions like AVX-512 on other CPUs).
RUN cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=OFF \
        -DGGML_AVX=ON \
        -DGGML_AVX2=ON \
        -DGGML_FMA=ON \
        -DGGML_F16C=ON \
        -DGGML_AVX512=OFF \
        -DLLAMA_CURL=ON \
        -DLLAMA_BUILD_TESTS=OFF \
        -DLLAMA_BUILD_EXAMPLES=ON \
        -DLLAMA_BUILD_SERVER=ON \
    && cmake --build build --config Release --target llama-server llama-bench -j "$(nproc)"

# Collect the server binary + the shared libs it links (libllama, libggml*, etc.)
RUN mkdir -p /opt/llama/bin /opt/llama/lib \
    && cp build/bin/llama-server /opt/llama/bin/ \
    && cp build/bin/llama-bench /opt/llama/bin/ \
    && find build -name "*.so" -exec cp {} /opt/llama/lib/ \; \
    && cp /llama.cpp.commit /opt/llama/

# ---------- runtime stage ----------
FROM ubuntu:24.04 AS runtime

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        libcurl4 \
        libgomp1 \
        ca-certificates \
        curl \
        numactl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -r -u 10001 -m -d /home/llama llama

COPY --from=build /opt/llama/bin/ /usr/local/bin/
COPY --from=build /opt/llama/lib/ /usr/local/lib/
COPY --from=build /opt/llama/llama.cpp.commit /etc/llama.cpp.commit
RUN ldconfig

USER llama
EXPOSE 8080

# Healthcheck hits llama.cpp's /health endpoint.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=5 \
    CMD curl -fsS http://localhost:8080/health || exit 1

# Model path, threads, context etc. are supplied by docker-compose as CLI args.
ENTRYPOINT ["llama-server"]
