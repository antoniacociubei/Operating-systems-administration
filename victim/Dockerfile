FROM ubuntu:latest

RUN apt update && apt install -y telnetd openbsd-inetd tcpdump

RUN useradd -rm -d /home/admin -s /bin/bash -g root -G sudo -u 1001 admin -p "$(openssl passwd -1 admin)"

RUN echo "telnet stream tcp nowait root /usr/sbin/telnetd telnetd" >> /etc/inetd.conf

EXPOSE 23

ENTRYPOINT /usr/sbin/inetd && service --status-all && tcpdump -i any -n ip
















