import time
import sys
import requests
import os
import re
import shutil
import argparse
import logging
from bs4 import BeautifulSoup
from plexapi.server import PlexServer
from qbittorrent import Client
from requests_html import HTMLSession

session = HTMLSession()
qb = Client("http://192.168.0.101:8090")
qb.login("xdsai","admins")
useragent = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"}
daisy_webhook_link = 'https://discord.com/api/webhooks/993897033259810946/7mDq6-TXPL5BPM7n0zsAnUlMzdtXJQBCinRsyCQZzJ4GwIxM3CfjqUdiIP-Y6P1LCKSZ'
token = 'KMUHALDo6oHH-dLamrAP'
plex = PlexServer('http://192.168.0.101:32400',token)
logging.basicConfig(filename='log.txt',
                    filemode='a',
                    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                    datefmt='%H:%M:%S',
                    level=logging.info)

drives = [{"type":"movies",
           "path":"/home/alex/hdd5a",
           "free":""},
           {
            "type":"other",
            "path":"/home/alex/hdd1a",
            "free":""
           }]

#for drive in drives:
#    drive['free'] = round(shutil.disk_usage(drive['path']).free/1000000)

def process(torrent_type, show_name, link):
    magnets = magnet_converter(link)

    if torrent_type == 'movie':
        logging.info(f"Detected type: movie")
        path = '/home/alex/hdd5a/movies/'
        path_temp = '/home/alex/hdd5a/temp/'
        docker_save_path = '/movies/temp/'
        for magnet in magnets:
            torrent_info = dl(magnet, docker_save_path)

            save_path = re.sub(docker_save_path, path_temp, torrent_info['content_path'])
            movie_file_name = re.sub(docker_save_path,'', torrent_info['content_path'])
            logging.info(f"Generated save path - {save_path}, movie_file_name: {movie_file_name}")
            logging.info(f"Checking for directory...")

            if os.isdir(save_path):
                logging.info(f"Is directory = True")
                files_within = os.listdir(save_path)
                logging.info(f"Files within - {files_within}")
                for file in files_within:
                    if file.endswith('.mkv') or file.endswith('.mp4'):
                        movie_file_name = file
                        logging.info(f"Found movie - {movie_file_name}")
                        movie_extensionless = movie_file_name[:len(movie_file_name)-4]
                        logging.info(f"Extensionless - {movie_extensionless}")
                        os.rename(f"{path_temp}/{movie_file_name}", f"{path}/{movie_file_name}")
                        logging.info(f"Renamed - {path_temp}/{movie_file_name}", f"{path}/{movie_file_name}")
                        break
                for file in files_within:
                    if file.endswith('.srt'):
                        logging.info(f"Found .srt file")
                        os.rename(f"{path_temp}/{file}", f"{path}/{movie_extensionless}.srt")
                        logging.info(f"Renamed - {path_temp}/{file}", f"{path}/{movie_extensionless}.srt")
            else:
                os.rename(save_path, f"{path}/{movie_file_name}")
                logging.info(f"Renamed - {save_path}, {path}/{movie_file_name}")
            plex.library.update()
            logging.info("Updated plex library")

               
    else:
        logging.info("Detected type: other/show")
        path = '/home/alex/hdd1a/'
        path_temp = '/home/alex/hdd1a/temp/'
        docker_save_path = '/other/temp/'
        for magnet in magnets:
            torrent_info = dl(magnet, docker_save_path)

            save_path = re.sub(docker_save_path, path_temp, torrent_info['content_path'])
            movie_file_name = re.sub(docker_save_path,'', torrent_info['content_path'])
            normalized_name = re.sub(' ', '_', show_name)
            logging.info(f"Generated - save_path: {save_path}, movie_file_name: {movie_file_name}, normalized_name: {normalized_name}")
            logging.info("Checking for directory...")

            if os.isdir(save_path):
                logging.info("Is directory = True")

                os.rename(f"{path_temp}/{movie_file_name}", f"{path}/{normalized_name}")
                logging.info(f"Renamed - {path_temp}/{movie_file_name} to {path}/{normalized_name}")
                os.chmod(f'{path}/{normalized_name}', 0o777)
                logging.info("Changed mod to 777")

                if torrent_type == 'show':
                    requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=show&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")
                else:
                    requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=movie&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")
                logging.info("Posted to plex")
                
            else:
                logging.info(f"Checking for SubsPlease in {movie_file_name}")

                if '[SubsPlease]' in movie_file_name:
                    logging.info("SubsPlease found")
                    show_name = re.search(r'\] (.*) - (\d*)', movie_file_name)[1]
                    normalized_name = re.sub(' ','_', show_name).lower()

                    logging.info(f"Generated - show_name: {show_name}, normalized_name = {normalized_name}")
                    logging.info(f"Checking for if folder {path}/{normalized_name} exists")

                    if not os.path.exists(f"{path}/{normalized_name}"):
                        logging.info("Folder not found, creating it...")
                        os.mkdir(f"{path}/{normalized_name}")
                        os.chmod(f'{path}/{normalized_name}', 0o777)
                        logging.info(f"Created {path}/{normalized_name} and set mod to 777")

                        requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=movie&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")
                        logging.info("Posted to plex")

                    os.rename(f"{path_temp}/{movie_file_name}", f"{path}/{normalized_name}")
                    logging.info(f"Renamed {path_temp}/{movie_file_name} to {path}/{normalized_name}")

                else:
                    logging.info("No Subsplease found")
                    normalized_name = re.sub(' ','_', show_name).lower()
                    logging.info(f"Generated normalized_name: {normalized_name}")
                    logging.info(f"Checking for if {path}/{normalized_name} exists")
                    if not os.path.exists(f"{path}/{normalized_name}"):
                        logging.info("Does not exist, attempting to create it...")
                        os.mkdir(f"{path}/{normalized_name}")
                        os.chmod(f'{path}/{normalized_name}', 0o777)
                        logging.info(f"Created {path}/{normalized_name} and set mod to 777")
                        if torrent_type == 'show':
                            requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=show&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")
                        else:
                            requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=movie&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")
                        logging.info("Posted to plex")

                    os.rename(f"{path_temp}/{movie_file_name}", f"{path}/{normalized_name}")
                    logging.info(f"Renamed {path_temp}/{movie_file_name} to {path}/{normalized_name}")
    requests.post(daisy_webhook_link, json = {'embeds':[{'title':f'Download of {torrent_info["name"]} completed', 'color':65436}]})


def magnet_converter(link) -> str:
    logging.info(f"Converting {link[:20]}")
    if '1337x.to' in link or 'nyaa.si' in link:
        init = requests.get(link)
        soup = BeautifulSoup(init.text, 'html.parser')
        logging.info(f"Made soup")
        for href in soup.find_all('a', href = True):
            if href['href'].startswith('magnet:?xt='):
                logging.info(f"Returning [{href['href']}]")
                return [href['href']]
            
    elif 'subsplease.org' in link:
        logging.info(f"Link contains subsplease, getting magnets...")
        init = session.get(link, headers = useragent)
        init.html.render(wait = 3)
        magnets = []
        for abs_link in init.html.absolute_links:
            if abs_link.startswith('magnet:?xt=') and '1080p' in abs_link:
                magnets.append(abs_link)
        logging.info(f"Returning {magnets}")
        return magnets
    elif link.startswith('magnet:?xt='):
        logging.info(f"Link already is a magnet, returning...")
        return [link]
    
def dl(magnet, save_path):
    logging.info(f"Beginning download to {save_path}")
    qb.download_from_link(magnet, save_path = save_path)
    time.sleep(5)
    torrent_info = qb.torrents(limit=1, sort = 'added_on', reverse = True)[0]
    torrent_name = torrent_info['name']
    logging.info(f"Found torrent name - {torrent_info['name']}")
    requests.post(daisy_webhook_link, json = {'embeds':[{'title':f'Download of {torrent_name} started', 'color':65436}]})

    while torrent_info['amount_left'] != 0:
        for torrent in qb.torrents():
            if torrent['name'] == torrent_name:
                torrent_info = torrent
                break
        time.sleep(1)
    logging.info(f"Torrent download finished, returning...")
    logging.info(f"{torrent_info}")
    return torrent_info


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Process some integers.')
    parser.add_argument('-t', type=str)
    parser.add_argument('-n', default = '', type=str)
    parser.add_argument('-m', type=str)
    args = parser.parse_args()
    if args.t.lower() not in ['movie', 'show', 'other']:
        print('invalid movie type')
        exit(1)
    else:
        torrent_type = args.t.lower()
    name = args.n
    link = args.m
    logging.info(f"Starting new torrent - type: {torrent_type}, name: {name}, link: {link[:20]}")
    process(torrent_type, name, link)