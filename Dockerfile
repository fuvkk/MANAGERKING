# We're using prebuilt docker images
FROM dasbastard/dirty:latest

# Docker
# Clone repo and prepare working directory
# Docker
RUN git clone 'https://github.com/CrePavan/MANAGERKING.git' /root/managerking
RUN mkdir /root/managerking/bin/
WORKDIR /root/managerking/
# Try Upgrade some requirements
# RUN pip3 install -r requirements.txt --upgrade

FROM debian:11
FROM python:3.10.1-slim-buster

WORKDIR /EmikoRobot/

RUN apt-get update && apt-get upgrade -y
RUN apt-get -y install git
RUN python3.9 -m pip install -U pip
RUN apt-get install -y wget python3-pip curl bash neofetch ffmpeg software-properties-common

COPY requirements.txt .

RUN pip3 install wheel
RUN pip3 install --no-cache-dir -U -r requirements.txt



# Finishim
CMD ["python3.9","-m","emilia"]
