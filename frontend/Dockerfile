FROM node:20-alpine AS build
WORKDIR /app
ARG VITE_OPS_TOKEN=
ENV VITE_OPS_TOKEN=$VITE_OPS_TOKEN
COPY package.json package-lock.json* ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
