FROM alpine:3.22
RUN apk add --no-cache busybox-extras bind-tools
RUN mkdir -p /www && head -c 8388608 /dev/urandom > /synthetic-layer
RUN echo CONTAINER_OK > /www/container
COPY index.html /www/index.html
CMD ["httpd", "-f", "-p", "8080", "-h", "/www"]
