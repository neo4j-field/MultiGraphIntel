FROM node:20-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/nginx.conf.template

# Delete the stock default.conf so only our rendered config serves.
RUN rm -f /etc/nginx/conf.d/default.conf

ENV BACKEND_URL=http://localhost:8080
EXPOSE 8080

# Render the template at container start, substituting only BACKEND_URL so
# nginx's own $-variables ($host, $remote_addr, etc.) pass through untouched.
# Then run nginx in the foreground.
CMD ["/bin/sh", "-c", "envsubst '$BACKEND_URL' < /etc/nginx/nginx.conf.template > /etc/nginx/conf.d/default.conf && cat /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'"]
