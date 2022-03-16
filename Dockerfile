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


# Finishim
CMD ["python3.9","-m","emilia"]
