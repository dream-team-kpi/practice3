# Інтеграційні програмні системи
#### Практична робота №3
Системи автоматизації збірки, автоматичні тести, рецензування коду та безперервна інтеграція. Робота присвячена організації процесу розробки у репозиторії.

## Build status
[![Build Status](https://travis-ci.org/dream-team-kpi/practice3.svg?branch=master)](https://travis-ci.org/dream-team-kpi/practice3)

## Опис
В рамках лабораторної роботи було написано невеликий сервер для чату, використовуючи Python. Встановлення просте; конфігурації не потрібно.

## Вимоги до ПЗ
Для запуску проекту на вашому комп’ютері має бути встановлене таке програмне забезпечення:

 * Git Можна завантажити з https://git-scm.com/downloads.
 * Python 2.6 і вище (Python3). Можна завантажити з http://www.python.org.
 * pip 9.0.1. Можна завантажити з https://pypi.python.org/pypi/pip.

## Установка
Склонуйте репозиторій за допомогою команди:
```
git clone https://github.com/dream-team-kpi/practice3.git
```
Далі виконайте наступні команди:
```
cd practice3
pip install -r requirements.txt
```
Запустіть сервер:
```
python chat.py --listen=127.0.0.1 --ports=12345
```

## Docker
This repository also has Docker support. 
Please, download and install latest Docker version from official site. See https://www.docker.com/

To create a Docker image type the following command in terminal in the root directory of the project:
```
docker build -t chat .
```
This will build new Docker image with repository name 'chat'.

To run the application type:
```
docker run -p 4000:8888 chat
```
Also, this command will map port 8888 of container to port 4000 of host.

To build and run tests with Docker run the following commands:
```
docker build -t chat-tests -f Dockerfile-tests .
docker run -p 4000:8888 chat-tests
```

## Ліцензія

MIT License


## Автори

* Жабокрицький Ігор
* Кохан Олена
* Махров Антон
* Чайковський Олександр

