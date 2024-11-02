import requests
from bs4 import BeautifulSoup
from reading import text_to_audio
from utilities import scrape_blog, extract_date_from_blog


def main():

    start_url = "https://www.hinatazaka46.com/s/official/diary/detail/40153?ima=0000&cd=member"
    base_url = "https://www.hinatazaka46.com"

    url = start_url

    while True:
        print("Scraping URL: ", url)
        blog_id = url.split("/")[-1].split("?")[0]
        date_str = extract_date_from_blog(url)

        text = scrape_blog(url)
        
        try:
            text_to_audio(text, f"data/{date_str}-{blog_id}.mp3")
        except Exception as e:
            print("Error converting to audio: ", e)
            continue

        # Get the previous blog URL
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")

        prev_link = soup.find("div", class_="c-pager__item c-pager__item--prev c-pager__item--kiji c-pager__item--kiji__blog")
        
        if prev_link and prev_link.find("a"):
            url = base_url + prev_link.find("a")["href"]

        else:
            break

if __name__ == "__main__":
    main()