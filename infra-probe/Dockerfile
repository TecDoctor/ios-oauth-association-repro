FROM busybox:1.37
RUN mkdir -p /www && head -c 8388608 /dev/urandom > /synthetic-layer
RUN echo CONTAINER_OK > /www/container
COPY index.html /www/index.html
CMD ["httpd", "-f", "-p", "8080", "-h", "/www"]
