FROM node:22-alpine AS builder

WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --include=dev --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY nginx/nginx.conf /etc/nginx/nginx.conf
COPY --from=builder /web/dist /usr/share/nginx/html
EXPOSE 80
