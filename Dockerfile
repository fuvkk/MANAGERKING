# We're using prebuilt docker images
FROM dasbastard/dirty:latest

# Docker

# Try Upgrade some requirements
# RUN pip3 install -r requirements.txt --upgrade

# Finishim
CMD ["python3","-m","emilia"]
