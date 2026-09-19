# Build stage
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite inlines VITE_* env vars at build time, and the resulting JS runs in the
# user's browser (not inside the Docker network), so this must be an address
# the browser can reach -- the backend's published host port, not the
# in-network service name "backend".
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Serve stage
FROM nginx:1.27-alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# 127.0.0.1, not localhost: this image's nginx.conf only binds 0.0.0.0:80
# (IPv4), but this container's resolver prefers localhost's IPv6 (::1)
# address, which nothing listens on -- wget would get "connection refused"
# and the healthcheck would report unhealthy despite nginx serving requests
# correctly on IPv4.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:80/ || exit 1
