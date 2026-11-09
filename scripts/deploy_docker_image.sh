#!/bin/bash

# Stop containers based on the image `kibad/crawler`
docker stop $(docker ps -a --format="{{.ID}} {{.Image}}" | grep kibad/crawler | cut -d' ' -f1)

# Remove containers based on the image `kibad/crawler`
docker rm $(docker ps -a --format="{{.ID}} {{.Image}}" | grep kibad/crawler | cut -d' ' -f1)

# Remove and build a new Docker image
docker rmi $(docker images kibad/crawler:1.0 -q) \
&& docker build -t kibad/crawler:1.0 .
