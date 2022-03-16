# We're using prebuilt docker images
FROM dasbastard/dirty:latest

# Docker
# Clone repo and prepare working directory
# Docker
RUN git clone 'https://github.com/CrePavan/MANAGER-KING-GROUP-SECURER.git' /root/managerking
RUN mkdir /root/MANAGER-KING-GROUP-SECURER/bin/
WORKDIR /root/MANAGER-KING-GROUP-SECURER/
# Try Upgrade some requirements
# RUN pip3 install -r requirements.txt --upgrade


# Finishim
CMD ["python3.9","-m","emilia"]
