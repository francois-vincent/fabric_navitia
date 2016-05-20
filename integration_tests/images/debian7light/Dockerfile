FROM debian:7

RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y libboost-all-dev
RUN apt-get install -y python2.7-dev python-pip locales sudo git logrotate vim
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
RUN echo "ServerName localhost" >> /etc/apache2/apache2.conf

# Supervisord
RUN apt-get install -y supervisor
COPY debian7/supervisord.conf /etc/supervisor/conf.d/supervisord.conf

CMD ["/usr/bin/supervisord"]
