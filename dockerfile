FROM python:3.6-slim-stretch
WORKDIR /var/unialert

ENV TZ=Europe/Madrid
RUN apt-get update && apt-get install -y cron
RUN apt-get install -y git

RUN mkdir /config
RUN pip install tzlocal==2.1
RUN pip install Pillow==8.1.0
RUN git clone https://github.com/fmartineze/Unialert.git /var/unialert

RUN touch /etc/cron.d/simple-cron
RUN echo "50 7 * * * /usr/local/bin/python3.6 /var/unialert/mail_agent.py -p:/config >/var/log/mail_agent.log" >/etc/cron.d/simple-cron
RUN echo "0 8 * * * /usr/local/bin/python3.6 /var/unialert/reporter.py -p:/config >/var/log/reporter.log" >>/etc/cron.d/simple-cron
RUN chmod 0644 /etc/cron.d/simple-cron
RUN crontab /etc/cron.d/simple-cron
RUN touch /var/log/cron.log

CMD /usr/local/bin/python3.6 /var/unialert/mail_agent.py -p:/config ; /usr/local/bin/python3.6 /var/unialert/reporter.py -p:/config ; cron && tail -f /var/log/cron.log