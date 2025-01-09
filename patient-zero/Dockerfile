FROM ubuntu:20.04
RUN apt-get update && apt-get install -y wget
WORKDIR /app
COPY start.sh /app/
RUN chmod +x start.sh
CMD ["./start.sh"]
