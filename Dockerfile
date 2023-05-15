FROM openeuler/openeuler:22.03-lts

MAINTAINER liuqi<469227928@qq.com>

RUN yum install -y vim wget git xz tar make automake autoconf libtool gcc gcc-c++ kernel-devel libmaxminddb-devel pcre-devel openssl openssl-devel tzdata \
readline-devel libffi-devel python3-devel mariadb-devel python3-pip net-tools.x86_64 iputils

RUN pip3 install uwsgi

WORKDIR /work/robot-openeuler-ci-tools

COPY . /work/robot-openeuler-ci-tools

RUN cd /work/robot-openeuler-ci-tools && pip3 install -r requirements.txt

ENV LANG=en_US.UTF-8 \
    PYTHONPATH=/work/robot-openeuler-ci-tools

ENTRYPOINT ["uwsgi", "--ini", "/work/robot-openeuler-ci-tools/deploy/production/uwsgi.ini"]
