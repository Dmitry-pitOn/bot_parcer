from datetime import date
from telebot import types
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup
from aiohttp import ClientSession
import config
import json
import asyncio
import telebot
import requests
import os
import pathlib
import smtplib
import re

bot = telebot.TeleBot(config.TOKEN)
email = ''
number_of_page = ''
real_month = ''
current_date = date.today()
tel_numbers = []
list_messages = []
months = ['Январь', "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь",
          "Декабрь"]


@bot.message_handler(commands=['about'])
def about(message):
    mess = f'Бот парсит телефонные номера автовладельцев с сайта Автомалиновки - "av.by", пожалуй, самого популярного автопортала Беларуси. ' \
           f'Пока парсим Витебск и ближайшие населённые пункты, где нет диагностических станций. ' \
           f'Функционал бота постоянно расширяется, следите за обновлениями! '
    bot.send_message(message.chat.id, mess)


@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, f"Привет, {message.from_user.first_name}!")

    keyboard_months = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard_months.add(*months)
    mess = f'Начнём работу! Выбери месяц рассылки\n' \
           f'(сегодня {date.today().strftime("%d.%m.%Y")}):'
    bot.send_message(message.chat.id, mess, reply_markup=keyboard_months)
    bot.register_next_step_handler(message, actual_month)


def actual_month(message):
    global real_month
    real_month = message.text
    if real_month.capitalize() in months:
        bot.send_message(message.chat.id,
                         "Укажите количество страниц, которые нужно спарсить.\nНа каждой странице по 25 номеров. Если рассылка раз в неделю, то обычно хвататает 10 страниц: ")
        bot.register_next_step_handler(message, number_of_pages)
    else:
        bot.send_message(message.chat.id,
                         'Неверно указан месяц... \nНажмите на квадрат с четырьмя точками и нажмите на кнопку с названием месяца,'
                         ' или напишите вручную русскими буквами: ')
        bot.register_next_step_handler(message, actual_month)
        return


def number_of_pages(messages):
    global number_of_page
    number_of_page = messages.text.strip()
    if number_of_page.isdigit() and int(number_of_page) < 20:
        number_of_page = int(number_of_page)
        bot.send_message(messages.chat.id,
                         'Отлично!\nТеперь напиши адрес электронной почты, на который присылать номера - и начнём:')
        bot.register_next_step_handler(messages, start_parcer)
    else:
        bot.send_message(messages.chat.id, "Неверно указано количество страниц. Введите число:")
        bot.register_next_step_handler(messages, number_of_pages)
        return


def start_parcer(messages):
    global email
    messages.text.strip().lower()
    pattern = re.compile(r'[\w.-]+@[\w]+.ru|com|yandex|gmail')
    result = pattern.search(messages.text.strip().lower())
    if result:
        email = result[0]
    else:
        bot.send_message(messages.chat.id,
                         "Указан неверный почтовый адрес. Введите корректный почтовый адрес, оканчивающийся на .ru или .com:")
        bot.register_next_step_handler(messages, start_parcer)
        return

    bot.send_message(messages.chat.id, "Идёт работа. Ожидайте...")
    main()

    ready_image = open("images/ready.jpg", 'rb')
    bot.send_photo(messages.chat.id, ready_image)
    bot.send_message(messages.chat.id,
                     f"{list_messages[0]}\n{list_messages[1]}\n{list_messages[2]}\n{list_messages[3]}\n{list_messages[4]}")
    bot.send_message(messages.chat.id, "Номера собраны и отфильтрованы. Проверьте почту!")
    list_messages.clear()


def parcing_numbers(page):
    headers = {
        "accept": "*/*",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36"
    }
    proxy = {'https': f'http://{config.proxy_login}:{config.proxy_password}@149.126.236.24:9363'}
    response_list = []
    for number in range(1, page + 1):
        url = f"https://cars.av.by/filter?place_city[0]=7&place_region[0]=1002&page={number}&sort=4"
        with requests.Session() as sess:
            src = sess.get(url, headers=headers, proxies=proxy)
            result = src.text

            soup = BeautifulSoup(result, "lxml")
            id_link = soup.find_all(class_="listing-item__link")

            for i in id_link:
                id_list = i.get("href").split("/")
                link_with_id = f"https://api.av.by/offers/{id_list[-1]}/phones"
                response = sess.get(link_with_id).json()
                if isinstance(response, list):
                    response_list.append(response[0])

    tel_numbers = []
    for i in response_list:
        tel_numbers.append(f"{i['country']['code']}{i['number']}")

    mess_1 = f"Спарсено номеров: {len(tel_numbers)}"
    mess_2 = f"Из них дубликатов: {len(tel_numbers) - len(set(tel_numbers))}"
    tel_numbers = set(tel_numbers)

    # добавляем информационные сообщения в список
    list_messages.append(mess_1)
    list_messages.append(mess_2)

    # записываем все собранные номера в файл
    with open(f"tel_files/collected numbers/collected_numbers({len(tel_numbers)},[{current_date}]).txt", 'w',
              encoding='utf-8') as file:
        for number in tel_numbers:
            file.write(f"{number}\n")
    return tel_numbers


def filter_numbers(set_numbers):
    # создаём множество из всех номеров
    for root, dirs, files in os.walk('tel_files/all_numbers'):
        all_numbers_file = f"{root}/{files[0]}"
        with open(all_numbers_file, 'r', encoding='utf-8') as file:
            all_numbers = set(file.read().split())

        # удаляем дубликаты из собранных номеров, сравнивая с общим списком
        new_numbers = set_numbers - all_numbers
        mess_3 = f"Дубликатов c общим списком номеров: {len(set_numbers.intersection(all_numbers))}"
        len_all_numbers = len(new_numbers.union(all_numbers))

        # добавляем в общий список новые номера и переименовываем файл
        with open(all_numbers_file, 'a', encoding='utf-8') as file:
            for num in new_numbers:
                file.write(f"{num}\n")
        os.rename(all_numbers_file, f"{root}/all_numbers ({len_all_numbers}).txt")

        mess_4 = f"Теперь в базе всего {len_all_numbers} номеров"
        list_messages.append(mess_3)
        list_messages.append(mess_4)

    # записываем новые номера в отдельный файл
    with open(f"tel_files/new_numbers/new_numbers ({len(new_numbers)}), [{current_date}].txt", "w") as file:
        for i in new_numbers:
            file.write(f"{i}\n")


def filter_per_week(month):
    all_tel = set()

    # собираем все номера с начала года
    for i in range(months.index(month) + 1):
        for root, dirs, files in os.walk(f"tel_files/months/{months[i]}/"):
            for i in files:
                with open(f"{root}/{i}", 'r', encoding='utf-8') as f:
                    temp_list = f.read().split()
                    all_tel = all_tel.union(set(temp_list))

    # открываем собранные номера, применяя фильтр по дате создания файла и фильтруем с общим списком
    for root, dirs, files in os.walk("tel_files/collected numbers/"):
        all_files = [os.path.join(root, file) for file in files]
        last_file = max(all_files, key=os.path.getctime)
        with open(last_file, 'r', encoding='utf-8') as file:
            collected_numbers = file.read().split()
            mailing_list = set(collected_numbers) - all_tel
    mess_5 = f"Телефонов для рассылки:  {len(mailing_list)}"
    list_messages.append(mess_5)

    # записываем номера для рассылки в файл
    current_date = date.today()
    with open(rf"tel_files/months/{month}/Еженедельная рассылка/вит_еженед_фильтр({current_date: %d-%m-%Y}).txt",
              'w') as f:
        for i in mailing_list:
            f.write(f"{i}\n")


def send_mail(send_to):
    sender = config.sender_email
    password = config.sender_password

    for root, dirs, files in os.walk(f"tel_files/months/{real_month}/еженедельная рассылка/"):
        all_files = [os.path.join(root, file) for file in files]
        last_file = max(all_files, key=os.path.getctime)

    with open("template_html/index.html", errors='ignore', encoding='utf-8') as file:
        template = file.read()
    with open(last_file, 'r', encoding='utf-8') as f:
        docfile = MIMEText(f.read())

    server = smtplib.SMTP('smtp.gmail.com', port=587)
    server.starttls()
    server.login(sender, password)

    msg = MIMEMultipart()
    msg["Subject"] = 'Файл с номерами готов!'
    msg["From"] = 'Sender'
    msg["To"] = send_to
    msg.attach(MIMEText("Здаров!"))
    msg.attach(MIMEText(template, 'html'))

    # добавляем заголовки, чтобы в письме приходил файл, а не текст файла
    docfile.add_header('content-disposition', 'attachment', filename='номера.txt')
    msg.attach(docfile)

    server.sendmail(sender, send_to, msg.as_string())
    server.quit()


def main():
    lst = parcing_numbers(number_of_page)
    filter_numbers(lst)
    filter_per_week(real_month)
    send_mail(email)


bot.polling(none_stop=True)
