# ---- Build stage: compile the React/Vite app into static assets ----
FROM node:20-alpine AS build
WORKDIR /app

# Install deps first so this layer is cached unless the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- Runtime stage: serve the built assets with nginx ----
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
