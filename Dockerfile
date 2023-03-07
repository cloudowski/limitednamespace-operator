FROM python:3.11
COPY requirements.txt /src/
RUN pip install -r /src/requirements.txt
COPY lns.py /src/
CMD kopf run /src/lns.py -A --verbose --liveness=http://0.0.0.0:8080/healthz