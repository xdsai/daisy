import logging
logging.basicConfig(filename='dlog',
    filemode='a',
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S',
    level=logging.INFO)

import time
import sys
import requests
import os
import re
import getpass
import shutil
import subprocess
import argparse
from bs4 import BeautifulSoup
from plexapi.server import PlexServer
from qbittorrent import Client
from requests_html import HTMLSession

logging.info("------------------NEW TORRENT------------------")
parser = argparse.ArgumentParser()
parser.add_argument('-t', default = '', type=str)
parser.add_argument('-n', default = '', type=str)
parser.add_argument('-m', default = '', type=str)
args = parser.parse_args()
logging.info(f"Parsed args - type: {args.t}, name: {args.n}, link: {args.m}")
if args.t.lower() not in ['movie', 'show', 'other']:
    logging.info("Invalid torrent type - exiting")
    sys.exit(1)
else:
    torrent_type = args.t.lower()
name = args.n
link = args.m

session = HTMLSession()
qb = Client("http://192.168.0.101:8080/")
qb.login("xdsai","admins")
logging.info(f"QB object: {qb}")

useragent = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/55.0.2883.87 Safari/537.36"}
logging.info(f"Using user-agent: {useragent}")

daisy_webhook_link = 'https://discord.com/api/webhooks/993897033259810946/7mDq6-TXPL5BPM7n0zsAnUlMzdtXJQBCinRsyCQZzJ4GwIxM3CfjqUdiIP-Y6P1LCKSZ'
token = 'iUZBWnFpHhsfMoTFjPAk'
plex = PlexServer('http://192.168.0.101:32400',token)
logging.info(f"PLEX server entity: {plex}")


logging.info(f"Env thinks the user is {os.getlogin()}, effective user is {getpass.getuser()}")
logging.info(f"Starting new torrent")


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
    if len(magnets) != 0:
        if torrent_type == 'movie':
            logging.info(f"Detected type: movie")
            path = '/home/alex/hdd5a/movies/'
            path_temp = '/home/alex/hdd5a/temp/'
            docker_save_path = '/movies/temp/'
            for magnet in magnets:
                torrent_info = dl(magnet, docker_save_path)
                if torrent_info['content_path'] != 'ERROR_RETURNED' and torrent_info['content_path'] != '':
                    save_path = re.sub(docker_save_path, path_temp, torrent_info['content_path'])
                    movie_file_name = re.sub(docker_save_path,'', torrent_info['content_path'])
                    logging.info(f"Generated save path - {save_path}, movie_file_name: {movie_file_name}")
                    logging.info(f"Checking for directory...")

                    if os.path.isdir(save_path) == True:
                        logging.info(f"Is directory = True")

                        files_within = os.listdir(save_path)
                        logging.info(f"Files within - {files_within}")

                        for file in files_within:
                            if file.endswith('.mkv') or file.endswith('.mp4'):
                                
                                movie_file_name = file
                                logging.info(f"Found movie - {movie_file_name}")
                                movie_extensionless = movie_file_name[:len(movie_file_name)-4]
                                logging.info(f"Extensionless - {movie_extensionless}")

                                logging.info(f"Trying to rename - {save_path}/{movie_file_name} to {path}/{movie_file_name}")
                                os.rename(f"{save_path}/{movie_file_name}", f"{path}/{movie_file_name}")
                                break
                                
                        for file in files_within:
                            if file.endswith('.srt'):
                                logging.info(f"Found .srt file")
                                logging.info(f"Trying to rename - {save_path}/{file} to {path}/{movie_extensionless}.srt")
                                os.rename(f"{save_path}/{file}", f"{path}/{movie_extensionless}.srt")
                        logging.info(f"Trying to remove - {path_temp}{movie_file_name}")
                        shutil.rmtree(f"{path_temp}{movie_file_name}")
                        
                    else:
                        logging.info(f"Trying to rename - {save_path} to {path}{movie_file_name}")
                        os.rename(save_path, f"{path}{movie_file_name}")
                    requests.post(daisy_webhook_link, json = {'embeds':[{'title':f'Download of {torrent_info["name"]} completed', 'color':65436}]})
                    logging.info(f"Download of {torrent_info['name']} completed")
                    plex.library.update()
                    logging.info("Updated plex library")   
        else:
            logging.info("Detected type: other/show")
            path = '/home/alex/hdd1a/'
            path_temp = '/home/alex/hdd1a/temp/'
            docker_save_path = '/other/temp/'
            plex_path = '/app/hdd1a/'
            for magnet in magnets:
                torrent_info = dl(magnet, docker_save_path)

                if torrent_info['content_path'] != 'ERROR_RETURNED' and torrent_info['content_path'] != '':
                    save_path = re.sub(docker_save_path, path_temp, torrent_info['content_path'])
                    movie_file_name = re.sub(docker_save_path,'', torrent_info['content_path'])
                    normalized_name = re.sub(' ', '_', show_name)
                    logging.info(f"Generated - save_path: {save_path}, movie_file_name: {movie_file_name}, normalized_name: {normalized_name}")
                    logging.info("Checking for directory...")

                    if os.path.isdir(save_path) == True:
                        logging.info("Is directory = True")
                        
                        if os.path.exists(f"{path}{normalized_name}") == True:
                            logging.info(f"Normalized directory already exists - {path}{normalized_name}")

                            files_within = os.listdir(f"{path_temp}{movie_file_name}")
                            for file in files_within:
                                logging.info(f"Trying to rename - {path_temp}{movie_file_name}/{file} to {path}{normalized_name}/{file}")
                                os.rename(f"{path_temp}{movie_file_name}/{file}", f"{path}{normalized_name}/{file}")
                            plex.library.update()
                            logging.info("Updated plex library")
                            logging.info(f"Trying to remove - {path_temp}{movie_file_name}")
                            shutil.rmtree(f"{path_temp}{movie_file_name}")

                        else:
                            logging.info(f"Normalized directory doesnt exist yet - {path}{normalized_name}")
                            logging.info(f"Calling subprocess chown to set ownership of temp dir")
                            subprocess.call(["sudo", "chown", "alex:alex", f"{path_temp}{movie_file_name}"])
                            logging.info(f"Trying to rename - {path_temp}{movie_file_name} to {path}{normalized_name}")
                            os.rename(f"{path_temp}{movie_file_name}", f"{path}{normalized_name}")
                            os.chmod(f'{path}{normalized_name}', 0o777)
                            logging.info("Changed mod to 777")

                            if torrent_type == 'show':
                                request_body = f"http://192.168.0.101:32400/library/sections?name={show_name}&type=show&agent=tv.plex.agents.series&scanner=Plex TV Series&language=en-US&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={plex_path}{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en"
                                posty = requests.post(request_body)
                            else:
                                request_body = f"http://192.168.0.101:32400/library/sections?name={show_name}&type=movie&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={plex_path}{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en"
                                posty = requests.post(request_body)
                            if posty.status_code == 201:
                                logging.info("Successfully posted to plex")
                            else:
                                logging.info(f"Failed to post to plex, post request status code: {posty.status_code}, reason: {posty.reason}")
                                logging.info(f"Plex request body: {request_body}")
                        
                    else:
                        logging.info(f"Checking for SubsPlease in {movie_file_name}")

                        if '[SubsPlease]' in movie_file_name:
                            logging.info("SubsPlease found")
                            show_name = re.search(r'\] (.*) - (\d*)', movie_file_name)[1]
                            normalized_name = re.sub(' ','_', show_name).lower()

                            logging.info(f"Generated - show_name: {show_name}, normalized_name = {normalized_name}")
                            logging.info(f"Checking for if folder {path}{normalized_name} exists")

                            if not os.path.exists(f"{path}{normalized_name}"):
                                logging.info("Folder not found, creating it...")
                                os.mkdir(f"{path}{normalized_name}")
                                os.chmod(f'{path}{normalized_name}', 0o777)
                                logging.info(f"Created {path}{normalized_name} and set mod to 777")

                                posty = requests.post(f"http://192.168.0.101:32400/library/sections?name={show_name}&type=movie&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={plex_path}{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en")
                                if posty.status_code == 201:
                                    logging.info("Successfully posted to plex")
                                else:
                                    logging.info(f"Failed to post to plex, post request status code: {posty.status_code}, reason: {posty.reason}")

                            logging.info(f"Calling subprocess chown to set ownership of temp dir")
                            subprocess.call(["sudo", "chown", "alex:alex", f"{path_temp}{movie_file_name}"])

                            logging.info(f"Trying to rename {path_temp}{movie_file_name} to {path}{normalized_name}/{movie_file_name}")
                            os.rename(f"{path_temp}{movie_file_name}", f"{path}{normalized_name}/{movie_file_name}")
                            logging.info(f"Successfully renamed")

                        else:
                            logging.info("No Subsplease found")
                            normalized_name = re.sub(' ','_', show_name).lower()
                            logging.info(f"Generated normalized_name: {normalized_name}")
                            logging.info(f"Checking for if {path}{normalized_name} exists")

                            if not os.path.exists(f"{path}{normalized_name}"):
                                logging.info("Does not exist, attempting to create it...")
                                os.mkdir(f"{path}{normalized_name}")
                                os.chmod(f'{path}{normalized_name}', 0o777)
                                logging.info(f"Created {path}{normalized_name} and set mod to 777")

                                if torrent_type == 'show':
                                    request_body = f"http://192.168.0.101:32400/library/sections?name={show_name}&type=show&agent=tv.plex.agents.series&scanner=Plex TV Series&language=en-US&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={plex_path}{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en"
                                    posty = requests.post(request_body)
                                else:
                                    request_body = f"http://192.168.0.101:32400/library/sections?name={show_name}&type=movie&agent=com.plexapp.agents.none&scanner=Plex Video Files Scanner&language=xn&importFromiTunes=&enableAutoPhotoTags=&downloadMedia=&location={plex_path}{normalized_name}&X-Plex-Product=Plex Web&X-Plex-Version=4.76.1&X-Plex-Client-Identifier=9fqw27x73r6ygz9hstlg47kq&X-Plex-Platform=Firefox&X-Plex-Platform-Version=99.0&X-Plex-Sync-Version=2&X-Plex-Features=external-media,indirect-media&X-Plex-Model=bundled&X-Plex-Device=Linux&X-Plex-Device-Name=Firefox&X-Plex-Device-Screen-Resolution=1920x921,1920x1080&X-Plex-Token=KMUHALDo6oHH-dLamrAP&X-Plex-Language=en"
                                    posty = requests.post(request_body)
                                if posty.status_code == 201:
                                    logging.info("Successfully posted to plex")
                                else:
                                    logging.info(f"Failed to post to plex, post request status code: {posty.status_code}, reason: {posty.reason}")
                                    logging.info(f"Plex request body: {request_body}")
                                    
                            logging.info(f"Calling subprocess chown to set ownership of temp dir")
                            subprocess.call(["sudo", "chown", "alex:alex", f"{path_temp}{movie_file_name}"])

                            logging.info(f"Trying to rename {path_temp}{movie_file_name} to {path}{normalized_name}/{movie_file_name}")
                            os.rename(f"{path_temp}{movie_file_name}", f"{path}{normalized_name}/{movie_file_name}")
                    requests.post(daisy_webhook_link, json = {'embeds':[{'title':f'Download of {torrent_info["name"]} completed', 'color':65436}]})
                    logging.info(f"Download of {torrent_info['name']} completed")
                    plex.library.update()
                    logging.info("Updated plex library")
        for drive in drives:
            drive['free'] = round(shutil.disk_usage(drive['path']).free/1000000000)

        requests.post("https://discord.com/api/webhooks/1079119240986107976/d6GsHCrHSHTVqLIWT71pISSUQHHxmzt6nFXHo4Kz5zQZVg-mVo3uI3j7raCjtb9leJpi", json = {'embeds':[{'title':f"Free space:\nhdd1a - {drives[1]['free']}/931\nhdd5a - {drives[0]['free']}/465", 'color':65436}]})

    else:
        logging.error("Could not find magnets.")
        requests.post(daisy_webhook_link, json = {'embeds':[{'title':f'Could not find magnets for {link}!', 'color':16711680}]})


def magnet_converter(link) -> str:
    logging.info(f"Magnet converter - {link[:40]}")
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
        magnets = []
        retrycounter = 0
        while retrycounter < 5:
            init = session.get(link, headers = useragent)
            init.html.render(wait = 10)
            for abs_link in init.html.absolute_links:
                if abs_link.startswith('magnet:?xt=') and '1080p' in abs_link:
                    if 'Batch' in abs_link:
                        logging.info("Found batch magnet")
                        magnets = [abs_link]
                        break
                    else:
                        magnets.append(abs_link)
            if len(magnets) == 0:
                retrycounter += 1
                logging.info(f"Retrying: on {retrycounter}. retry")
            else:
                break
        logging.info(f"Returning {len(magnets)} magnets")
        return magnets
    
    elif link.startswith('magnet:?xt='):
        logging.info(f"Link already is a magnet, returning...")
        return [link]
    
def dl(magnet, save_path):
    logging.info(f"Beginning download to {save_path}")
    try:
        download_response = qb.download_from_link(magnet, save_path = save_path)
        logging.info(f"QB response: {download_response}")
        if 'fails.' == download_response.lower():
            logging.error(f"Failed to start download {magnet[55:100]}")
            return {'content_path':'ERROR_RETURNED'}
        
    except Exception as e:
        logging.error(f"Error callback: {e}")
        logging.info(f"Local variables: magnet: {magnet} ||| save_path: {save_path}, download: {download_response}")
        return {'content_path':'ERROR_RETURNED'}

    else:
        time.sleep(5)
        try:
            torrent_info = qb.torrents(limit=1, sort = 'added_on', reverse = True)[0]
            torrent_name = torrent_info['name']
            logging.info(f"Found torrent name - {torrent_info['name']}")
            requests.post(daisy_webhook_link, json = {'embeds':[{'title':f'Download of {torrent_name} started', 'color':65436}]})
            meta_DL_counter = 0
            while torrent_info['amount_left'] != 0 or torrent_info['state'] == 'metaDL':
                for torrent in qb.torrents():
                    if torrent['name'] == torrent_name:
                        torrent_info = torrent
                        break
                time.sleep(1)
                if torrent_info['state'] == 'metaDL':
                    meta_DL_counter += 1
                if meta_DL_counter > 120:
                    logging.error(f"Failed to download metadata for {torrent_info['name']}")
                    qb.delete(torrent_info['infohash_v1'])
                    logging.info(f"Deleting failed torrent: {torrent_info['name']}")
                    requests.post(daisy_webhook_link, json = {'embeds':[{'title':f"Failed to download metadata - {torrent_info['name']}, try a different one!", 'color':16711680}]})
                    return {'content_path':'ERROR_RETURNED'}
        except Exception as e:
            logging.error(f"Error callback: {e}")
            logging.debug(f"Local variables: magnet: {magnet} ||| save_path: {save_path}, download: {download_response}, torrent_info: {torrent_info}")
            return {'content_path':'ERROR_RETURNED'}

        logging.info(f"Torrent download finished, returning...")
        logging.info(f"{torrent_info}")
        return torrent_info

try:
    process(torrent_type, name, link)
except Exception as e:
    logging.error(f"Callback: {e}")
    sys.exit(1)
