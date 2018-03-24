#!/bin/bash

openssl req -newkey rsa:2048 -nodes -keyout key.pem -x509 -days 365 -out certificate.pem
openssl pkcs12 -inkey key.pem -in certificate.pem -export -out certificate.p12

cat key.pem certificate.pem > temp.pem
openssl pkcs12 -export -in temp.pem -out server.p12 -name localhost

keytool -importkeystore  -destkeystore keystore.jks -srckeystore server.p12 -srcstoretype PKCS12 -alias localhost

rm temp.pem
rm server.p12