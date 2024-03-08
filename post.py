import re
import os
import json
import argparse
import threading
import dataclasses
import configparser
from queue import Queue
from urllib.parse import urlparse
from typing import Optional, Tuple, Any

import requests
from bs4 import BeautifulSoup

from utils import Logger

GET_HEADERS = {
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Sec-Fetch-Site': 'same-origin',
    'Upgrade-Insecure-Requests': '1',
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
}

POST_HEADERS = {**GET_HEADERS, 'Content-Type': 'application/x-www-form-urlencoded'}

requests.urllib3.disable_warnings()

config = configparser.ConfigParser()

with open("./settings/settings.ini") as file:
    config.read_file(file)

START_URL = config.get("start url", "url")

BASE_URL = f"{urlparse(START_URL).scheme}://{urlparse(START_URL).netloc}" + "{}"

BASE_RESOURCE_ID = re.search(r"\d+", START_URL).group()

PARSER = argparse.ArgumentParser(description="Optional update args")

PARSER.add_argument("-i", "--input", nargs="+", type=str, default="./input/")

PARSER.add_argument("-u", "--update", action="store_true")

@dataclasses.dataclass
class User:
    """Stores user credentials"""
    username: str = config.get("credentials", "username")
    password: str = config.get("credentials", "password")

class BibleVersePoster:
    """Posts html files to https://bsi.driftingkelp.com/"""
    def __init__(self, update: bool) -> None:
        self.logger = Logger(__class__.__name__)
        self.logger.info("{:*^50}".format("BibleVersePoster Started"))

        self.len_queue = 0
        self.is_update = update
        self.posted, self.failed, self.posted_resources = [], [], []

        self.queue = Queue()
        self.session = requests.Session()
        self.csrf_token = self.__login()
        self.thread_num = int(config.get("threads", "number"))
    
    def __get_request(self, url: str, params: Optional[dict]=None) -> Optional[requests.Response]:
        """Performs a get request"""
        for _ in range(3):
            try:
                response = self.session.get(url, headers=GET_HEADERS, params=params, verify=False)

                if response.ok: return response
            
            except:
                self.logger.warn("Request to {} failed! Retrying...".format(url))

        self.logger.error("Request failed three times! Exiting..", True)
    
    def __post_request(self, url: str, payload: dict[str, Any]=None, files: list=None) -> Optional[requests.Response]:
        """Performs a post request"""
        for _ in range(3):
            try:
                if payload:
                    response = self.session.post(url, headers=POST_HEADERS, data=payload, verify=False)
                else:
                    response = self.session.post(url, files=files, headers=GET_HEADERS, verify=False)

                if response.ok: return response
            
            except:
                self.logger.warn("Request to {} failed! Retrying...".format(url))
        
        self.logger.error("Request failed three times! Exiting..", True)
    
    @staticmethod
    def __extract_login_payload(response: requests.Response) -> Optional[dict[str, str]]:
        """Extracts login payload from the response object"""
        soup = BeautifulSoup(response.text, "html.parser")

        items = {}

        for form in soup.select("form"):
            if not "login" in form["action"]: continue

            for item in form.select("input"):
                if not item.get("name"): continue

                items[item["name"]] = item.attrs.get("value")
            
            items.update({'login': User.username, 'password': User.password})

            return items

    def __login(self) -> str:
        """Logs into the site"""
        self.logger.info("Logging into {}...".format(BASE_URL.format("")))

        login_url = BASE_URL.format("/login/login")

        response = self.__get_request(login_url)

        login_payload = self.__extract_login_payload(response)

        if login_payload is None:
            self.logger.error("Login failed! Failed to get csrf token.", True)
        
        self.__post_request(login_url, payload=login_payload)

        self.logger.info("Login successful.")

        return login_payload.get("_xfToken")

    def __read_html_file(self, filepath: str) -> Optional[str]:
        """Reads the html file to be posted and returns it's contents"""
        if not os.path.isfile(filepath): 
            self.logger.warn("Skipping non-existent file >> {}...".format(filepath.split("/")[-1]))

            return

        with open(filepath, encoding="utf-8") as file: return file.read()
    
    @staticmethod
    def __format_html(html: str) -> str:
        """Formats the html to be posted"""
        html = html.replace("\n", "").replace(" ", "&nbsp;")

        html = html.replace("<", "&lt;").replace(">", "&gt;")

        html = html.strip("[parsehtml]").strip("[/parsehtml]")

        html = f'[parsehtml]<div data-xf-p="1">{html}</div>[/parsehtml]'

        html = html.replace("[parsehtml]", '<div data-xf-p="1">[parsehtml]</div>')

        return html.replace('[/parsehtml]', '<div data-xf-p="1">[/parsehtml]</div>', 1)
    
    def __get_chapter(self, html: str) -> str:
        """Extract the book and chapter from the html string"""        
        soup = BeautifulSoup(html, "html.parser")

        for div in soup.select("div"):
            if div.attrs.get("id"): return div.attrs.get("id")
    
    @staticmethod
    def __extract_verse_payload(response: requests.Response) -> Tuple[dict[str, str], str]:
        """Extracts the payload for a verse upload"""
        soup = BeautifulSoup(response.text, "html.parser")

        payload = {}

        for form in soup.select("form"):
            if not form.get("action") or not ("add" in form["action"] or "edit" in form["action"]): 
                continue

            form_action = form.get("action")

            for item in form.select("input"):
                if not item.get("name"): continue

                payload[item["name"]] = item.attrs.get("value")
            
            for item in form.select("select"):
                if not item.get("name"): continue

                for option in item.select("option"):
                    if not option.get("selected") == "selected": continue

                    payload[item["name"]] = option.get("value")

                    break
            
            return payload, form_action

    def __get_existing_resources(self, html: str) -> list[dict[str, str]]:
        """Extracts existing resources from html pulled from the site"""
        soup = BeautifulSoup(html, "html.parser")

        table = soup.select_one("table.dataList-table")

        existing_resources = []

        if table is None: return existing_resources

        for tr in table.select("tr"):
            chapter = tr.select_one("div.dataList-mainRow")
            url = tr.select_one("div.dataList-subRow > a")

            if not (chapter is not None and url is not None): continue
            
            existing_resources.append({chapter.get_text(strip=True): url.attrs.get("href")})
        
        return existing_resources

    def __post_verse(self, verse: dict[str, str], post_url: str, filename: str) -> None:
        """Posts an html file to the site"""
        if post_url.endswith("edit"):
            response = self.__get_request(post_url)
        else:
            params = {
                'title': verse["title"],
                'xc_rc_resource_id': BASE_RESOURCE_ID,
                'xc_rc_title': verse["title"],
                'xc_rc_display_order': verse['xc_rc_display_order'],
            }

            response = self.__get_request(post_url, params=params)

        payload, action_url = self.__extract_verse_payload(response)

        payload = {**payload, **verse, 
                   "_xfRequestUri": action_url, 
                   "_xfWithData": 1, 
                   "_xfResponseType": "json"}
        
        final_payload = [(k, (None, v)) for k, v in payload.items()]
        
        response = self.__post_request(BASE_URL.format(action_url), files=final_payload)

        if response.json()["status"] == "ok": 
            self.posted.append("")

            queue = self.len_queue - len(self.posted) - len(self.failed)

            info_text = f"Queue: {queue} || Posted: {len(self.posted)}"

            if len(self.failed): info_text += f" || Failed: {len(self.failed)}"

            self.logger.info(info_text)
        else:
            self.failed.append("")

            self.logger.warn(f"Failed to post file {filename} \n  <<{str(response.json())}>>")
    
    def __update(self, html_content: str, book: str, chapter: str, file_path: str) -> None:
        """Updates existing resource"""
        for item in self.posted_resources:
            for k, v in item.items():
                if k != f'{book} {chapter}': continue

                url = f"{BASE_URL.format(v).rstrip('/')}/edit"

                self.__post_verse({"description_html": html_content}, url, file_path.split("/")[-1])

                return

    def __work(self, post_url: str, posted_resources: list[str]) -> None:
        """Work to be done by threads"""        
        while True:
            file_path, startrow = self.queue.get()

            html_content = self.__read_html_file(filepath=file_path)

            if html_content is None:
                self.queue.task_done()

                continue

            book_chapter = self.__get_chapter(html=html_content)

            if book_chapter is None:
                self.logger.warn(f"Couldn't extract book and chapter from file {file_path}")

                self.queue.task_done()

                continue

            book, chapter = re.search(r"([\w\s]+)_(\d+)", book_chapter).groups()

            book = book.capitalize()

            html_content = self.__format_html(html_content)

            if f"{book} {chapter}" in posted_resources:
                if not self.is_update:
                    self.logger.info(f"Skipping posted resource <{f'{book} {chapter}'}>")                    

                    self.posted.append("")
                else:
                    self.__update(html_content, book, chapter, file_path)

                self.queue.task_done()

                continue

            order = str(int(chapter) + startrow)

            payload = {"title": f"{book} {chapter}", 
                       "tag_line": f"{book} Chapter {chapter}",
                       "description_html": html_content,
                       'xc_rc_display_order': order}
            
            self.__post_verse(payload, post_url, file_path.split("/")[-1])

            self.queue.task_done()
    
    def __create_work(self, html_files: list[str], posted: list[str]) -> None:
        """Groups the files by book name and adds them to queue to be processed"""
        grouped_files: dict[str, list] = {}

        for file in html_files:
            book = re.search(r"\d{5,5}((\d?\s?)[a-zA-Z_\s]+)\d+", file).group(1)

            grouped_files[book].append(file) if grouped_files.get(book) \
            else grouped_files.update({book: [file]})
        
        self.len_queue = len(html_files)

        with open("./utils/books.json") as f: ordered_books: dict[str, list] = json.load(f)

        grouped_files = self.__order_by_book(grouped_files, list(ordered_books.keys()))

        order, startrow = {}, 0

        for kl in list(ordered_books.keys()): 
            if grouped_files.get(kl): order[kl] = startrow

            if len(order) == len(grouped_files): break

            startrow += ordered_books.get(kl)

        if len(posted):
            for k in list(grouped_files.keys()):
                if re.search(rf"{k}", " ".join(posted), re.I):
                    [self.queue.put((i, order.get(k))) for i in grouped_files.get(k)]

                    self.queue.join()

                    grouped_files.pop(k)

        for k, files in grouped_files.items():
            [self.queue.put((f, order.get(k))) for f in files]

            self.queue.join()
    
    def __order_by_book(self, html_files: dict[str, list], ordered_books: list[str]) -> dict[str, list]:
        """Orders the book following biblical order"""
        ordered_files = {}

        for book in ordered_books:
            for k, v in html_files.items():
                if re.match(k, book, re.I):
                    ordered_files[book] = v

                    break
            
            if len(ordered_files) == len(html_files): return ordered_files

    def post(self, input_path: str) -> None:
        """Entry point to the poster"""
        params = {
            '_xfRequestUri': urlparse(START_URL).path,
            '_xfWithData': '1',
            '_xfToken': self.csrf_token,
            '_xfResponseType': 'json',
        }

        response = self.__get_request(f"{START_URL.rstrip('/')}/chapters-manage", params)

        self.posted_resources = self.__get_existing_resources(response.json()["html"]["content"])

        posted = [k for item in self.posted_resources for k in item.keys()]

        english_category = config.get("english-bible", "category_id")

        post_url = BASE_URL.format(f"/resources/categories/{english_category}/add")

        POST_HEADERS.update({"Content-Type": "multipart/form-data"})

        [threading.Thread(target=self.__work, 
                          daemon=True, args=(post_url, posted, )).start() for _ in range(self.thread_num)]
        
        self.__create_work([f"{input_path.rstrip('/')}/{f}" for f in os.listdir(input_path)], posted)

        self.logger.info("Done posting html files.")

if __name__ == "__main__":
    args = PARSER.parse_args()

    app = BibleVersePoster(args.update)
    app.post(''.join(args.input))