# We're using prebuilt docker images
FROM dasbastard/dirty:latest

# Docker
# Clone repo and prepare working directory
# Docker
RUN git clone 'https://github.com/CrePavan/MANAGERKING' /root/MANAGERKING
RUN mkdir /root/MANAGERKING/bin/
WORKDIR /root/MANAGERKING/

# Try Upgrade some requirements
# RUN pip3 install -r requirements.txt --upgrade

# Finishim
CMD ["python3","-m","emilia"]
