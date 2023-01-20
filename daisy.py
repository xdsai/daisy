import time
import sys
import requests
import os
import re
import shutil
import argparse
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
        path = '/home/alex/hdd5a/movies/'
        path_temp = '/home/alex/hdd5a/temp/'
        docker_save_path = '/movies/temp/'
        for magnet in magnets:
            torrent_info = dl(magnet, docker_save_path)

            save_path = re.sub(docker_save_path, path_temp, torrent_info['content_path'])
            movie_file_name = re.sub(docker_save_path,'', torrent_info['content_path'])

            if os.isdir(save_path):
                files_within = os.listdir(save_path)
                for file in files_within:
                    if file.endswith('.mkv') or file.endswith('.mp4'):
                        movie_file_name = file
                        movie_extensionless = movie_file_name[:len(movie_file_name)-4]
                        os.rename(f"{path_temp}/{movie_file_name}", f"{path}/{movie_file_name}")
                        break
                for file in files_within:
                    if file.endswith('.srt'):
                        os.rename(f"{path_temp}/{file}", f"{path}/{movie_extensionless}.srt")
            else:
                os.rename(save_path, f"{path}/{movie_file_name}")
            plex.library.update()

               
    else:
        path = '/home/alex/hdd1a/'
        path_temp = '/home/alex/hdd1a/temp/'
        docker_save_path = '/other/temp/'
        for magnet in magnets:
            torrent_info = dl(magnet, docker_save_path)

            save_path = re.sub(docker_save_path, path_temp, torrent_info['content_path'])
            movie_file_name = re.sub(docker_save_path,'', torrent_info['content_path'])
            normalized_name = re.sub(' ', '_', show_name)

            if os.isdir(save_path):
                os.rename(f"{path_temp}/{movie_file_name}", f"{path}/{normalized_name}")
                os.chmod(f'{path}/{normalized_name}', 0o777)
                if torrent_type == 'show':
                    requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=show&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")
                else:
                    requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=movie&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")

            else:
                if '[SubsPlease]' in movie_file_name:
                    show_name = re.search(r'\] (.*) - (\d*)', movie_file_name)[1]
                    plex_name = show_name
                    normalized_name = re.sub(' ','_', show_name).lower()
                    if not os.path.exists(f"{path}/{normalized_name}"):
                        os.mkdir(f"{path}/{normalized_name}")
                        os.chmod(f'{path}/{normalized_name}', 0o777)
                        requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=movie&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")
                    os.rename(f"{path_temp}/{movie_file_name}", f"{path}/{normalized_name}")

                else:
                    normalized_name = re.sub(' ','_', show_name).lower()
                    if not os.path.exists(f"{path}/{normalized_name}"):
                        os.mkdir(f"{path}/{normalized_name}")
                        os.chmod(f'{path}/{normalized_name}', 0o777)
                        if torrent_type == 'show':
                            requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=show&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")
                        else:
                            requests.post(f"http://192.168.0.101:32400/library/sections?show_name={show_name}&type=movie&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={path}/{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")

                    os.rename(f"{path_temp}/{movie_file_name}", f"{path}/{normalized_name}")


def magnet_converter(link) -> str:
    if '1337x.to' in link or 'nyaa.si' in link:
        init = requests.get(link)
        soup = BeautifulSoup(init.text, 'html.parser')
        for href in soup.find_all('a', href = True):
            if href['href'].startswith('magnet:?xt='):
                return [href['href']]
            
    elif 'subsplease.org' in link:
        init = session.get(link, headers = useragent)
        init.html.render(wait = 3)
        magnets = []
        for abs_link in init.html.absolute_links:
            if abs_link.startswith('magnet:?xt=') and '1080p' in abs_link:
                magnets.append(abs_link)
        return magnets
    elif link.startswith('magnet:?xt='):
        return [link]
    
def dl(magnet, save_path):
    qb.download_from_link(magnet, save_path = save_path)
    time.sleep(5)
    torrent_info = qb.torrents(limit=1, sort = 'added_on', reverse = True)[0]
    torrent_name = torrent_info['name']
    requests.post(daisy_webhook_link, json = {'embeds':[{'title':f'Download of {torrent_name} started', 'color':65436}]})

    while torrent_info['amount_left'] != 0:
        for torrent in qb.torrents():
            if torrent['name'] == torrent_name:
                torrent_info = torrent
                break
        time.sleep(1)

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
        torrent_type = args.t
    name = args.n
    link = args.m
    process(torrent_type, name, link)