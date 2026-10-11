FROM nginx:1.27-alpine

COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf

# 443 serves the apps and the API over TLS 1.3 (certificate mounted from infra/certs); 80 only redirects.
EXPOSE 80 443

HEALTHCHECK --interval=10s --timeout=3s --retries=3     CMD wget -qO- http://127.0.0.1:80/health || exit 1

CMD ["nginx", "-g", "daemon off;"]
