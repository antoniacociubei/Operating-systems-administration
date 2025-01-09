#!/bin/bash

service mariadb start

if ! test -f /app/sql-init; then
    mysql -u root < /app/db.sql
    touch /app/sql-init
fi

./cnc
