FROM python:3.6-slim-stretch
WORKDIR /var/unialert

ENV TZ=Europe/Madrid
RUN apt-get update && apt-get install -y cron

RUN mkdir /config
RUN pip install tzlocal==2.1
RUN pip install Pillow==8.1.0
ADD https://raw.githubusercontent.com/fmartineze/Unialert/main/mail_agent.py /var/unialert/mail_agent.py
ADD https://raw.githubusercontent.com/fmartineze/Unialert/main/reporter.py /var/unialert/reporter.py

RUN touch /etc/cron.d/simple-cron
RUN echo "50 7 * * * /usr/local/bin/python3.6 /var/unialert/mail_agent.py -p:/config >/var/log/cron.log" >/etc/cron.d/simple-cron
RUN echo "0 8 * * * /usr/local/bin/python3.6 /var/unialert/reporter.py -p:/config >/var/log/cron.log" >>/etc/cron.d/simple-cron
RUN chmod 0644 /etc/cron.d/simple-cron
RUN crontab /etc/cron.d/simple-cron
RUN touch /var/log/cron.log

CMD /usr/local/bin/python3.6 /var/unialert/mail_agent.py -p:/config ; /usr/local/bin/python3.6 /var/unialert/reporter.py -p:/config ; cron && tail -f /var/log/cron.log

