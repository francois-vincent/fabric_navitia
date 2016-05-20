FROM debian:8

RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y sysvinit-core
RUN apt-get install -y python2.7-dev python-pip locales sudo git logrotate vim
RUN apt-get remove -y systemd
RUN pip install --upgrade pip virtualenv

# set locale to French
RUN sed -i "/^# fr_FR.UTF-8 UTF-8/c\fr_FR.UTF-8 UTF-8" /etc/locale.gen
RUN locale-gen fr_FR.UTF-8

# SSH
RUN apt-get install -y openssh-server
# configure SSH server
RUN mkdir /var/run/sshd
RUN mkdir -p /root/.ssh
# SSH login fix. Otherwise user is kicked off after login
RUN sed 's@session\s*required\s*pam_loginuid.so@session optional pam_loginuid.so@g' -i /etc/pam.d/sshd
COPY keys/unsecure_key.pub /root/.ssh/authorized_keys
RUN chmod 644 /root/.ssh/authorized_keys

# Apache
RUN apt-get install -y apache2 libapache2-mod-wsgi
# set basic Apache config
RUN mkdir /etc/apache2/conf.d
RUN echo "ServerName localhost" >> /etc/apache2/apache2.conf
RUN echo "Include conf.d/" >> /etc/apache2/apache2.conf

# Redis
RUN apt-get install -y redis-server
# change redis-server conf for not daemonize (for supervisord)
RUN sed -i '/^daemonize yes/c\daemonize no' /etc/redis/redis.conf

# Postgres
RUN apt-get install -y  postgresql-server-dev-all postgis

# RabbitMQ
RUN apt-get install -y rabbitmq-server
RUN touch /etc/rabbitmq/rabbitmq.config
RUN echo "[{rabbit, [{loopback_users, []}]}]." >> /etc/rabbitmq/rabbitmq.config

# Supervisord
RUN apt-get install -y supervisor
COPY debian8/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord"]
