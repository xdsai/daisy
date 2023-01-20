import time
import sys
import requests
import os
import re
import shutil
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

def process(type, name, link):
    magnets = magnet_converter(link)
    if type == 'movie':
        path = '/home/alex/hdd5a/movies/'
        docker_save_path = '/movies/temp/'
        for magnet in magnets:
            torrent_info, file_name = dl(magnet, docker_save_path)
            print(torrent_info)

               
    else:
        path = '/home/alex/other/'
        docker_save_path = '/other/temp/'
        for magnet in magnets:
            torrent_info, file_name = dl(magnet, docker_save_path)
                 
    
        

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
    elif link.startwith('magnet:?xt='):
        return [link]
    
def dl(magnet, save_path):
    info_hash = magnet.split('magnet:?xt=urn:btih:')[1].split('&')[0]
    qb.download_from_link(magnet, save_path = save_path)
    time.sleep(5)
    torrent_info = qb.torrent(info_hash)
    requests.post(daisy_webhook_link, json = {'embeds':[{'title':f'Download of {torrent_info["name"]} started', 'color':65436}]})
    file_name = re.sub(save_path,'',torrent_info['content_path'])
    while torrent_info['amount_left'] != 0:
        torrent_info = qb.torrent(info_hash)
        time.sleep(1)
    return torrent_info, file_name


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print('invalid amount of args')
        exit(1)
    if sys.argv[1] not in ['movie', 'other', 'show']:
        print('invalid torrent type')
        exit(1)
    else:
        torrent_type = sys.argv[1]
    name = sys.argv[2]
    link = sys.argv[3]
    process(torrent_type, name, link)