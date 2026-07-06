# OpsGPT — frontend build + static serving (also the edge reverse-proxy for /api)
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/opsgpt.conf
# included by both server blocks; kept OUT of conf.d so nginx doesn't try to
# load these `location` directives at the http context.
COPY nginx-locations.conf /etc/nginx/opsgpt-locations.conf
COPY security-headers.conf /etc/nginx/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
