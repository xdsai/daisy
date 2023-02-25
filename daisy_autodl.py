import logging
logging.basicConfig(filename='alog',
    filemode='a',
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=logging.INFO)

import requests, json, time, re, feedparser, subprocess
subsplease = 'https://subsplease.org/rss/?r=1080'

def fetch_shows():
    init = feedparser.parse(subsplease)
    releases = []
    for show in init.entries:
        name = re.sub('- 1080', '', show.category)
        releases.append({
            "name": name,
            "magnet": show.link,
            "title":show.title
        })
    return releases

logging.info(f"Starting loop...")

while True:
    with open('autodl_queries.json', 'r') as ir:
        autodl_queries = json.load(ir)
        logging.info(f"autodl_queries.json loaded")
        logging.info(f"{autodl_queries}")
    with open('downloaded.json', 'r') as dld:
        dld = json.load(dld)

    logging.info(f"downloaded.json loaded")
    logging.info(f"{dld}")
    releases = fetch_shows()
    logging.info(f"Returned releases")
    for query in autodl_queries:
        logging.info(f"Checking query: {query}")
        for show in releases:
            if query in show['name'].lower():
                logging.info(f"Query matched! - {show['name']}")
                logging.info(f"Checking for if match is not in downloaded - {show['title']}")
                if show['title'] not in dld:
                    logging.info(f"Show is not in downloaded, continuing...")
                    logging.info(f'Calling subprocess with params - ./daisy_shell.sh Other autodl "{show["magnet"]}"')
                    subprocess.call(['sh','daisy_shell.sh', 'Other', "autodl", show["magnet"]])
                    dld.append(show['title'])
                    with open('downloaded.json', 'w') as dld_update:
                        json.dump(dld, dld_update)
                    time.sleep(20)
                else:
                    logging.info(f"Show is in downloaded, skipping... - {show['title']}")
    time.sleep(1200)
