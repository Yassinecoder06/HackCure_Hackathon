FROM nginx:alpine

COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD wget -qO- http://127.0.0.1:80/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
