# syntax=docker/dockerfile:1
#
# FFMPEG API - Python/FastAPI REST API for FFmpeg on Red Hat UBI.
#
# Updating:
#   * New UBI release:  change UBI_IMAGE / UBI_MINIMAL_IMAGE (and PYTHON_VERSION if needed).
#   * New FFmpeg:       rebuild. FFMPEG_VERSION=latest resolves the newest release from
#                       ffmpeg.org at build time. Pin it with --build-arg FFMPEG_VERSION=9.0.2.
#
# Everything is downloaded at build time. The running container makes no external calls.
#
# Why build FFmpeg from source: UBI does not ship FFmpeg, and the RPM Fusion/EPEL packages
# for EL10 are older than upstream and do not install on UBI (they need libSDL2).

ARG UBI_IMAGE=registry.access.redhat.com/ubi10/ubi
ARG UBI_MINIMAL_IMAGE=registry.access.redhat.com/ubi10/ubi-minimal

###############################################################################
# Stage 1: build FFmpeg (static codec libraries, only ffmpeg and ffprobe are kept)
###############################################################################
FROM ${UBI_IMAGE} AS ffmpeg-build

ARG FFMPEG_VERSION=latest
ARG NASM_VERSION=3.02
ARG LAME_VERSION=3.100
ARG BUILD_JOBS=4

RUN dnf -y install gcc gcc-c++ make pkgconf-pkg-config tar xz bzip2 diffutils perl \
        zlib-ng-compat-devel \
    && dnf clean all

ENV PREFIX=/opt/build
ENV PATH=${PREFIX}/bin:${PATH}
ENV PKG_CONFIG_PATH=${PREFIX}/lib/pkgconfig
WORKDIR /src

# nasm: assembler for x264 and FFmpeg (not in UBI repos)
RUN curl -fsSL --retry 5 --retry-all-errors https://www.nasm.us/pub/nasm/releasebuilds/${NASM_VERSION}/nasm-${NASM_VERSION}.tar.xz \
        | tar xJ \
    && cd nasm-${NASM_VERSION} \
    && ./configure --prefix=${PREFIX} \
    && make -j${BUILD_JOBS} && make install

# x264: H.264 encoder (stable branch)
RUN curl -fsSL --retry 5 --retry-all-errors https://code.videolan.org/videolan/x264/-/archive/stable/x264-stable.tar.bz2 \
        | tar xj \
    && cd x264-stable \
    && ./configure --prefix=${PREFIX} --enable-static --enable-pic --disable-cli \
    && make -j${BUILD_JOBS} && make install

# LAME: MP3 encoder
RUN curl -fsSL --retry 5 --retry-all-errors https://downloads.sourceforge.net/project/lame/lame/${LAME_VERSION}/lame-${LAME_VERSION}.tar.gz \
        | tar xz \
    && cd lame-${LAME_VERSION} \
    && ./configure --prefix=${PREFIX} --disable-shared --enable-static --with-pic --disable-frontend \
    && make -j${BUILD_JOBS} && make install

# FFmpeg
RUN set -eux; \
    version="${FFMPEG_VERSION}"; \
    if [ "$version" = "latest" ]; then \
        version=$(curl -fsSL --retry 5 --retry-all-errors https://ffmpeg.org/releases/ \
            | grep -oE 'ffmpeg-[0-9]+\.[0-9]+(\.[0-9]+)?\.tar\.xz' \
            | sed -E 's/ffmpeg-(.*)\.tar\.xz/\1/' | sort -uV | tail -1); \
    fi; \
    echo "Building FFmpeg ${version}"; \
    curl -fsSL --retry 5 --retry-all-errors -o ffmpeg.tar.xz \
        "https://ffmpeg.org/releases/ffmpeg-${version}.tar.xz"; \
    tar xJf ffmpeg.tar.xz; \
    cd "ffmpeg-${version}"; \
    ./configure \
        --prefix=/opt/ffmpeg \
        --pkg-config-flags=--static \
        --extra-cflags="-I${PREFIX}/include" \
        --extra-ldflags="-L${PREFIX}/lib" \
        --enable-gpl --enable-libx264 --enable-libmp3lame \
        --disable-ffplay --disable-doc --disable-debug \
        --disable-bzlib --disable-lzma --disable-xlib --disable-sdl2 --disable-libxcb; \
    make -j${BUILD_JOBS}; \
    make install; \
    # only system libraries may remain as dynamic dependencies
    ldd /opt/ffmpeg/bin/ffmpeg; \
    /opt/ffmpeg/bin/ffmpeg -hide_banner -encoders 2>/dev/null | grep -E 'libx264|libmp3lame| aac |pcm_s16le|mjpeg|png'

###############################################################################
# Stage 2: Swagger UI assets, served from the container so /docs works offline
###############################################################################
FROM ${UBI_IMAGE} AS swagger-assets

ARG SWAGGER_UI_VERSION=5.34.0

RUN mkdir /swagger && cd /swagger \
    && curl -fsSL --retry 5 --retry-all-errors https://registry.npmjs.org/swagger-ui-dist/-/swagger-ui-dist-${SWAGGER_UI_VERSION}.tgz \
        | tar xz --strip-components=1 package/swagger-ui-bundle.js package/swagger-ui.css \
            package/favicon-32x32.png

###############################################################################
# Stage 3: base runtime = UBI minimal + Python + FFmpeg + application
###############################################################################
FROM ${UBI_MINIMAL_IMAGE} AS base

ARG PYTHON_VERSION=3.14

RUN microdnf -y install --setopt=install_weak_deps=0 --setopt=tsflags=nodocs \
        python${PYTHON_VERSION} python${PYTHON_VERSION}-pip \
    && microdnf clean all

COPY --from=ffmpeg-build /opt/ffmpeg/bin/ffmpeg /opt/ffmpeg/bin/ffprobe /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

COPY requirements.txt /app/requirements.txt
RUN python${PYTHON_VERSION} -m venv /opt/venv \
    && pip install -r /app/requirements.txt

WORKDIR /app
COPY app /app/app
COPY --from=swagger-assets /swagger /app/app/static/swagger

###############################################################################
# Stage 4: test image (docker build --target test .)
###############################################################################
FROM base AS test

COPY requirements-dev.txt pyproject.toml /app/
COPY tests /app/tests
RUN pip install -r /app/requirements-dev.txt
CMD ["pytest", "-v"]

###############################################################################
# Stage 5: final image
###############################################################################
FROM base AS runtime

# Non-root numeric user (no passwd entry needed). Group 0 permissions on /app keep it
# working with the arbitrary UID that OpenShift assigns.
RUN chmod -R g=u /app
USER 1001

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:3000/health', timeout=3).status == 200 else 1)"

CMD ["python", "-m", "app"]
